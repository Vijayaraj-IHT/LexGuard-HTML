"""
LexGuard read-only integrity report.

Runs the same checks that the integrity review performed by hand, and prints them.
It opens the SQLite database READ-ONLY (SQLite URI mode=ro), so it cannot change data.

Usage (from the backend/ directory):
    python integrity_report.py --db lexguard.db
    python integrity_report.py --db lexguard.db --json

Checks:
  1. Audit chain: full verify_audit_chain result, per-entry recomputation failures
     grouped by action, broken parent links, timezone-naive timestamps.
  2. Judicial seals: published records, sealed records, seals that reproduce,
     sealed records with no APPROVE audit entry.
  3. Maker-checker: published records approved by their own uploader.
  4. Documents: each record's PDF on disk, re-hashed against file_hash.
  5. Registry hygiene: duplicate file hashes, empty full text on published records,
     placeholder case numbers.

Exit status: 0 if every check passed, 1 if any integrity check failed, 2 on usage error.
"""

import argparse
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _open_readonly(db_path: str) -> None:
    """Points the app's engine at the database in read-only mode. Must run before importing app.*."""
    abs_path = os.path.abspath(db_path)
    if not os.path.exists(abs_path):
        print(f"error: database not found: {abs_path}", file=sys.stderr)
        sys.exit(2)
    os.environ["DATABASE_URL"] = f"sqlite:///file:{abs_path}?mode=ro&uri=true"


def run(db_path: str) -> dict:
    _open_readonly(db_path)

    # Imports happen after the environment is set, so the engine is read-only.
    from app.core.database import SessionLocal
    from app.models.audit_log import AuditLog
    from app.models.case import Case
    from app.services.crypto_service import (
        verify_audit_chain,
        compute_h_meta,
        compute_h_text,
        compute_judicial_seal,
        verify_sha256_stream,
    )
    from app.services.audit_service import check_audit_entry
    import hmac

    db = SessionLocal()
    report = {"chain": {}, "seals": {}, "maker_checker": {}, "documents": {}, "hygiene": {}}
    failures = []

    # 1. Audit chain -----------------------------------------------------------
    # Chain order shared with the writer (timestamp asc, id tiebreak).
    from app.services.audit_service import LEDGER_ORDER_ASC
    logs = db.query(AuditLog).order_by(*LEDGER_ORDER_ASC).all()
    chain = verify_audit_chain(logs)
    per_action = collections.Counter()
    link_breaks = 0
    for lg in logs:
        c = check_audit_entry(db, lg)
        if not c["recomputed_ok"]:
            per_action[lg.action] += 1
        if not c["link_ok"]:
            link_breaks += 1
    naive = sum(1 for lg in logs if getattr(lg.timestamp, "tzinfo", None) is None)
    report["chain"] = {
        "records": len(logs),
        "order": "chain order (timestamp asc, id tiebreak)",
        "full_chain_valid": chain["is_valid"],
        "first_failure": chain.get("reason") or chain.get("message"),
        "hash_recompute_failures": sum(per_action.values()),
        "hash_recompute_failures_by_action": dict(per_action.most_common()),
        "broken_parent_links": link_breaks,
        "naive_timestamps": naive,
    }
    if not chain["is_valid"]:
        failures.append("audit chain invalid")

    # 2. Judicial seals ----------------------------------------------------------
    cases = db.query(Case).all()
    published = [c for c in cases if c.status == "published"]
    sealed = [c for c in published if c.redacted_file_hash]
    reproducible = 0
    sealed_no_approve_log = 0
    approve_case_ids = {
        row.case_id
        for row in db.query(AuditLog.case_id).filter(AuditLog.action == "APPROVE").all()
    }
    for c in sealed:
        if c.approved_at:
            recomputed = compute_judicial_seal(
                c.file_hash or "",
                compute_h_meta(c.case_no, c.court, c.judge, c.disposition, c.year),
                compute_h_text(c.full_text),
                c.approved_at.isoformat(),
            )
            if hmac.compare_digest(recomputed, c.redacted_file_hash):
                reproducible += 1
        if c.id not in approve_case_ids:
            sealed_no_approve_log += 1
    report["seals"] = {
        "published": len(published),
        "published_without_seal": len(published) - len(sealed),
        "sealed": len(sealed),
        "seals_reproducing": reproducible,
        "sealed_without_approve_log": sealed_no_approve_log,
    }
    if len(published) - len(sealed) > 0 or reproducible < len(sealed):
        failures.append("judicial seals missing or not reproducible")

    # 3. Maker-checker -----------------------------------------------------------
    self_approved = sum(
        1 for c in published if c.approved_by_id and c.approved_by_id == c.uploaded_by_id
    )
    report["maker_checker"] = {"published": len(published), "self_approved": self_approved}
    if self_approved:
        failures.append("published records approved by their own uploader")

    # 4. Documents on disk --------------------------------------------------------
    from app.core.config import resolve_case_pdf_path
    counts = collections.Counter()
    for c in cases:
        if not c.file_path:
            counts["no_file_path"] += 1
            continue
        p = resolve_case_pdf_path(c.file_path)
        if not os.path.exists(p):
            counts["missing_on_disk"] += 1
            continue
        if verify_sha256_stream(str(p), c.file_hash or ""):
            counts["hash_match"] += 1
        else:
            counts["hash_MISMATCH"] += 1
    report["documents"] = dict(counts)
    if counts.get("hash_MISMATCH"):
        failures.append("document bytes do not match registered hash")

    # 5. Registry hygiene ----------------------------------------------------------
    hashes = collections.Counter(c.file_hash for c in cases if c.file_hash)
    placeholder = sum(
        1 for c in cases
        if (c.case_no or "").startswith(("CASE_", "Case No. Not", "Pending"))
    )
    report["hygiene"] = {
        "duplicate_file_hash_groups": sum(1 for v in hashes.values() if v > 1),
        "published_with_empty_full_text": sum(1 for c in published if not (c.full_text or "").strip()),
        "placeholder_case_numbers": placeholder,
    }

    db.close()
    report["failed_checks"] = failures
    report["ok"] = not failures
    return report


def _print(report: dict) -> None:
    def section(title, data):
        print(f"\n== {title}")
        for k, v in data.items():
            print(f"  {k}: {v}")

    print("LexGuard integrity report (read-only)")
    section("1. Audit chain", report["chain"])
    section("2. Judicial seals", report["seals"])
    section("3. Maker-checker", report["maker_checker"])
    section("4. Documents on disk", report["documents"])
    section("5. Registry hygiene", report["hygiene"])
    print("\n== Result")
    if report["ok"]:
        print("  PASS: all integrity checks passed")
    else:
        print("  FAIL:")
        for f in report["failed_checks"]:
            print(f"    - {f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True, help="path to a SQLite database (opened read-only)")
    ap.add_argument("--json", action="store_true", help="print machine-readable JSON")
    args = ap.parse_args()
    report = run(args.db)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        _print(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
