from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class SearchFilters(BaseModel):
    court: Optional[str] = None
    bench: Optional[str] = None
    year_from: Optional[int] = Field(default=None, ge=1900)
    year_to: Optional[int] = Field(default=None, le=2100)
    act: Optional[str] = None
    outcome: Optional[str] = None
    disposition: Optional[str] = None


class SearchRequest(BaseModel):
    query: str = Field(default="", min_length=0, max_length=1000)
    filters: Optional[SearchFilters] = None
    limit: int = Field(default=10, ge=1, le=50)
    offset: int = Field(default=0, ge=0)


class SearchResultItem(BaseModel):
    id: str
    case_no: str
    title: str
    court: str
    year: int
    matched_sections: List[str] = []
    relevance_score: float
    outcome: Optional[str] = None
    disposition: Optional[str] = None
    judge: Optional[str] = None
    summary: Optional[str] = None
    ratio_decidendi: Optional[str] = None
    file_hash: str
    redacted_file_hash: Optional[str] = None
    act_tags: List[str] = []
    section_tags: List[str] = []
    keyword_tags: List[str] = []
    matched_snippets: List[str] = []
    matched_keywords: List[str] = []
    source_url: Optional[str] = None
    rrf_score: Optional[float] = None
    cnr_number: Optional[str] = None
    case_type: Optional[str] = None
    legal_domain: Optional[str] = None
    decision_date: Optional[str] = None
    precedential_status: Optional[str] = "Good Law"
    cited_by_count: Optional[int] = 0
    official_citation: Optional[str] = None
    search_mode: Optional[str] = None


class SearchResponse(BaseModel):
    total: int
    results: List[SearchResultItem]
    query_understanding: Optional[Dict[str, Any]] = None
