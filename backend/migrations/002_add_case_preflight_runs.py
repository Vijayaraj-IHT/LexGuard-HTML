"""Migration 002: case-preflight ledger + cases index alignment.

Creates ``case_preflight_runs`` (JSONB on PostgreSQL, JSON-encoded TEXT on SQLite)
and makes sure the ``cases`` table carries the indexes the preflight and search paths
rely on:

    ix_cases_file_hash       (file_hash)
    ix_cases_cnr_number      (cnr_number)
    ix_cases_decision_date   (decision_date)
    ix_cases_status          (status)

Idempotent: safe to run repeatedly. It only creates tables and indexes — nothing is
dropped, altered or rewritten.

Usage (from the repository root or backend/):
    python backend/migrations/002_add_case_preflight_runs.py
    python backend/migrations/002_add_case_preflight_runs.py --dry-run
    DATABASE_URL=postgresql+psycopg2://... python backend/migrations/002_add_case_preflight_runs.py
"""
import argparse
import os
import sys

# Ensure backend/ is importable when the script is run directly.
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import inspect, text  # noqa: E402

from app.core.database import engine  # noqa: E402
from app.models.preflight import CasePreflightRun  # noqa: E402
from app.services.case_preflight_service import CASE_INDEXES  # noqa: E402


def run(dry_run: bool = False) -> dict:
    dialect = engine.dialect.name
    print(f"Connecting to database engine: {dialect} ({engine.url.drivername})")
    inspector = inspect(engine)
    result = {
        "dialect": dialect,
        "table_created": False,
        "table_present": inspector.has_table(CasePreflightRun.__tablename__),
        "indexes_created": [],
        "indexes_present": [],
        "dry_run": dry_run,
    }

    # 1. Ledger table
    if result["table_present"]:
        print(f"  [*] Table already exists: {CasePreflightRun.__tablename__}")
    elif dry_run:
        print(f"  [+] Would create table: {CasePreflightRun.__tablename__}")
        result["table_created"] = True
    else:
        CasePreflightRun.__table__.create(bind=engine, checkfirst=True)
        result["table_created"] = True
        result["table_present"] = True
        print(f"  [+] Created table: {CasePreflightRun.__tablename__} ({dialect} column types)")

    # 2. cases indexes
    if not inspector.has_table("cases"):
        print("  [!] cases table not found; skipping index alignment")
        return result

    existing = {ix.get("name") for ix in inspector.get_indexes("cases")}
    for name, column in CASE_INDEXES.items():
        if name in existing:
            result["indexes_present"].append(name)
            print(f"  [*] Index already exists: {name}")
            continue
        if dry_run:
            print(f"  [+] Would create index: {name} on cases({column})")
            result["indexes_created"].append(name)
            continue
        with engine.begin() as conn:
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON cases ({column})"))
        result["indexes_created"].append(name)
        print(f"  [+] Created index: {name} on cases({column})")

    print("Migration 002 completed.")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="print what would change, touch nothing")
    args = ap.parse_args()
    run(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
