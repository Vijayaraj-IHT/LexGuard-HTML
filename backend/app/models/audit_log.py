import uuid
from datetime import datetime, timezone
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import relationship
from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        # Legacy segment 0 is retained for disclosure and may contain the
        # historical forks found during the Phase-0 audit. Enforce link
        # uniqueness for every actively written segment (>= 1).
        Index(
            "uq_audit_segment_previous_hash",
            "segment",
            "previous_log_hash",
            unique=True,
            sqlite_where=text("segment >= 1"),
            postgresql_where=text("segment >= 1"),
        ),
        Index(
            "uq_audit_segment_current_hash",
            "segment",
            "current_hash",
            unique=True,
            sqlite_where=text("segment >= 1"),
            postgresql_where=text("segment >= 1"),
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # Audit rows are evidence: do not let a parent delete rewrite hashed
    # fields to NULL. Users/cases should be retired rather than hard-deleted.
    user_id = Column(String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True, index=True)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="RESTRICT"), nullable=True, index=True)
    action = Column(String(50), nullable=False, index=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    # Monotonic ordering and chain segmentation. ``seq`` removes timestamp-tie
    # ambiguity; ``segment`` allows an explicitly disclosed reseal without
    # rewriting a contaminated historical chain.
    seq = Column(BigInteger, nullable=True, unique=True, index=True)
    segment = Column(Integer, nullable=False, default=1, server_default="1", index=True)

    # Cryptographic hash chaining (tamper-evident, not tamper-proof).
    previous_log_hash = Column(String(64), nullable=True)
    current_hash = Column(String(64), nullable=False)

    # Relationships
    user = relationship("User", back_populates="audit_logs")
    case = relationship("Case", back_populates="audit_logs")
