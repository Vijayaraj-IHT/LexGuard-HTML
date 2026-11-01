#!/usr/bin/env python3
"""CLI: verify (and optionally repair) the stored case-file corpus.

Runs the same service the API uses, records a row in ``case_preflight_runs``, and
prints a summary. No absolute paths are printed.

Examples
--------
    python preflight_cases.py                                   # verify (PostgreSQL required)
    python preflight_cases.py --allow-sqlite                     # local evaluation on lexguard.db
    python preflight_cases.py --mode repair --quarantine-mismatch --allow-sqlite
    python preflight_cases.py --json | jq .

Exit codes
----------
    0  clean run (COMPLETED / REPAIRED)
    1  run finished but found issues (COMPLETED_WITH_ISSUES)
    2  refused or failed (POSTGRES_REQUIRED / BUSY / FAILED)
"""
import argparse
import json
import os
import sys

BACKEND_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BACKEND_DIR)

from app.core.database import SessionLocal, engine  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.models.preflight import (  # noqa: E402
    PREFLIGHT_STATUS_COMPLETED,
    PREFLIGHT_STATUS_ISSUES,
    PREFLIGHT_STATUS_REPAIRED,
)
from app.services.case_preflight_service import (  # noqa: E402
    ensure_preflight_schema,
    run_case_preflight,
    run_summary,
)

EXIT_OK = 0
EXIT_ISSUES = 1
EXIT_REFUSED = 2


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Verify the case-file corpus against its recorded hashes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--mode", choices=["verify", "repair"], default="verify")
    ap.add_argument(
        "--quarantine-mismatch",
        action="store_true",
        help="with --mode repair: set status='quarantined' on cases whose file hash does not match",
    )
    ap.add_argument(
        "--allow-sqlite",
        action="store_true",
        help="permit running on SQLite (local evaluation); advisory locking is disabled",
    )
    ap.add_argument("--trigger", default="cli", help="label recorded on the run row")
    ap.add_argument("--batch-size", type=int, default=int(getattr(settings, "PREFLIGHT_DEFAULT_BATCH_SIZE", 500)))
    ap.add_argument("--no-hash", action="store_true", help="skip SHA-256 re-computation (faster, weaker)")
    ap.add_argument("--json", action="store_true", help="print the run summary as JSON only")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.quarantine_mismatch and args.mode != "repair":
        print("--quarantine-mismatch requires --mode repair", file=sys.stderr)
        return EXIT_REFUSED

    schema = ensure_preflight_schema(engine)
    if not args.json:
        print(f"Database: {engine.url.drivername} ({schema['dialect']})")
        if schema["table_created"]:
            print("  [+] created case_preflight_runs")
        if schema["indexes_created"]:
            print(f"  [+] created indexes: {', '.join(schema['indexes_created'])}")

    db = SessionLocal()
    try:
        run = run_case_preflight(
            db,
            mode=args.mode,
            trigger=args.trigger,
            batch_size=args.batch_size,
            allow_non_postgres=args.allow_sqlite,
            quarantine_mismatch=args.quarantine_mismatch,
            verify_hashes=not args.no_hash,
        )
        summary = run_summary(run, max_samples=int(getattr(settings, "PREFLIGHT_MAX_SAMPLES", 25)))
    finally:
        db.close()

    if args.json:
        print(json.dumps(summary, indent=2, default=str))
    else:
        report = summary.get("report") or {}
        print(f"Run {summary['id']}  status={summary['status']}  mode={summary['mode']}")
        print(f"  total cases          : {summary['total_cases']}")
        print(f"  verified             : {summary['verified_count']}")
        print(f"  missing file         : {summary['missing_count']}")
        print(f"  hash mismatch        : {summary['mismatch_count']}")
        print(f"  invalid metadata     : {summary['invalid_metadata_count']}")
        print(f"  duplicate hash cases : {summary['duplicate_hash_count']}")
        if report.get("metadata_reasons"):
            print(f"  metadata reasons     : {report['metadata_reasons']}")
        if report.get("repair", {}).get("quarantined_count"):
            print(f"  quarantined          : {report['repair']['quarantined_count']}")
        if report.get("message"):
            print(f"  message              : {report['message']}")
        if report.get("duration_ms") is not None:
            print(f"  duration             : {report['duration_ms']} ms")

    if summary["status"] in (PREFLIGHT_STATUS_COMPLETED, PREFLIGHT_STATUS_REPAIRED):
        return EXIT_OK
    if summary["status"] == PREFLIGHT_STATUS_ISSUES:
        return EXIT_ISSUES
    return EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
