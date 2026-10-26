"""
LexGuard Scaled Automated Batch Ingestion Engine.
Processes authentic Indian court judgment PDFs from an incoming directory,
computes cryptographic SHA-256 seals, extracts coram, CNRs, dates, and sanitized text,
generates canonical judicial filenames, saves records into PostgreSQL,
and dynamically links them into the Precedent Citation Network.
"""
import sys
import os
import shutil
import hashlib
import json
import uuid
import re
from datetime import datetime, timezone
import psycopg2

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.services.text_sanitizer import text_sanitizer
from app.services.embedding_service import embedding_service
from app.core.database import SessionLocal
from app.services.audit_service import log_audit_event

DB_URI = "postgresql://lexguard:lexguard123@localhost:5432/lexguard"

DEFAULT_INCOMING_DIR = os.path.join(os.path.dirname(__file__), "..", "incoming_pdfs")
TARGET_STORAGE_DIRS = [
    os.path.join(os.path.dirname(__file__), "..", "backend", "storage", "cases"),
    os.path.join(os.path.dirname(__file__), "..", "storage", "cases"),
    os.path.join(os.path.dirname(__file__), "..", "..", "LexGuard-HTML", "storage", "cases"),
    os.path.join(os.path.dirname(__file__), "..", "..", "LexGuard-HTML", "backend", "storage", "cases"),
]
QUARANTINE_DIR = os.path.join(os.path.dirname(__file__), "..", "backend", "storage", "quarantine")

os.makedirs(DEFAULT_INCOMING_DIR, exist_ok=True)
for d in TARGET_STORAGE_DIRS:
    os.makedirs(d, exist_ok=True)
os.makedirs(QUARANTINE_DIR, exist_ok=True)


def compute_file_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_court_code(court_str: str) -> str:
    c = (court_str or "").upper()
    if "SUPREME" in c:
        return "SC"
    if "MADRAS" in c:
        if "MADURAI" in c:
            return "MHC-MB"
        return "MHC-PS"
    if "GUJARAT" in c:
        return "GHC"
    if "BOMBAY" in c:
        return "BHC"
    if "CALCUTTA" in c or "KOLKATA" in c:
        return "CHC"
    if "DELHI" in c:
        return "DHC"
    if "JAMMU" in c or "KASHMIR" in c:
        return "JKHC"
    if "ALLAHABAD" in c:
        return "ALHC"
    if "HIGH COURT" in c or "HC" in c:
        return "HC"
    return "IND"


