from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    case_id: Optional[str] = None
    action: str
    details: Optional[str] = None
    ip_address: Optional[str] = None
    timestamp: datetime
    previous_log_hash: Optional[str] = None
    current_hash: str

    model_config = ConfigDict(from_attributes=True)


class AuditChainVerificationResponse(BaseModel):
    is_valid: bool
    total_records: int
    broken_at_id: Optional[str] = None
    message: str
