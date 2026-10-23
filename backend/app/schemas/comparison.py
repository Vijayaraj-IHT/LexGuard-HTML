from typing import Optional, List
from pydantic import BaseModel, Field


class CaseComparisonRequest(BaseModel):
    precedent_case_id: str = Field(..., description="Target registered precedent case ID (must be published)")
    case_title: Optional[str] = Field(default=None, max_length=300, description="Title of user case or petition")
    court_jurisdiction: Optional[str] = Field(default=None, max_length=150, description="Court or forum name")
    practice_area: Optional[str] = Field(default=None, max_length=100, description="Legal field, e.g., Criminal, Cyber Law, Arbitration")
    facts_summary: Optional[str] = Field(default=None, description="Concise factual matrix (not retained by server)")
    legal_issues: List[str] = Field(default_factory=list, description="Legal questions or issues framed")
    statutory_provisions: List[str] = Field(default_factory=list, description="Acts, Sections, or Articles invoked, e.g. Section 438 CrPC")
    remedy_sought: Optional[str] = Field(default=None, max_length=150, description="Specific prayer or remedy, e.g. Anticipatory Bail, Quashing")
    procedural_status: Optional[str] = Field(default=None, max_length=100, description="Procedural posture, e.g. Pre-arrest, Trial, Appeal")
    outcome: Optional[str] = Field(default=None, max_length=100, description="Outcome if decided, or 'Pending' if ongoing")


class DimensionComparisonResult(BaseModel):
    dimension_name: str
    user_value: Optional[str] = None
    precedent_value: Optional[str] = None
    match_state: str  # exact, partial, different, not_comparable
    weight_assigned: float
    effective_weight_percentage: float
    dimension_score: float  # 0 to 100
    explanation: str
    is_included_in_score: bool


class PrecedentSummary(BaseModel):
    case_id: str
    title: str
    case_no: str
    court: str
    year: int
    source_url: Optional[str] = None
    file_hash: str
    precedential_status: str


class CaseComparisonResponse(BaseModel):
    overall_score: float  # 0 to 100
    score_method: str = "lexguard-deterministic-v1.0"
    dimensions: List[DimensionComparisonResult]
    precedent: PrecedentSummary
    disclaimer: str = (
        "This comparison score is generated as a structured legal research aid based on transparent "
        "factual and statutory dimension matching. It does not predict judicial outcomes, constitute legal advice, "
        "or establish binding precedential effect."
    )


class MultiCaseComparisonRequest(BaseModel):
    precedent_case_ids: List[str] = Field(..., min_length=1, max_length=3, description="List of 1 to 3 published precedent IDs")
    case_title: Optional[str] = Field(default=None, max_length=300, description="Title of user case or petition")
    court_jurisdiction: Optional[str] = Field(default=None, max_length=150, description="Court or forum name")
    practice_area: Optional[str] = Field(default=None, max_length=100, description="Legal field, e.g., Criminal, Cyber Law, Commercial")
    facts_summary: Optional[str] = Field(default=None, description="Concise factual matrix (not retained by server)")
    legal_issues: List[str] = Field(default_factory=list, description="Legal questions or issues framed")
    statutory_provisions: List[str] = Field(default_factory=list, description="Acts, Sections, or Articles invoked, e.g. Section 438 CrPC")
    remedy_sought: Optional[str] = Field(default=None, max_length=150, description="Specific prayer or remedy, e.g. Anticipatory Bail, Quashing")
    procedural_status: Optional[str] = Field(default=None, max_length=100, description="Procedural posture, e.g. Pre-arrest, Trial, Appeal")
    outcome: Optional[str] = Field(default=None, max_length=100, description="Outcome if decided, or 'Pending' if ongoing")


class MultiCaseComparisonResponse(BaseModel):
    results: List[CaseComparisonResponse]
    best_match_id: Optional[str] = None
    best_match_score: float = 0.0
    cross_statutory_matrix: dict = Field(default_factory=dict)
    disclaimer: str = (
        "This comparison matrix is generated as a structured legal research aid based on transparent "
        "factual and statutory dimension matching. It does not predict judicial outcomes, constitute legal advice, "
        "or establish binding precedential effect."
    )

