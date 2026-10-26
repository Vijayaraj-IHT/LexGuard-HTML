from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class AuditLogResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    case_id: Optional[str] = None
    action: str
    details: Optional[str] = None
    ip_address: Optional[str] = None
    timestamp: datetime
    seq: Optional[int] = None
    segment: Optional[int] = None
    previous_log_hash: Optional[str] = None
    current_hash: str

    model_config = ConfigDict(from_attributes=True)


class AuditChainVerificationResponse(BaseModel):
    is_valid: bool
    total_records: int
    active_segment: Optional[int] = None
    active_records: int = 0
    segments: List[Dict[str, Any]] = Field(default_factory=list)
    broken_at_index: Optional[int] = None
    broken_at_id: Optional[str] = None
    message: str


class AuditChainResealRequest(BaseModel):
    reason: str = Field(..., min_length=10, max_length=1000)


class AuditChainResealResponse(BaseModel):
    segment: int
    entry_id: str
    current_hash: str
    message: str
