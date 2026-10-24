from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class StatutoryTest(BaseModel):
    test: str = Field(..., description="Short identifier for the legal test")
    mandatory: bool = Field(default=True, description="Whether the requirement is mandatory")
    condition: str = Field(..., description="Full text of the legal condition")
    section_ref: Optional[str] = Field(default=None, description="Statutory citation")


class PrecedentCited(BaseModel):
    title: str
    year: Optional[int] = None
    citation: Optional[str] = None
    court: Optional[str] = None


class CaseBase(BaseModel):
    case_no: str = Field(..., max_length=255)
    cnr_number: Optional[str] = Field(default=None, max_length=50)
    case_type: Optional[str] = Field(default="Judgment", max_length=100)
    title: str = Field(..., max_length=500)
    court: str = Field(..., max_length=255)
    year: int = Field(..., ge=1800, le=2100)
    decision_date: Optional[Any] = None
    judge: Optional[str] = Field(default=None, max_length=500)
    bench_type: Optional[str] = Field(default="Single Bench", max_length=100)
    parties: Optional[str] = Field(default=None, max_length=1000)
    petitioner: Optional[str] = Field(default=None, max_length=500)
    respondent: Optional[str] = Field(default=None, max_length=500)
    petitioner_counsel: Optional[str] = Field(default=None, max_length=500)
    respondent_counsel: Optional[str] = Field(default=None, max_length=500)
    legal_domain: Optional[str] = Field(default="General", max_length=100)
    act_tags: List[str] = Field(default_factory=list)
    section_tags: List[str] = Field(default_factory=list)
    keyword_tags: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    layman_summary: Optional[str] = None
    outcome: Optional[str] = Field(default=None, max_length=500)
    facts: Optional[str] = None
    issues_framed: List[str] = Field(default_factory=list)
    ratio_decidendi: Optional[str] = None
    statutory_tests: List[Any] = Field(default_factory=list)
    disposition: Optional[str] = Field(default=None, max_length=1000)
    precedents_cited: List[Any] = Field(default_factory=list)
    cited_by_count: Optional[int] = 0
    official_citation: Optional[str] = Field(default=None, max_length=200)
    full_text: Optional[str] = None
    page_count: Optional[int] = 1
    source_url: Optional[str] = None
    source_verification_state: Optional[str] = "unverified"
    precedential_status: Optional[str] = "Good Law"
    auto_extracted: bool = False



class EnrichedCaseDetailResponse(BaseModel):
    id: str
    case_no: str
    title: str
    court: str
    year: int
    judge: Optional[str] = None
    parties: Optional[str] = None
    act_tags: List[str] = []
    section_tags: List[str] = []
    keyword_tags: List[str] = []
    summary: Optional[str] = None
    facts: Optional[str] = None
    issues_framed: List[str] = []
    ratio_decidendi: Optional[str] = None
    statutory_tests: List[Dict[str, Any]] = []
    disposition: Optional[str] = None
    precedents_cited: List[Dict[str, Any]] = []
    full_text: Optional[str] = None
    page_count: Optional[int] = 1
    file_hash: str
    status: str

    model_config = ConfigDict(from_attributes=True)


class CaseCreate(CaseBase):
    pass


class CaseResponse(CaseBase):
    id: str
    file_hash: str
    redacted_file_hash: Optional[str] = None
    status: str
    uploaded_by_id: str
    approved_by_id: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CaseDetailResponse(CaseResponse):
    integrity_status: str = "verified"  # verified, tampered, pending_check


class CaseVerificationResponse(BaseModel):
    case_id: str
    expected_hash: str
    computed_hash: str
    is_valid: bool
    status_badge: str  # "VERIFIED_UNTAMPERED" or "INTEGRITY_VIOLATION"
    verified_at: datetime


class CaseStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(pending_review|pending_approval|published|rejected|quarantined)$")
    review_note: Optional[str] = Field(default=None, max_length=1000)


class CaseMetadataUpdate(BaseModel):
    case_no: Optional[str] = None
    title: Optional[str] = None
    court: Optional[str] = None
    year: Optional[int] = None
    judge: Optional[str] = None
    parties: Optional[str] = None
    disposition: Optional[str] = None
    outcome: Optional[str] = None
    precedential_status: Optional[str] = None
    facts: Optional[str] = None
    ratio_decidendi: Optional[str] = None
    summary: Optional[str] = None
    act_tags: Optional[List[str]] = None
    section_tags: Optional[List[str]] = None
    keyword_tags: Optional[List[str]] = None
    source_url: Optional[str] = None


