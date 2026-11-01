"""Case-preflight run ledger.

One row per execution of the case-file preflight service. The table is written by
``app/services/case_preflight_service.py`` (web ``POST /system/case-preflight/run``
or ``backend/preflight_cases.py``) and read by the read-only system endpoints.

``report_json`` must work on both supported backends: ``JSONB`` on PostgreSQL and
``TEXT`` (JSON-encoded) on SQLite, because local evaluation runs entirely on SQLite.
"""
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.types import TypeDecorator

from app.core.database import Base


class JSONText(TypeDecorator):
    """JSONB on PostgreSQL, JSON-encoded TEXT on SQLite.

    Keeps the PostgreSQL column queryable with JSONB operators while remaining a
    plain TEXT column on SQLite, so the same model works in both environments.
    """

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB

            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            # psycopg2 adapts dict/list to JSONB natively.
            return value
        return json.dumps(value, default=str, sort_keys=True)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return {}


#: Terminal and transient states a preflight run can be in.
PREFLIGHT_STATUS_QUEUED = "QUEUED"
PREFLIGHT_STATUS_RUNNING = "RUNNING"
PREFLIGHT_STATUS_COMPLETED = "COMPLETED"
PREFLIGHT_STATUS_ISSUES = "COMPLETED_WITH_ISSUES"
PREFLIGHT_STATUS_REPAIRED = "REPAIRED"
PREFLIGHT_STATUS_POSTGRES_REQUIRED = "POSTGRES_REQUIRED"
PREFLIGHT_STATUS_BUSY = "BUSY"
PREFLIGHT_STATUS_FAILED = "FAILED"

PREFLIGHT_ACTIVE_STATUSES = (PREFLIGHT_STATUS_QUEUED, PREFLIGHT_STATUS_RUNNING)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CasePreflightRun(Base):
    __tablename__ = "case_preflight_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    started_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False, index=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    # Who/what asked for the run: web_init, web_manual, cli, test.
    trigger = Column(String(50), default="web_init", nullable=False)
    # verify | repair
    mode = Column(String(20), default="verify", nullable=False)
    # See PREFLIGHT_STATUS_* constants above.
    status = Column(String(40), default=PREFLIGHT_STATUS_QUEUED, nullable=False, index=True)

    total_cases = Column(Integer, default=0, nullable=False)
    verified_count = Column(Integer, default=0, nullable=False)
    missing_count = Column(Integer, default=0, nullable=False)
    mismatch_count = Column(Integer, default=0, nullable=False)
    duplicate_hash_count = Column(Integer, default=0, nullable=False)
    invalid_metadata_count = Column(Integer, default=0, nullable=False)

    # Structured report: counts, samples (case ids only), lock state, dialect.
    # Never stores absolute filesystem paths.
    report_json = Column(JSONText, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"<CasePreflightRun {self.id} status={self.status} mode={self.mode} "
            f"total={self.total_cases} verified={self.verified_count}>"
        )
