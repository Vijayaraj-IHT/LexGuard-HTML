"""
Statute and Codified Bare Acts Model for LexGuard.
Stores official legislative sections for the Top 12 Fundamental Indian Statutes.
"""
import uuid
from sqlalchemy import Column, String, Text, Integer
from app.core.database import Base


class StatuteSection(Base):
    __tablename__ = "statute_sections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    act_code = Column(String(20), index=True, nullable=False) # e.g. CRPC, IPC, NI_ACT, CONST
    act_title = Column(String(150), nullable=False)          # e.g. Code of Criminal Procedure, 1973
    section_no = Column(String(20), index=True, nullable=False) # e.g. 482, 439, 138, 226
    section_title = Column(String(200), nullable=False)       # e.g. Saving of inherent powers of High Court
    bare_text = Column(Text, nullable=False)                 # Official legislative statutory text
    explanation = Column(Text, nullable=True)                # Plain-English judicial commentary
    case_count = Column(Integer, default=0, nullable=False)  # Dynamic count of cases interpreting this section
