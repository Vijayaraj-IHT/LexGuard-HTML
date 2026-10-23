import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime
from sqlalchemy.orm import relationship
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(150), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), default="public", index=True, nullable=False)  # court_staff, senior_staff, advocate, scholar, public
    status = Column(String(50), default="active", nullable=False)  # active, pending_verification, suspended
    credential_id = Column(String(100), nullable=True)  # Bar Council ID, Student/Faculty ID
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    uploaded_cases = relationship("Case", foreign_keys="Case.uploaded_by_id", back_populates="uploader")
    approved_cases = relationship("Case", foreign_keys="Case.approved_by_id", back_populates="approver")
    audit_logs = relationship("AuditLog", back_populates="user")
    bookmarks = relationship("Bookmark", back_populates="user")
    draft_sessions = relationship("DraftSession", back_populates="user")
