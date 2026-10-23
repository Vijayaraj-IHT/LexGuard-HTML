import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Text, JSON, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from app.core.database import Base


# Support pgvector when on PostgreSQL with extension installed, fallback to JSON
try:
    from pgvector.sqlalchemy import Vector
    VectorColumnType = Vector(384)
except Exception:
    VectorColumnType = JSON


class Case(Base):
    __tablename__ = "cases"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_no = Column(String(100), index=True, nullable=False)
    title = Column(String(300), index=True, nullable=False)
    court = Column(String(150), index=True, nullable=False)
    year = Column(Integer, index=True, nullable=False)
    judge = Column(String(255), nullable=True)
    parties = Column(String(500), nullable=True)
    
    # Categorization and Metadata
    act_tags = Column(JSON, default=list, nullable=False)        # e.g. ["IPC", "CrPC", "NDPS Act"]
    section_tags = Column(JSON, default=list, nullable=False)    # e.g. ["Section 420 IPC", "Section 37 NDPS"]
    keyword_tags = Column(JSON, default=list, nullable=False)    # e.g. ["bail", "mens rea", "quashing"]
    summary = Column(Text, nullable=True)
    outcome = Column(String(100), nullable=True)                 # Allowed, Dismissed, Partly Allowed

    # Multi-Dimensional Judicial Rhetorical Structure
    facts = Column(Text, nullable=True)                          # Factual matrix of the dispute
    issues_framed = Column(JSON, default=list, nullable=False)   # Specific legal questions decided by the bench
    ratio_decidendi = Column(Text, nullable=True)                # Binding legal holding and precedent rule
    statutory_tests = Column(JSON, default=list, nullable=False) # Mandatory statutory conditions/prerequisites
    disposition = Column(String(100), nullable=True)             # Allowed, Dismissed, Quashed, Remanded
    precedents_cited = Column(JSON, default=list, nullable=False)# Prior landmark judgments relied upon

    # Official PDF Full Text & Metadata
    full_text = Column(Text, nullable=True)                      # Complete extracted text of official judgment PDF
    page_count = Column(Integer, default=1, nullable=True)       # Total pages in official PDF document

    # Source & Precedential Status Attributes
    source_url = Column(String(500), nullable=True)              # Official court repository URL if verified
    source_verification_state = Column(String(50), default="unverified", nullable=True) # verified, unverified
    precedential_status = Column(String(100), default="Precedential status not checked", nullable=True) # Good Law, Precedential status not checked

    # Cryptographic File Verification
    file_path = Column(String(500), nullable=False)
    file_hash = Column(String(64), index=True, nullable=False)  # SHA-256 hexadecimal digest
    redacted_file_path = Column(String(500), nullable=True)
    redacted_file_hash = Column(String(64), nullable=True)

    # Vector Embedding for Semantic Search
    embedding = Column(VectorColumnType, nullable=True)

    # Workflow & Approval Status
    status = Column(String(50), default="pending_approval", index=True, nullable=False)  # pending_review, pending_approval, published, rejected, quarantined
    auto_extracted = Column(Boolean, default=False, nullable=False)
    uploaded_by_id = Column(String(36), ForeignKey("users.id"), nullable=False)

    approved_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    uploader = relationship("User", foreign_keys=[uploaded_by_id], back_populates="uploaded_cases")
    approver = relationship("User", foreign_keys=[approved_by_id], back_populates="approved_cases")
    versions = relationship("DocumentVersion", back_populates="case", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="case")
    bookmarks = relationship("Bookmark", back_populates="case", cascade="all, delete-orphan")
    approval_entries = relationship("ApprovalQueue", back_populates="case", cascade="all, delete-orphan")
