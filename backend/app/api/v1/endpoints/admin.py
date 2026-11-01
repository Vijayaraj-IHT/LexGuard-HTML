import os
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
from app.services.crypto_service import (
    verify_audit_chain,
    compute_h_meta,
    compute_h_text,
    compute_judicial_seal,
)
import hmac
from app.services.audit_service import log_audit_event

router = APIRouter()


def not_case_file_present(case: Case) -> bool:
    """True when the record points at no readable file (legacy import / moved storage)."""
    from app.core.config import resolve_case_pdf_path
    try:
        path = str(resolve_case_pdf_path(case.file_path)) if case.file_path else ""
    except Exception:
        return True
    return not path or not os.path.exists(path)


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

    queue_entry = (
        db.query(ApprovalQueue)
        .filter(ApprovalQueue.case_id == case_id, ApprovalQueue.status == "pending")
        .first()
    )

    # ---- Maker-checker -----------------------------------------------------
    # The maker is whoever uploaded the bytes OR whoever queued it for review;
    # checking only uploaded_by_id would let a reviewer queue a record and then
    # approve it themselves.
    if review_in.status == "published":
        maker_ids = {str(case.uploaded_by_id) if case.uploaded_by_id else None}
        if queue_entry and queue_entry.submitted_by_id:
            maker_ids.add(str(queue_entry.submitted_by_id))
        maker_ids.discard(None)
        if str(current_user.id) in maker_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Maker-checker violation: the uploader cannot publish their own submission. "
                       "A second staff member must approve it.",
            )
        if case.approved_by_id and str(case.approved_by_id) == str(current_user.id) \
                and case.status == "published":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Maker-checker violation: this record is already published and cannot be "
                       "re-approved by the same reviewer.",
            )
        # A quarantined record whose stored bytes are present AND still wrong must not
        # be published: the seal would be affixed to bytes nobody re-checked.
        # A record with no readable file (legacy import, Windows-era path) is not
        # blocked here — there are no bytes to contradict the record; the absence is
        # recorded in the audit entry instead of silently passing as "verified".
        quarantine_bytes_ok: Optional[bool] = None
        if case.status == "quarantined":
            from app.services.crypto_service import verify_sha256_stream
            from app.core.config import resolve_case_pdf_path
            path = str(resolve_case_pdf_path(case.file_path)) if case.file_path else ""
            if not path or not os.path.exists(path):
                quarantine_bytes_ok = None
            else:
                quarantine_bytes_ok = verify_sha256_stream(path, case.file_hash or "")
                if not quarantine_bytes_ok:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Quarantined record: the stored file still fails SHA-256 verification. "
                               "Restore an authentic copy before publishing.",
                    )

    case.status = review_in.status
    case.approved_by_id = current_user.id
    case.approved_at = datetime.now(timezone.utc)

    # Update approval queue record
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
        # Seal formula lives in crypto_service (frozen; see compute_judicial_seal).
        h_doc = case.file_hash or ""                                   # H_doc
        h_meta = compute_h_meta(case.case_no, case.court, case.judge, case.disposition, case.year)
        h_text = compute_h_text(case.full_text)                        # H_text
        t_approved = case.approved_at.isoformat()                      # T_approved
        judicial_seal = compute_judicial_seal(h_doc, h_meta, h_text, t_approved)

        # NOTE: this column stores the composite seal Phi_case, NOT a redacted-file digest.
        case.redacted_file_hash = judicial_seal
        db.commit()
        db.refresh(case)

        details_str = (
            f"Case approved and judicial seal affixed. "
            f"Seal(Phi_case): {judicial_seal} "
            f"[H_doc: {h_doc[:8]}.., H_meta: {h_meta[:8]}.., H_text: {h_text[:8]}..]. "
            f"Note: {review_in.review_note or 'Verified'}"
        )

    if review_in.status == "published" and case.status != "quarantined" and not_case_file_present(case):
        details_str += " [UNVERIFIED: stored file not present at approval; seal covers the registered digest only]"

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


@router.get("/cases/{case_id}/seal-check")
def check_judicial_seal(
    case_id: str,
    current_user: User = Depends(require_role(["court_staff", "senior_staff"])),
    db: Session = Depends(get_db),
):
    """
    Recomputes the composite judicial seal Phi_case from the record's current fields
    and reports whether it still matches the stored seal.

    A seal that no longer reproduces means a sealed field (file hash, metadata,
    full text or approval time) changed after approval, or the seal was written
    outside the approval path (no APPROVE audit entry).
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case record not found.")

    approve_log_found = (
        db.query(AuditLog)
        .filter(AuditLog.case_id == case.id, AuditLog.action == "APPROVE")
        .first()
        is not None
    )
    stored = case.redacted_file_hash  # holds the composite seal (see approve_or_reject_case)
    if not stored or not case.approved_at:
        return {
            "case_id": case.id,
            "sealed": bool(stored),
            "reproducible": False,
            "approve_log_found": approve_log_found,
            "reason": "No seal stored." if not stored else "Seal stored but approval time is missing.",
        }

    h_doc = case.file_hash or ""
    h_meta = compute_h_meta(case.case_no, case.court, case.judge, case.disposition, case.year)
    h_text = compute_h_text(case.full_text)
    t_approved = case.approved_at.isoformat()
    recomputed = compute_judicial_seal(h_doc, h_meta, h_text, t_approved)
    reproducible = hmac.compare_digest(recomputed, stored)

    reason = None
    if not reproducible:
        reason = "Sealed fields changed after approval, or the seal was not written by the approval path."
        if not approve_log_found:
            reason += " No APPROVE audit entry exists for this case."

    return {
        "case_id": case.id,
        "sealed": True,
        "reproducible": reproducible,
        "approve_log_found": approve_log_found,
        "stored_seal": stored,
        "recomputed_seal": recomputed,
        "components": {"H_doc": h_doc, "H_meta": h_meta, "H_text": h_text, "T_approved": t_approved},
        "reason": reason,
    }


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

    from app.services.audit_service import LEDGER_ORDER_DESC
    logs = query.order_by(*LEDGER_ORDER_DESC).offset(skip).limit(limit).all()
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
    # Chain order (timestamp asc, id tiebreak) — shared with the writer, so the
    # verification walks the ledger in exactly the order it was linked in.
    from app.services.audit_service import LEDGER_ORDER_ASC
    logs = db.query(AuditLog).order_by(*LEDGER_ORDER_ASC).all()
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
