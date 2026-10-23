import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(50), nullable=False, index=True)  # LOGIN, LOGOUT, SEARCH, VIEW, DOWNLOAD, UPLOAD, APPROVE, REJECT, VERIFY_INTEGRITY
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    # Cryptographic Hash Chaining (Blockchain-like immutable audit chain)
    previous_log_hash = Column(String(64), nullable=True)  # SHA-256 hash of previous block (null only on genesis)
    current_hash = Column(String(64), nullable=False)       # SHA-256 hash(previous_log_hash + record details)

    # Relationships
    user = relationship("User", back_populates="audit_logs")
    case = relationship("Case", back_populates="audit_logs")
