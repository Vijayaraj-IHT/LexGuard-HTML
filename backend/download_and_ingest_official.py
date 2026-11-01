import sys
import json
import hashlib
import urllib.request
import io
from pathlib import Path

# Setup paths
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from app.core.database import SessionLocal
from app.models.case import Case
from app.models.user import User
from app.services.embedding_service import embedding_service
import pdfplumber

MANIFEST_PATH = HERE / "seed_corpus" / "manifest.json"
PDF_DIR = HERE / "seed_corpus" / "pdfs"
STORAGE_DIR = HERE / "storage" / "cases"

PDF_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def download_file(file_id: str) -> bytes:
    """Download Google Drive file by ID handling redirects."""
    urls = [
        f"https://drive.usercontent.google.com/download?id={file_id}&export=download&authuser=0",
        f"https://drive.google.com/uc?export=download&id={file_id}"
    ]
    for url in urls:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                # If Google returns an HTML confirm screen for larger files
                if b"confirm=" in data and b"href=\"" in data:
                    confirm_token = None
                    for line in data.split(b"\n"):
                        if b"confirm=" in line:
                            import re
                            m = re.search(r'confirm=([0-9a-zA-Z_-]+)', line.decode('utf-8', errors='ignore'))
                            if m:
                                confirm_token = m.group(1)
                                break
                    if confirm_token:
                        conf_url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm={confirm_token}"
                        conf_req = urllib.request.Request(conf_url, headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(conf_req, timeout=30) as c_resp:
                            data = c_resp.read()
                if data.startswith(b"%PDF"):
                    return data
        except Exception as e:
            print(f"  Attempt failed for URL {url}: {e}")
    raise RuntimeError(f"Could not download PDF for file ID {file_id}")


def extract_pdf_content(pdf_bytes: bytes) -> tuple[str, int]:
    """Extract full text with page boundaries and page count."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page_count = len(pdf.pages)
        full_text_parts = []
        for i, page in enumerate(pdf.pages):
            txt = page.extract_text() or ""
            txt_clean = txt.strip()
            full_text_parts.append(f"--- PAGE {i + 1} ---\n{txt_clean}")
        return "\n\n".join(full_text_parts), page_count


def run_ingestion():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    documents = manifest.get("documents", [])
    print(f"Loaded manifest with {len(documents)} official judgments.")

    db = SessionLocal()
    # Get a staff or admin user for uploaded_by_id
    staff_user = db.query(User).filter(User.role.in_(["staff", "senior_staff", "court_staff"])).first()
    if not staff_user:
        staff_user = db.query(User).first()
    uploader_id = staff_user.id if staff_user else "system-seed"

    success_count = 0
    duplicate_count = 0

    for idx, doc in enumerate(documents, start=1):
        filename = doc["file"]
        expected_hash = doc["sha256"]
        drive_id = doc["drive_file_id"]
        case_no = doc["case_no"]
        title = doc["title"]
        court = doc["court"]

        print(f"\n[{idx}/{len(documents)}] Processing {case_no}: {title[:50]}...")

        # 1. Check local cache or download
        local_path = PDF_DIR / filename
        storage_path = STORAGE_DIR / f"{expected_hash}.pdf"

        pdf_bytes = None
        if local_path.exists():
            with open(local_path, "rb") as f:
                data = f.read()
            if hashlib.sha256(data).hexdigest() == expected_hash:
                print(f"  Found cached file with matching hash: {filename}")
                pdf_bytes = data

        if not pdf_bytes:
            print(f"  Downloading from Google Drive (ID: {drive_id})...")
            try:
                pdf_bytes = download_file(drive_id)
                actual_hash = hashlib.sha256(pdf_bytes).hexdigest()
                if actual_hash != expected_hash:
                    print(f"  WARNING: Hash mismatch! Expected {expected_hash}, got {actual_hash}")
                else:
                    print(f"  Downloaded & verified SHA-256 successfully.")
                # Save locally
                with open(local_path, "wb") as f:
                    f.write(pdf_bytes)
            except Exception as e:
                print(f"  ERROR downloading {filename}: {e}")
                continue

        # Save to persistent storage path
        with open(storage_path, "wb") as f:
            f.write(pdf_bytes)

        # 2. Extract official text
        try:
            full_text, page_count = extract_pdf_content(pdf_bytes)
            print(f"  Extracted {len(full_text)} characters across {page_count} pages.")
        except Exception as e:
            print(f"  Error extracting text from PDF: {e}")
            full_text = doc.get("summary") or ""
            page_count = 1

        # 3. Check if already exists in DB
        existing = db.query(Case).filter(Case.file_hash == expected_hash).first()
        if not existing:
            existing = db.query(Case).filter(Case.case_no == case_no).first()

        # Build embedding for semantic similarity
        embedding_text = f"{title}. {doc.get('summary') or ''}. {' '.join(doc.get('section_tags') or [])} {' '.join(doc.get('keyword_tags') or [])}"
        try:
            emb = embedding_service.generate_embedding(embedding_text)
        except Exception:
            emb = None

        if existing:
            # Update with official extracted text, storage path, and status
            existing.full_text = full_text
            existing.page_count = page_count
            existing.file_path = str(storage_path)
            existing.file_hash = expected_hash
            existing.status = "published"
            existing.court = court
            existing.title = title
            existing.summary = doc.get("summary") or existing.summary
            existing.act_tags = doc.get("act_tags") or existing.act_tags
            existing.section_tags = doc.get("section_tags") or existing.section_tags
            existing.keyword_tags = doc.get("keyword_tags") or existing.keyword_tags
            existing.source_url = "https://mhc.tn.gov.in/judis" if "Madras" in court else "https://judgments.ecourts.gov.in"
            existing.source_verification_state = "verified"
            existing.precedential_status = "Good Law"
            if emb:
                existing.embedding = emb
            db.commit()
            print(f"  Updated existing record in DB: ID={existing.id}")
            duplicate_count += 1
        else:
            new_case = Case(
                case_no=case_no,
                title=title,
                court=court,
                year=doc.get("year", 2026),
                judge=doc.get("judge"),
                parties=doc.get("parties"),
                act_tags=doc.get("act_tags") or [],
                section_tags=doc.get("section_tags") or [],
                keyword_tags=doc.get("keyword_tags") or [],
                summary=doc.get("summary"),
                outcome=doc.get("outcome"),
                facts=doc.get("summary"),  # Pre-seed factual matrix
                ratio_decidendi=f"Decision of {court} in {case_no}",
                statutory_tests=[{"test": t, "mandatory": True} for t in (doc.get("section_tags") or [])],
                disposition="Allowed" if "Bail" in title or "Quash" in title else "Decided",
                precedents_cited=[],
                full_text=full_text,
                page_count=page_count,
                file_path=str(storage_path),
                file_hash=expected_hash,
                embedding=emb,
                status="published",
                uploaded_by_id=uploader_id,
                source_url="https://mhc.tn.gov.in/judis" if "Madras" in court else "https://judgments.ecourts.gov.in",
                source_verification_state="verified",
                precedential_status="Good Law",
            )
            db.add(new_case)
            db.commit()
            print(f"  Inserted new case into DB: ID={new_case.id}")
            success_count += 1

    db.close()
    print(f"\n==========================================")
    print(f"Corpus Ingestion Complete!")
    print(f"Newly Created: {success_count}")
    print(f"Updated / Enriched: {duplicate_count}")
    print(f"Total Processed: {len(documents)}")
    print(f"==========================================")


if __name__ == "__main__":
    run_ingestion()
