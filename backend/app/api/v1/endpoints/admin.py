from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import hashlib
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.core.security import get_password_hash, require_role
from app.models.user import User
from app.models.case import Case
from app.models.approval_queue import ApprovalQueue
from app.models.audit_log import AuditLog
from app.schemas.case import CaseResponse, CaseStatusUpdate
from app.schemas.audit import (
    AuditLogResponse,
    AuditChainVerificationResponse,
    AuditChainResealRequest,
    AuditChainResealResponse,
)
from app.schemas.user import AdminUserCreate, UserAdminUpdate, UserResponse
from app.services.crypto_service import verify_audit_chain
from app.services.audit_service import log_audit_event, reseal_audit_chain

router = APIRouter()

ALLOWED_CASE_TRANSITIONS = {
    "pending_review": {"pending_approval", "published", "rejected", "quarantined"},
    "pending_approval": {"published", "rejected", "quarantined"},
    "quarantined": {"pending_review", "pending_approval", "rejected"},
    "published": {"quarantined"},
    "rejected": {"pending_review", "pending_approval"},
}

QUEUE_STATUS_BY_CASE_STATUS = {
    "published": "approved",
    "rejected": "rejected",
    "pending_review": "pending",
    "pending_approval": "pending",
    "quarantined": "quarantined",
}


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
    current_user: User = Depends(require_role(["senior_staff"])),
    db: Session = Depends(get_db),
):
    """
    Senior-staff case review workflow.

    Segregation of duties is enforced: the uploader/submitter cannot decide
    their own submission. Only transitions in ``ALLOWED_CASE_TRANSITIONS``
    are accepted. Publication affixes the composite judicial seal to the
    dedicated ``judicial_seal`` column; ``redacted_file_hash`` remains
    exclusively the hash of redacted file bytes.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case record not found.")

    queue_entry = (
        db.query(ApprovalQueue)
        .filter(ApprovalQueue.case_id == case_id, ApprovalQueue.status == "pending")
        .order_by(ApprovalQueue.submitted_at.desc())
        .first()
    )

    submitter_ids = {str(case.uploaded_by_id)}
    if queue_entry:
        submitter_ids.add(str(queue_entry.submitted_by_id))
    if str(current_user.id) in submitter_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Segregation of duties: a case cannot be reviewed by its uploader or submitter.",
        )

    current_status = case.status
    target_status = review_in.status
    if target_status not in ALLOWED_CASE_TRANSITIONS.get(current_status, set()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Illegal case status transition: {current_status} -> {target_status}.",
        )

    decision_at = datetime.now(timezone.utc)
    case.status = target_status

    judicial_seal = None
    h_doc = case.file_hash or ""
    h_meta = None
    h_text = None

    if target_status == "published":
        case.approved_by_id = current_user.id
        case.approved_at = decision_at

        # 1. H_doc = raw PDF SHA-256
        # 2. H_meta = SHA-256(case_no | court | judge | disposition | year)
        meta_str = f"{case.case_no}|{case.court}|{case.judge or ''}|{case.disposition or ''}|{case.year}"
        h_meta = hashlib.sha256(meta_str.encode("utf-8")).hexdigest()
        # 3. H_text = SHA-256(full_text)
        h_text = hashlib.sha256((case.full_text or "").encode("utf-8")).hexdigest()
        # 4. Phi_case = SHA-256(H_doc || H_meta || H_text || T_approved)
        seal_payload = f"{h_doc}|{h_meta}|{h_text}|{decision_at.isoformat()}"
        judicial_seal = hashlib.sha256(seal_payload.encode("utf-8")).hexdigest()
        case.judicial_seal = judicial_seal
    elif target_status == "rejected":
        case.approved_by_id = current_user.id
        case.approved_at = decision_at
        case.judicial_seal = None
    elif target_status in {"pending_review", "pending_approval"}:
        case.approved_by_id = None
        case.approved_at = None
        case.judicial_seal = None
    elif target_status == "quarantined":
        # A quarantined record must not continue to present an approval seal
        # as a current integrity assurance. The seal remains in audit history.
        case.judicial_seal = None

    if queue_entry:
        queue_entry.status = QUEUE_STATUS_BY_CASE_STATUS[target_status]
        queue_entry.reviewed_by_id = current_user.id
        queue_entry.review_note = review_in.review_note
        queue_entry.reviewed_at = decision_at
    elif target_status in {"pending_review", "pending_approval"}:
        db.add(
            ApprovalQueue(
                case_id=case.id,
                submitted_by_id=case.uploaded_by_id,
                status="pending",
                review_note=review_in.review_note,
            )
        )

    db.commit()
    db.refresh(case)

    action_type = {
        "published": "APPROVE",
        "rejected": "REJECT",
        "quarantined": "QUARANTINE",
    }.get(target_status, "CASE_STATUS_CHANGE")

    if target_status == "published":
        details_str = (
            f"Case approved and judicial seal affixed. "
            f"Seal(Phi_case): {judicial_seal} "
            f"[H_doc: {h_doc[:8]}.., H_meta: {h_meta[:8]}.., H_text: {h_text[:8]}..]. "
            f"Note: {review_in.review_note or 'Verified'}"
        )
    else:
        details_str = (
            f"Case status changed from {current_status} to {target_status}. "
            f"Note: {review_in.review_note or 'None'}"
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
    """Retrieves tamper-evident audit log entries with filter and pagination."""
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if case_id:
        query = query.filter(AuditLog.case_id == case_id)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)

    logs = (
        query.order_by(
            AuditLog.segment.desc(),
            AuditLog.seq.desc().nullslast(),
            AuditLog.timestamp.desc(),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )
    return logs


@router.get("/verify-audit-chain", response_model=AuditChainVerificationResponse)
def verify_audit_ledger_chain(
    current_user: User = Depends(require_role(["court_staff", "senior_staff"])),
    db: Session = Depends(get_db),
):
    """
    Verify the hash-chained audit ledger segment by segment.

    ``is_valid`` refers to the active segment; archived segment results are
    returned in ``segments`` so a disclosed legacy reseal is not misreported
    as a pristine historical chain.
    """
    logs = (
        db.query(AuditLog)
        .order_by(
            AuditLog.segment.asc(),
            AuditLog.seq.asc().nullsfirst(),
            AuditLog.timestamp.asc(),
            AuditLog.id.asc(),
        )
        .all()
    )
    verification = verify_audit_chain(logs)

    return AuditChainVerificationResponse(
        is_valid=verification["is_valid"],
        total_records=verification["total_records"],
        active_segment=verification.get("active_segment"),
        active_records=verification.get("active_records", 0),
        segments=verification.get("segments", []),
        broken_at_index=verification.get("broken_at_index"),
        broken_at_id=str(verification.get("broken_at_id")) if verification.get("broken_at_id") else None,
        message=verification.get("message") or verification.get("reason", "Verification finished"),
    )


@router.post("/reseal-audit-chain", response_model=AuditChainResealResponse)
def reseal_audit_ledger_chain(
    payload: AuditChainResealRequest,
    request: Request,
    current_user: User = Depends(require_role(["senior_staff"])),
    db: Session = Depends(get_db),
):
    """
    Archive the current audit segment and start a new disclosed segment.

    This is a senior-staff remediation operation. It never rewrites or
    deletes historical audit rows.
    """
    try:
        entry = reseal_audit_chain(
            db,
            user_id=current_user.id,
            reason=payload.reason,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return AuditChainResealResponse(
        segment=entry.segment,
        entry_id=entry.id,
        current_hash=entry.current_hash,
        message=f"Audit chain resealed; active segment is now {entry.segment}. Historical rows were retained unchanged.",
    )


@router.get("/users", response_model=List[UserResponse])
def list_users(
    role: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(require_role(["senior_staff"])),
    db: Session = Depends(get_db),
):
    """List user accounts for senior-staff administration."""
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    if status_filter:
        query = query.filter(User.status == status_filter)
    return query.order_by(User.created_at.asc()).offset(skip).limit(limit).all()


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user_as_admin(
    user_in: AdminUserCreate,
    request: Request,
    current_user: User = Depends(require_role(["senior_staff"])),
    db: Session = Depends(get_db),
):
    """Provision an account, including staff roles that public registration forbids."""
    existing = db.query(User).filter(User.email == user_in.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email address already exists.",
        )

    user = User(
        name=user_in.name,
        email=user_in.email,
        password_hash=get_password_hash(user_in.password),
        role=user_in.role,
        status=user_in.status,
        credential_id=user_in.credential_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    log_audit_event(
        db=db,
        action="USER_CREATED",
        user_id=current_user.id,
        details=f"Provisioned user {user.email} with role {user.role} and status {user.status}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return user


@router.patch("/users/{user_id}", response_model=UserResponse)
def update_user_as_admin(
    user_id: str,
    user_in: UserAdminUpdate,
    request: Request,
    current_user: User = Depends(require_role(["senior_staff"])),
    db: Session = Depends(get_db),
):
    """Update a user's profile, role or account status with lockout guards."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    updates = user_in.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No user fields were supplied for update.",
        )

    proposed_role = updates.get("role", target.role)
    proposed_status = updates.get("status", target.status)

    if str(target.id) == str(current_user.id) and (
        proposed_role != "senior_staff" or proposed_status != "active"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Senior staff cannot demote, suspend or deactivate their own account.",
        )

    if target.role == "senior_staff" and (
        proposed_role != "senior_staff" or proposed_status != "active"
    ):
        active_seniors = (
            db.query(User)
            .filter(User.role == "senior_staff", User.status == "active")
            .count()
        )
        if active_seniors <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="At least one active senior-staff account must remain.",
            )

    for field, value in updates.items():
        setattr(target, field, value)

    db.commit()
    db.refresh(target)

    log_audit_event(
        db=db,
        action="USER_UPDATED",
        user_id=current_user.id,
        details=(
            f"Updated user {target.email}; changed fields: "
            f"{', '.join(sorted(updates.keys()))}"
        ),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return target


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
