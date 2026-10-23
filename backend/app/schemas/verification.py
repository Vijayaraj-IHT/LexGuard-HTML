from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class HashLookupRequest(BaseModel):
    sha256_hash: str = Field(..., pattern="^[a-fA-F0-9]{64}$", description="Lowercase 64-character SHA-256 hexadecimal hash")


class MatchedCaseSummary(BaseModel):
    id: str
    case_no: str
    title: str
    court: str
    year: int
    judge: Optional[str] = None
    disposition: Optional[str] = None
    act_tags: List[str] = Field(default_factory=list)
    section_tags: List[str] = Field(default_factory=list)
    source_url: Optional[str] = None
    source_verification_state: Optional[str] = "unverified"
    precedential_status: Optional[str] = "Precedential status not checked"
    expected_hash: str
    file_hash: Optional[str] = None
    composite_seal: Optional[str] = None
    matched_hash_type: Optional[str] = "document_hash"
    h_meta: Optional[str] = None
    h_text: Optional[str] = None
    approved_at: Optional[datetime] = None
    verified_at: datetime


class HashLookupResponse(BaseModel):
    matched: bool
    query_hash: str
    message: str
    case: Optional[MatchedCaseSummary] = None
    hash_label: Optional[str] = None
    audit_label: Optional[str] = None
    audit_event: Optional[Dict[str, Any]] = None
    integrity_status: Optional[str] = "UNREGISTERED"