def clean_case_no(case_no: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", case_no or "judgment").strip("_")
    if len(clean) > 35:
        clean = clean[:35].rstrip("_")
    return clean or "judgment"


def build_case_pdf_filename(court: str, year: int, case_no: str, case_id: str, decision_date=None) -> str:
    court_code = get_court_code(court)
    clean_no = clean_case_no(case_no)
    if decision_date:
        yr = str(decision_date.year)
    else:
        m = re.findall(r"(?:19|20)\d{2}", case_no or "")
        if m:
            yr = m[-1]
        else:
            yr = str(year) if year else str(datetime.now().year)
    short_id = str(case_id)[:8]
    return f"{court_code}_{yr}_{clean_no}_{short_id}.pdf"


def ingest_batch(incoming_dir: str = DEFAULT_INCOMING_DIR):
    print("=" * 70)
    print("LEXGUARD AUTOMATED BATCH INGESTION ENGINE")
    print("Target Directory:", incoming_dir)
    print("=" * 70)

    pdf_files = [f for f in os.listdir(incoming_dir) if f.lower().endswith(".pdf")]
    if not pdf_files:
        print(f" [!] No PDF files found in '{incoming_dir}'.")
        print(f" [i] Place your downloaded court judgment PDFs in '{incoming_dir}' and run again.")
        print("=" * 70)
        return

    print(f"Found {len(pdf_files)} PDF documents to process.")

    conn = psycopg2.connect(DB_URI)
    cur = conn.cursor()

    cur.execute("SELECT id FROM users WHERE role IN ('senior_staff', 'staff') LIMIT 1;")
    user_row = cur.fetchone()
    staff_user_id = user_row[0] if user_row else str(uuid.uuid4())

    successful = 0
    skipped = 0
    quarantined = 0

    for idx, fname in enumerate(pdf_files, 1):
        src_path = os.path.join(incoming_dir, fname)
        print(f"\n[{idx}/{len(pdf_files)}] Processing: {fname}")

        try:
            # 1. Compute Cryptographic SHA-256 Seal
            file_hash = compute_file_sha256(src_path)

            # Check for duplicate
            cur.execute("SELECT id, case_no FROM cases WHERE file_hash = %s;", (file_hash,))
            existing = cur.fetchone()
            if existing:
                print(f"  [-] SKIP: Document already indexed as '{existing[1]}' (Hash: {file_hash[:12]}...)")
                skipped += 1
                continue

            # 2. Extract Metadata & Sanitize Text via TextSanitizerService
            meta = text_sanitizer.extract_metadata_from_pdf(src_path)

            case_no = meta.get("case_no") or f"JUDGMENT/{file_hash[:8].upper()}/{datetime.now().year}"
            cnr = meta.get("cnr_number")
            decision_date = meta.get("decision_date")
            judge = meta.get("judge")
            bench_type = meta.get("bench_type") or "Single Bench"
            case_type = meta.get("case_type") or "Judgment"
            domain = meta.get("legal_domain") or "General"
            page_count = meta.get("page_count") or 1
            cleaned_text = meta.get("full_text") or ""
            act_tags = meta.get("act_tags") or []
            section_tags = meta.get("section_tags") or []

            pet = meta.get("petitioner")
            resp = meta.get("respondent")
            if pet and resp:
                title = f"{pet} v. {resp}"[:490]
            else:
                clean_name = os.path.splitext(fname)[0].replace("_", " ").replace("-", " ")
                title = f"Judgment in {case_no} ({clean_name[:80]})"

            court = "High Court of Judicature"
            if "MADURAI" in cleaned_text[:500].upper():
                court = "Madras High Court (Madurai Bench)"
            elif "MADRAS" in cleaned_text[:500].upper():
                court = "Madras High Court (Principal Seat, Chennai)"
            elif "BOMBAY" in cleaned_text[:500].upper():
                court = "High Court of Judicature at Bombay"
            elif "GUJARAT" in cleaned_text[:500].upper():
                court = "High Court of Gujarat at Ahmedabad"
            elif "CALCUTTA" in cleaned_text[:500].upper():
                court = "High Court at Calcutta"
            elif "SUPREME COURT" in cleaned_text[:500].upper():
                court = "Supreme Court of India"

            case_id = str(uuid.uuid4())
            case_year = decision_date.year if decision_date else datetime.now().year

            # 3. Canonical Judicial Filename & CAS Storage
            canonical_filename = build_case_pdf_filename(court, case_year, case_no, case_id, decision_date)
            for d in TARGET_STORAGE_DIRS:
                dst = os.path.join(d, canonical_filename)
                shutil.copy2(src_path, dst)

            rel_file_path = f"storage/cases/{canonical_filename}"

            # 4. Generate Summaries & Official Citation
            summary = f"Judgment delivered by {judge or 'the Court'} in {case_no}. The dispute involves {domain} concerning {', '.join(act_tags) or 'procedural rights'}."
            layman_summary = f"In this {case_type.lower()}, the {court} evaluated issues between {pet or 'the Petitioner'} and {resp or 'the Respondent'}. The Court decided on statutory principles governing {domain}."
            official_citation = f"{case_year} LexGuard ({case_type[:4].strip()}) {case_id[:6].upper()}"

            # 5. Generate Dense Vector Embedding for Semantic Search
            embed_text = f"{title}. {summary}. {' '.join(act_tags)} {' '.join(section_tags)}"
            try:
                embedding = embedding_service.generate_embedding(embed_text)
            except Exception:
                embedding = None

            # 6. Insert Record into PostgreSQL
            cur.execute("""
                INSERT INTO cases (
                    id, case_no, cnr_number, case_type, title, court, year, decision_date,
                    judge, bench_type, petitioner, respondent, legal_domain,
                    act_tags, section_tags, keyword_tags, summary, layman_summary,
                    outcome, disposition, ratio_decidendi, issues_framed, statutory_tests,
                    precedents_cited, full_text, page_count, file_path, file_hash,
                    precedential_status, official_citation, embedding, status,
                    auto_extracted, uploaded_by_id, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s
                );
            """, (
                case_id, case_no, cnr, case_type, title, court, case_year, decision_date,
                judge, bench_type, pet, resp, domain,
                json.dumps(act_tags), json.dumps(section_tags), json.dumps([domain.lower(), case_type.lower()]),
                summary, layman_summary, "Disposed", "Disposed",
                f"Holding and principles affirmed under {domain} in {case_no}.",
                json.dumps(["Procedural standard adherence", "Statutory threshold compliance"]),
                json.dumps([]), json.dumps([]), cleaned_text, page_count,
                rel_file_path, file_hash, "Precedential status not checked", official_citation,
                json.dumps(embedding) if embedding else None, "published",
                True, staff_user_id, datetime.now(timezone.utc), datetime.now(timezone.utc)
            ))

            # 7. Record the event through the canonical audit writer. The
            # raw case insert is committed first so the ORM writer can see it.
            conn.commit()
            audit_db = SessionLocal()
            try:
                log_audit_event(
                    db=audit_db,
                    action="INGEST_OFFICIAL_JUDGMENT",
                    user_id=staff_user_id,
                    case_id=case_id,
                    details=f"Ingested official court judgment {case_no} as {canonical_filename} (SHA-256: {file_hash[:16]}...)",
                    ip_address="127.0.0.1",
                )
            finally:
                audit_db.close()

            successful += 1
            print(f"  [+] SUCCESS: Registered '{case_no}' -> {canonical_filename}")

        except Exception as e:
            conn.rollback()
            quarantined += 1
            print(f"  [X] ERROR processing '{fname}': {e}")
            try:
                shutil.copy2(src_path, os.path.join(QUARANTINE_DIR, fname))
            except Exception:
                pass

    conn.close()

    print("\n" + "=" * 70)
    print("BATCH INGESTION SUMMARY")
    print(f"Total PDFs In Batch:  {len(pdf_files)}")
    print(f"Successfully Indexed: {successful}")
    print(f"Duplicates Skipped:   {skipped}")
    print(f"Quarantined / Error:  {quarantined}")
    print("=" * 70)

    # Automatically re-link citation network if new judgments were ingested
    if successful > 0:
        print("\nRe-linking precedent citation graph...")
        try:
            import link_citation_network
            link_citation_network.main()
        except Exception as e:
            print("Citation graph update error:", e)


if __name__ == "__main__":
    dir_arg = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INCOMING_DIR
    ingest_batch(dir_arg)
