"""Idempotent Phase-0 database migration for LexGuard.

Adds the audit ordering/segmentation columns and the dedicated judicial-seal
column to an existing SQLite or PostgreSQL database.

Important: this migration never rewrites audit hashes and never reseals the
ledger. Restored legacy audit rows are labelled segment 0 and backfilled with
``seq`` in timestamp/id order. A senior operator must subsequently perform an
explicit, disclosed reseal (API or ``scripts/reseal_audit_chain.py``).
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, Optional

from sqlalchemy import create_engine, inspect, text


def _column_names(inspector, table_name: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table_name)}


def _enforce_restrict_audit_foreign_keys(conn, inspector) -> int:
    """Prevent user/case deletion from rewriting hashed audit FK fields."""
    parent_by_column = {"user_id": ("users", "id"), "case_id": ("cases", "id")}
    dialect = conn.dialect.name
    quote = conn.dialect.identifier_preparer.quote

    if dialect == "postgresql":
        changed = 0
        for foreign_key in inspector.get_foreign_keys("audit_logs"):
            constrained = foreign_key.get("constrained_columns") or []
            if len(constrained) != 1 or constrained[0] not in parent_by_column:
                continue
            on_delete = str((foreign_key.get("options") or {}).get("ondelete") or "")
            if on_delete.upper() == "RESTRICT":
                continue

            column = constrained[0]
            parent_table, parent_column = parent_by_column[column]
            constraint_name = foreign_key.get("name") or f"audit_logs_{column}_fkey"
            conn.execute(
                text(
                    f"ALTER TABLE audit_logs DROP CONSTRAINT {quote(constraint_name)}"
                )
            )
            conn.execute(
                text(
                    f"ALTER TABLE audit_logs ADD CONSTRAINT {quote(constraint_name)} "
                    f"FOREIGN KEY ({quote(column)}) REFERENCES {quote(parent_table)} "
                    f"({quote(parent_column)}) ON DELETE RESTRICT"
                )
            )
            changed += 1
        return changed

    if dialect == "sqlite":
        foreign_keys = conn.execute(
            text("PRAGMA foreign_key_list(audit_logs)")
        ).mappings().all()
        changed = sum(
            1
            for fk in foreign_keys
            if fk["from"] in parent_by_column
            and str(fk["on_delete"] or "").upper() != "RESTRICT"
        )
        if not changed:
            return 0

        columns = conn.execute(text("PRAGMA table_info(audit_logs)")).mappings().all()
        column_names = [column["name"] for column in columns]
        definitions = []
        for column in columns:
            definition = f"{quote(column['name'])} {column['type'] or 'TEXT'}"
            if column["pk"]:
                definition += " PRIMARY KEY"
            if column["notnull"]:
                definition += " NOT NULL"
            if column["dflt_value"] is not None:
                definition += f" DEFAULT {column['dflt_value']}"
            definitions.append(definition)
        definitions.extend(
            [
                "FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT",
                "FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE RESTRICT",
            ]
        )

        index_sql = [
            row[0]
            for row in conn.execute(
                text(
                    "SELECT sql FROM sqlite_master WHERE type = 'index' "
                    "AND tbl_name = 'audit_logs' AND sql IS NOT NULL"
                )
            ).fetchall()
        ]
        quoted_columns = ", ".join(quote(name) for name in column_names)

        conn.execute(text("PRAGMA defer_foreign_keys = ON"))
        conn.execute(
            text(f"CREATE TABLE audit_logs_phase0_new ({', '.join(definitions)})")
        )
        conn.execute(
            text(
                f"INSERT INTO audit_logs_phase0_new ({quoted_columns}) "
                f"SELECT {quoted_columns} FROM audit_logs"
            )
        )
        conn.execute(text("DROP TABLE audit_logs"))
        conn.execute(text("ALTER TABLE audit_logs_phase0_new RENAME TO audit_logs"))
        for statement in index_sql:
            conn.execute(text(statement))
        violations = conn.execute(text("PRAGMA foreign_key_check(audit_logs)")).fetchall()
        if violations:
            raise RuntimeError(
                "Audit-log foreign-key check failed after RESTRICT migration: "
                f"{len(violations)} violation(s)"
            )
        return changed

    return 0


def migrate(bind: Optional[Any] = None) -> Dict[str, Any]:
    """Apply the Phase-0 schema/data backfill and return a summary."""
    if bind is None:
        from app.core.database import engine as bind

    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    summary: Dict[str, Any] = {
        "audit_logs_present": "audit_logs" in tables,
        "cases_present": "cases" in tables,
        "audit_seq_backfilled": 0,
        "audit_segment_backfilled": 0,
        "judicial_seals_moved": 0,
        "audit_foreign_keys_restricted": 0,
        "columns_added": [],
    }

    with bind.begin() as conn:
        if "audit_logs" in tables:
            columns = _column_names(inspector, "audit_logs")

            if "seq" not in columns:
                conn.execute(text("ALTER TABLE audit_logs ADD COLUMN seq BIGINT"))
                summary["columns_added"].append("audit_logs.seq")
            if "segment" not in columns:
                conn.execute(text("ALTER TABLE audit_logs ADD COLUMN segment INTEGER"))
                summary["columns_added"].append("audit_logs.segment")

            # Anything already present before Phase 0 is legacy segment 0.
            # This preserves and discloses the historical chain, including
            # forks, rather than pretending it is a valid active segment.
            result = conn.execute(
                text("UPDATE audit_logs SET segment = 0 WHERE segment IS NULL")
            )
            summary["audit_segment_backfilled"] = int(result.rowcount or 0)

            max_seq = conn.execute(text("SELECT MAX(seq) FROM audit_logs")).scalar()
            next_seq = int(max_seq or 0) + 1
            missing_seq_ids = conn.execute(
                text(
                    'SELECT id FROM audit_logs WHERE seq IS NULL '
                    'ORDER BY "timestamp" ASC, id ASC'
                )
            ).fetchall()
            for (log_id,) in missing_seq_ids:
                conn.execute(
                    text("UPDATE audit_logs SET seq = :seq WHERE id = :id"),
                    {"seq": next_seq, "id": log_id},
                )
                next_seq += 1
            summary["audit_seq_backfilled"] = len(missing_seq_ids)
            summary["audit_foreign_keys_restricted"] = (
                _enforce_restrict_audit_foreign_keys(conn, inspector)
            )

            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_audit_logs_seq "
                    "ON audit_logs (seq) WHERE seq IS NOT NULL"
                )
            )
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "uq_audit_segment_previous_hash "
                    "ON audit_logs (segment, previous_log_hash) "
                    "WHERE segment >= 1"
                )
            )
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS "
                    "uq_audit_segment_current_hash "
                    "ON audit_logs (segment, current_hash) "
                    "WHERE segment >= 1"
                )
            )

        if "cases" in tables:
            columns = _column_names(inspector, "cases")
            if "judicial_seal" not in columns:
                conn.execute(text("ALTER TABLE cases ADD COLUMN judicial_seal VARCHAR(64)"))
                summary["columns_added"].append("cases.judicial_seal")

            if {"redacted_file_hash", "redacted_file_path"}.issubset(columns):
                # Older approval code stored Phi_case in redacted_file_hash.
                # It is a seal, not a redacted-file digest, when no redacted
                # file exists. Move only that unambiguous legacy shape.
                result = conn.execute(
                    text(
                        "UPDATE cases "
                        "SET judicial_seal = redacted_file_hash, "
                        "redacted_file_hash = NULL "
                        "WHERE judicial_seal IS NULL "
                        "AND redacted_file_hash IS NOT NULL "
                        "AND (redacted_file_path IS NULL OR redacted_file_path = '')"
                    )
                )
                summary["judicial_seals_moved"] = int(result.rowcount or 0)

            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_cases_judicial_seal "
                    "ON cases (judicial_seal)"
                )
            )

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=None,
        help="Optional SQLAlchemy database URL. Defaults to app DATABASE_URL.",
    )
    args = parser.parse_args()

    bind = create_engine(args.database_url) if args.database_url else None
    summary = migrate(bind)
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(
        "Phase-0 migration complete. No audit hashes were rewritten and no "
        "reseal was performed automatically."
    )


if __name__ == "__main__":
    main()
