"""Explicitly reseal the LexGuard audit chain into a new segment.

This senior-operator tool never rewrites historical audit rows. It appends a
single CHAIN_RESEALED genesis event through ``audit_service``; verification
continues to report the archived legacy segment separately.
"""

from __future__ import annotations

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.core.database import SessionLocal, engine
from app.models.audit_log import AuditLog
from app.models.user import User
from app.services.audit_service import reseal_audit_chain
from app.services.crypto_service import verify_audit_chain


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Active senior_staff account email")
    parser.add_argument("--reason", required=True, help="Disclosed reseal reason (min 10 chars)")
    parser.add_argument(
        "--migrate",
        action="store_true",
        help="Run the idempotent Phase-0 migration before resealing",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required confirmation that historical rows must be retained unchanged",
    )
    args = parser.parse_args()

    if not args.confirm:
        parser.error("--confirm is required; resealing is an explicit governance action")

    if args.migrate:
        import migrate_phase0

        print(f"Migration summary: {migrate_phase0.migrate(engine)}")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == args.email).first()
        if not user or user.role != "senior_staff" or user.status != "active":
            print("ERROR: --email must identify an active senior_staff account.", file=sys.stderr)
            return 2

        entry = reseal_audit_chain(
            db,
            user_id=user.id,
            reason=args.reason,
            user_agent="LexGuard reseal CLI",
        )
        print(
            f"Resealed audit chain: segment={entry.segment} "
            f"entry_id={entry.id} current_hash={entry.current_hash}"
        )

        logs = (
            db.query(AuditLog)
            .order_by(
                AuditLog.segment.asc(),
                AuditLog.seq.asc().nullsfirst(),
                AuditLog.timestamp.asc(),
                AuditLog.id.asc(),
            )
            .all()
        )
        result = verify_audit_chain(logs)
        print(
            f"verification: active_segment={result.get('active_segment')} "
            f"is_valid={result.get('is_valid')} message={result.get('message')}"
        )
        for segment in result.get("segments", []):
            print(
                f"  segment {segment['segment']}: valid={segment['is_valid']} "
                f"records={segment['total_records']} broken_at={segment['broken_at_index']}"
            )
        return 0 if result.get("is_valid") else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
