import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class ApprovalQueue(Base):
    __tablename__ = "approval_queue"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True)
    submitted_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    reviewed_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    status = Column(String(50), default="pending", index=True, nullable=False)  # pending, approved, rejected
    review_note = Column(Text, nullable=True)
    submitted_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    case = relationship("Case", back_populates="approval_entries")
    submitted_by = relationship("User", foreign_keys=[submitted_by_id])
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])
