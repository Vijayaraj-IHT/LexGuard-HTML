from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.core.security import require_role
from app.models.user import User
from app.models.case import Case
from app.models.approval_queue import ApprovalQueue
from app.models.audit_log import AuditLog
from app.schemas.case import CaseResponse, CaseStatusUpdate
from app.schemas.audit import AuditLogResponse, AuditChainVerificationResponse
from app.services.crypto_service import verify_audit_chain
from app.services.audit_service import log_audit_event

router = APIRouter()


@router.get("/queue", response_model=List[Dict[str, Any]])
def get_approval_queue(
    current_user: User = Depends(require_role(["court_staff", "senior_staff"])),
    db: Session = Depends(get_db),
):
    """Retrieves all pending case uploads awaiting administrative review."""
    queue_entries = (
        db.query(ApprovalQueue)
        .filter(ApprovalQueue.status == "pending")
        .order_by(ApprovalQueue.submitted_at.asc())
        .all()
    )

    results = []
    for q in queue_entries:
        case = db.query(Case).filter(Case.id == q.case_id).first()
        submitter = db.query(User).filter(User.id == q.submitted_by_id).first()
        results.append({
            "queue_id": q.id,
            "case_id": q.case_id,
            "case_no": case.case_no if case else "Unknown",
            "title": case.title if case else "Unknown",
            "court": case.court if case else "Unknown",
            "year": case.year if case else None,
            "file_hash": case.file_hash if case else None,
            "submitted_by": submitter.name if submitter else "Staff",
            "submitted_at": q.submitted_at,
            "status": q.status,
        })
    return results


@router.post("/approve/{case_id}", response_model=CaseResponse)
def approve_or_reject_case(
    case_id: str,
    review_in: CaseStatusUpdate,
    request: Request,
    current_user: User = Depends(require_role(["senior_staff", "court_staff"])),
    db: Session = Depends(get_db),
):
    """
    Administrative Review Workflow:
    - Approves or rejects a submitted case.
    - Updates case status ('published' or 'rejected').
    - Updates approval queue state and review notes.
    - Logs the administrative decision into the hash-chained audit trail.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case record not found.")

    case.status = review_in.status
    case.approved_by_id = current_user.id
    case.approved_at = datetime.now(timezone.utc)

    # Update approval queue record
    queue_entry = (
        db.query(ApprovalQueue)
        .filter(ApprovalQueue.case_id == case_id, ApprovalQueue.status == "pending")
        .first()
    )
    if queue_entry:
        queue_entry.status = review_in.status
        queue_entry.reviewed_by_id = current_user.id
        queue_entry.review_note = review_in.review_note
        queue_entry.reviewed_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(case)

    # Immutable Audit Log & Composite Judicial Seal Phi_case Calculation
    action_type = "APPROVE" if review_in.status == "published" else "REJECT"
    details_str = f"Case status changed to {review_in.status}. Note: {review_in.review_note or 'None'}"

    if review_in.status == "published":
        import hashlib
        # 1. H_doc = raw PDF SHA-256
        h_doc = case.file_hash or ""
        # 2. H_meta = SHA-256(case_no | court | judge | disposition | year)
        meta_str = f"{case.case_no}|{case.court}|{case.judge or ''}|{case.disposition or ''}|{case.year}"
        h_meta = hashlib.sha256(meta_str.encode("utf-8")).hexdigest()
        # 3. H_text = SHA-256(full_text)
        h_text = hashlib.sha256((case.full_text or "").encode("utf-8")).hexdigest()
        # 4. T_approved = ISO timestamp
        t_approved = case.approved_at.isoformat()
        # 5. Composite Judicial Seal: Phi_case = SHA-256(H_doc || H_meta || H_text || T_approved)
        seal_payload = f"{h_doc}|{h_meta}|{h_text}|{t_approved}"
        judicial_seal = hashlib.sha256(seal_payload.encode("utf-8")).hexdigest()

        case.redacted_file_hash = judicial_seal
        db.commit()
        db.refresh(case)

        details_str = (
            f"Case approved and judicial seal affixed. "
            f"Seal(Phi_case): {judicial_seal} "
            f"[H_doc: {h_doc[:8]}.., H_meta: {h_meta[:8]}.., H_text: {h_text[:8]}..]. "
            f"Note: {review_in.review_note or 'Verified'}"
        )

    log_audit_event(
        db=db,
        action=action_type,
        user_id=current_user.id,
        case_id=case.id,
        details=details_str,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return case


@router.get("/audit-logs", response_model=List[AuditLogResponse])
def get_audit_logs(
    action: Optional[str] = Query(None),
    case_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_role(["court_staff", "senior_staff"])),
    db: Session = Depends(get_db),
):
    """Retrieves immutable audit log entries with filter and pagination."""
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if case_id:
        query = query.filter(AuditLog.case_id == case_id)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)

    logs = query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()
    return logs


@router.get("/verify-audit-chain", response_model=AuditChainVerificationResponse)
def verify_audit_ledger_chain(
    current_user: User = Depends(require_role(["court_staff", "senior_staff"])),
    db: Session = Depends(get_db),
):
    """
    Cryptographic Audit Trail Verification:
    Iterates through all chronological audit entries and verifies every
    SHA-256 hash link to ensure zero tampering, deletion, or modification of logs.
    """
    logs = db.query(AuditLog).order_by(AuditLog.timestamp.asc()).all()
    verification = verify_audit_chain(logs)

    return AuditChainVerificationResponse(
        is_valid=verification["is_valid"],
        total_records=verification["total_records"],
        broken_at_id=str(verification.get("broken_at_id")) if verification.get("broken_at_id") else None,
        message=verification.get("message") or verification.get("reason", "Verification finished"),
    )


@router.get("/analytics", response_model=Dict[str, Any])
def get_admin_analytics(
    current_user: User = Depends(require_role(["court_staff", "senior_staff"])),
    db: Session = Depends(get_db),
):
    """Calculates repository counts, user breakdowns, and audit statistics."""
    total_cases = db.query(Case).count()
    published_cases = db.query(Case).filter(Case.status == "published").count()
    pending_cases = db.query(Case).filter(Case.status == "pending_approval").count()
    quarantined_cases = db.query(Case).filter(Case.status == "quarantined").count()

    total_logs = db.query(AuditLog).count()
    recent_violations = db.query(AuditLog).filter(AuditLog.action == "INTEGRITY_VIOLATION").count()

    # User role distribution
    user_counts = (
        db.query(User.role, func.count(User.id))
        .group_by(User.role)
        .all()
    )
    users_by_role = {role: count for role, count in user_counts}

    return {
        "cases": {
            "total": total_cases,
            "published": published_cases,
            "pending_approval": pending_cases,
            "quarantined": quarantined_cases,
        },
        "audit": {
            "total_events": total_logs,
            "integrity_violations_detected": recent_violations,
        },
        "users": {
            "total": sum(users_by_role.values()),
            "by_role": users_by_role,
        },
    }
