"""
LexGuard Bulk Document Ingestion CLI Tool.
Iterates through a folder of official Indian Court judgment PDFs,
executes the 3-pass extraction pipeline, stores records in PostgreSQL,
and outputs a CSV ingestion audit report.
"""

import os
import sys
import glob
import argparse
import csv
from datetime import datetime

# Add backend directory to sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.core.database import SessionLocal
from app.models.case import Case
from app.models.user import User
from app.services.crypto_service import compute_sha256
from app.services.extraction_service import ExtractionService
from app.services.audit_service import log_audit_event


def run_bulk_ingestion(folder_path: str, staff_email: str = "staff@lexguard.gov.in", output_csv: str = None):
    """Processes all PDFs in folder_path and saves case records."""
    if not os.path.exists(folder_path):
        print(f"[ERROR] Target folder does not exist: {folder_path}")
        return

    pdf_files = sorted(glob.glob(os.path.join(folder_path, "*.pdf")))
    if not pdf_files:
        print(f"[WARNING] No .pdf files found in {folder_path}")
        return

    print(f"\n=======================================================")
    print(f" LexGuard Automated Bulk Ingestion Pipeline")
    print(f" Target Folder: {folder_path}")
    print(f" Total PDF Documents: {len(pdf_files)}")
    print(f"=======================================================\n")

    db = SessionLocal()
    # Resolve staff user
    staff_user = db.query(User).filter(User.email == staff_email).first()
    if not staff_user:
        staff_user = db.query(User).filter(User.role.in_(["court_staff", "senior_staff"])).first()

    if not staff_user:
        # Fallback to any active user or system
        staff_user = db.query(User).first()

    uploader_id = staff_user.id if staff_user else "system-service-account"

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = output_csv or f"ingestion_report_{timestamp_str}.csv"
    report_path = os.path.join(PROJECT_ROOT, report_filename)

    results = []
    processed_count = 0
    duplicate_count = 0
    error_count = 0

    for idx, pdf_path in enumerate(pdf_files, 1):
        filename = os.path.basename(pdf_path)
        print(f"[{idx}/{len(pdf_files)}] Processing: {filename} ...", end=" ", flush=True)

        try:
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            file_hash = compute_sha256(pdf_bytes)

            # Check duplicate
            existing = db.query(Case).filter(Case.file_hash == file_hash).first()
            if existing:
                print(f"[SKIPPED: Duplicate case {existing.case_no}]")
                duplicate_count += 1
                results.append({
                    "filename": filename,
                    "case_no": existing.case_no,
                    "cnr": existing.case_no,
                    "court": existing.court,
                    "judge": existing.judge,
                    "outcome": existing.outcome,
                    "overall_confidence": 1.0,
                    "sha256": file_hash,
                    "status": "DUPLICATE_EXISTING",
                })
                continue

            # Run Extraction
            extracted = ExtractionService.extract_from_pdf(pdf_path, extract_passes=[1, 2, 3])

            new_case = Case(
                case_no=extracted.get("case_no", "Pending Staff Review")[:100],
                title=extracted.get("title", f"Document {filename}")[:300],
                court=extracted.get("court", "High Court")[:150],
                year=extracted.get("year", datetime.now().year),
                judge=extracted.get("judge"),
                parties=extracted.get("parties"),
                act_tags=extracted.get("act_tags") or [],
                section_tags=extracted.get("section_tags") or [],
                keyword_tags=extracted.get("keyword_tags") or [],
                summary=extracted.get("summary"),
                outcome=extracted.get("outcome"),
                facts=extracted.get("prayer"),
                ratio_decidendi=extracted.get("ratio_decidendi"),
                disposition=extracted.get("disposition") or extracted.get("outcome"),
                full_text=extracted.get("full_text"),
                page_count=extracted.get("page_count", 1),
                source_url=extracted.get("source_url"),
                source_verification_state=extracted.get("source_verification_state", "unverified"),
                precedential_status=extracted.get("precedential_status", "Precedential status not checked"),
                file_path=pdf_path,
                file_hash=file_hash,
                auto_extracted=True,
                status="pending_review",
                uploaded_by_id=uploader_id,
            )
            db.add(new_case)
            db.commit()
            db.refresh(new_case)

            log_audit_event(
                db=db,
                action="BULK_INGEST_DOCUMENT",
                user_id=uploader_id,
                case_id=new_case.id,
                details=f"Bulk ingested {filename} ({new_case.case_no})",
            )

            processed_count += 1
            print(f"[OK: {new_case.case_no} | Conf: {extracted.get('overall_confidence', 0.5)}]")

            results.append({
                "filename": filename,
                "case_no": new_case.case_no,
                "cnr": extracted.get("cnr"),
                "court": new_case.court,
                "judge": new_case.judge,
                "outcome": new_case.outcome,
                "overall_confidence": extracted.get("overall_confidence", 0.5),
                "sha256": file_hash,
                "status": "INGESTED_PENDING_REVIEW",
            })

        except Exception as e:
            db.rollback()
            error_count += 1
            print(f"[FAILED: {e}]")
            results.append({
                "filename": filename,
                "case_no": "ERROR",
                "cnr": "ERROR",
                "court": "ERROR",
                "judge": "ERROR",
                "outcome": "ERROR",
                "overall_confidence": 0.0,
                "sha256": "N/A",
                "status": f"ERROR: {str(e)[:100]}",
            })

    db.close()

    # Write CSV Report
    if results:
        fieldnames = ["filename", "case_no", "cnr", "court", "judge", "outcome", "overall_confidence", "sha256", "status"]
        with open(report_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)

    print("\n=======================================================")
    print(f" Ingestion Summary Report")
    print(f" Total Processed: {processed_count}")
    print(f" Duplicates:      {duplicate_count}")
    print(f" Errors:          {error_count}")
    print(f" Report Saved To: {report_path}")
    print(f"=======================================================\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bulk Ingestion CLI for LexGuard Court Judgments")
    parser.add_argument("--folder", type=str, default=os.path.join(PROJECT_ROOT, "backend", "seed_corpus", "pdfs"), help="Path to PDF directory")
    parser.add_argument("--user", type=str, default="staff@lexguard.gov.in", help="Uploader staff email")
    parser.add_argument("--output", type=str, default=None, help="Output CSV report path")

    args = parser.parse_args()
    run_bulk_ingestion(folder_path=args.folder, staff_email=args.user, output_csv=args.output)
