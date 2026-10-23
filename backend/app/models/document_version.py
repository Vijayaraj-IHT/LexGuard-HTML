import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id", ondelete="CASCADE"), nullable=False)
    version_no = Column(Integer, default=1, nullable=False)
    file_path = Column(String(500), nullable=False)
    file_hash = Column(String(64), nullable=False)  # SHA-256 hash of this specific version
    change_summary = Column(String(255), nullable=True)
    changed_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    changed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    case = relationship("Case", back_populates="versions")
    changed_by = relationship("User")
