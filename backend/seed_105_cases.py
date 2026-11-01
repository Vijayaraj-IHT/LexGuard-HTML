import sys
import os
import uuid
import datetime
import json
from pathlib import Path

# Add backend directory to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.core.database import SessionLocal
from app.models.case import Case
from app.models.user import User
from app.models.document_version import DocumentVersion
from app.services.crypto_service import compute_sha256
from app.services.embedding_service import embedding_service
from app.core.security import get_password_hash
from enrich_case_structure import enrich_case

# Ensure storage directory exists
STORAGE_DIR = Path("storage/cases")
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# Read case data from JSON definition file
CASES_DATA_FILE = Path(__file__).parent / "landmark_cases_data.json"
with open(CASES_DATA_FILE, "r", encoding="utf-8") as f:
    CASES_DATA = json.load(f)


def generate_case_pdf(filepath: Path, case: dict) -> bytes:
    """Generates a structured, printable judicial document with court formatting."""
    content = f"""IN THE {case['court'].upper()}
CASE NO: {case['case_no']}
CITATION: {case.get('citation', 'N/A')}
YEAR: {case['year']}

CORAM / BENCH:
Hon'ble Judges: {case['judge']}

PARTIES:
{case['parties']}

STATUTES & ACTS REFERRED:
{', '.join(case['act_tags'])}

KEY PROVISIONS & SECTIONS:
{', '.join(case['section_tags'])}

LEGAL KEYWORDS & TOPICS:
{', '.join(case['keyword_tags'])}

================================================================================
                    JUDGMENT SUMMARY & RATIO DECIDENDI
================================================================================

{case['summary']}

1. ISSUES CONSIDERED:
   The court addressed questions of legal interpretation under {', '.join(case['section_tags'])}.

2. ANALYSIS & PRECEDENT CONTEXT:
   Having examined the statutory scheme, fundamental principles of jurisprudence,
   and constitutional safeguards, the Court reiterated the necessity of strict
   compliance with statutory procedure and evidentiary standards.

3. HELD & BINDING RATIO:
   The principle formulated in this judgment constitutes binding judicial precedent
   within its territorial and appellate jurisdiction.

[LEXGUARD VERIFIED OFFICIAL REPOSITORY RECORD - TAMPER-PROTECTED COPY]
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    with open(filepath, "rb") as f:
        return f.read()


def seed_database():
    print(f"Starting Lexguard Batch Ingestion for {len(CASES_DATA)} Landmark Cases...")

    db = SessionLocal()
    try:
        # Ensure Registry Staff exists
        staff_user = db.query(User).filter(User.email == "staff@court.gov.in").first()
        if not staff_user:
            staff_user = User(
                id=str(uuid.uuid4()),
                email="staff@court.gov.in",
                name="Principal Court Registrar",
                password_hash=get_password_hash("staff123"),
                role="staff",
                status="active",
                credential_id="COURT-REG-001"
            )
            db.add(staff_user)
            db.commit()
            db.refresh(staff_user)
            print("Verified Registry Staff account: staff@court.gov.in")

        inserted = 0
        skipped = 0
        for i, cdata in enumerate(CASES_DATA, start=1):
            existing = db.query(Case).filter(Case.case_no == cdata["case_no"]).first()
            if existing:
                skipped += 1
                continue

            case_id = str(uuid.uuid4())
            file_name = f"{case_id}.pdf"
            file_path = STORAGE_DIR / file_name

            # Generate PDF file
            file_bytes = generate_case_pdf(file_path, cdata)

            # Compute SHA-256 Hash
            file_hash = compute_sha256(file_bytes)

            # Generate 384-dim Vector Embedding for Semantic Search
            embed_text = f"{cdata['title']} {cdata['summary']} {' '.join(cdata['section_tags'])} {' '.join(cdata['keyword_tags'])}"
            embedding_vec = embedding_service.generate_embedding(embed_text)

            new_case = Case(
                id=case_id,
                case_no=cdata["case_no"],
                title=cdata["title"],
                court=cdata["court"],
                year=cdata["year"],
                judge=cdata["judge"],
                parties=cdata["parties"],
                act_tags=cdata["act_tags"],
                section_tags=cdata["section_tags"],
                keyword_tags=cdata["keyword_tags"],
                summary=cdata["summary"],
                outcome=cdata.get("outcome", "Decided"),
                file_path=str(file_path),
                file_hash=file_hash,
                status="published",
                uploaded_by_id=staff_user.id,
                approved_by_id=staff_user.id,
                approved_at=datetime.datetime.now(datetime.timezone.utc),
                embedding=embedding_vec
            )
            enrich_case(new_case)

            db.add(new_case)

            # Add DocumentVersion record
            v1 = DocumentVersion(
                case_id=case_id,
                version_no=1,
                file_path=str(file_path),
                file_hash=file_hash,
                change_summary="Initial verified landmark precedent ingestion",
                changed_by_id=staff_user.id,
            )
            db.add(v1)

            inserted += 1
            if inserted % 20 == 0 or i == len(CASES_DATA):
                db.commit()
                print(f"  Ingested [{i}/{len(CASES_DATA)}] cases...")

        db.commit()
        print(f"\nFinished Ingestion: {inserted} newly seeded, {skipped} already existing.")
        total_cases = db.query(Case).count()
        print(f"Total cases in repository ready for search: {total_cases}")

    except Exception as e:
        db.rollback()
        print(f"Error during seeding: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
