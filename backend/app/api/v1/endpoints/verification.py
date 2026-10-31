import os
import re
import hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.core.config import resolve_case_pdf_path
from app.core.database import get_db
from app.core.security import get_optional_current_user
from app.models.user import User
from app.models.case import Case
from app.models.audit_log import AuditLog
from app.schemas.verification import HashLookupResponse, HashLookupRequest, MatchedCaseSummary
from app.services.crypto_service import verify_sha256, verify_sha256_stream
from app.services.audit_service import log_audit_event, check_audit_entry
from app.core.rate_limit import rate_limit

router = APIRouter()

HEX_64_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")


def resolve_case_file_path(file_path: str) -> str:
    """Resolves physical file path portably, falling back across configured and standard storage locations."""
    if not file_path:
        return ""
    return str(resolve_case_pdf_path(file_path))


def _execute_hash_lookup(hash_str: str, request: Request, db: Session, current_user: User = None) -> HashLookupResponse:
    cleaned_hash = hash_str.strip().lower()
    if not HEX_64_PATTERN.match(cleaned_hash):
        raise HTTPException(
            status_code=422,
            detail="Invalid hash format: must be exactly 64 hexadecimal characters."
        )

    # Strictly search only published records to prevent leaking pending/rejected/quarantined documents
    matched_case = (
        db.query(Case)
        .filter(
            (Case.file_hash == cleaned_hash) | (Case.redacted_file_hash == cleaned_hash),
            Case.status == "published"
        )
        .first()
    )

    if not matched_case:
        return HashLookupResponse(
            matched=False,
            query_hash=cleaned_hash,
            message="No registered published document matches this SHA-256 digest in the Lexguard repository.",
            case=None,
            hash_label=None,
            audit_label=None,
            integrity_status="UNREGISTERED",
        )

    # Determine match type: Document Hash H_doc or Composite Judicial Seal Phi_case
    matched_type = "document_hash"
    if matched_case.redacted_file_hash and cleaned_hash == matched_case.redacted_file_hash.lower():
        matched_type = "composite_seal"

    # Compute Metadata Hash H_meta and Text Hash H_text for cryptographic verification
    meta_str = f"{matched_case.case_no}|{matched_case.court}|{matched_case.judge or ''}|{matched_case.disposition or ''}|{matched_case.year}"
    h_meta = hashlib.sha256(meta_str.encode("utf-8")).hexdigest()
    h_text = hashlib.sha256((matched_case.full_text or "").encode("utf-8")).hexdigest()

    # Latest audit entries for this case, each checked locally (see check_audit_entry).
    recent_entries = (
        db.query(AuditLog)
        .filter(AuditLog.case_id == matched_case.id)
        .order_by(AuditLog.timestamp.desc())
        .limit(10)
        .all()
    )
    audit_trail = []
    for e in recent_entries:
        checks = check_audit_entry(db, e)
        audit_trail.append({
            "id": e.id,
            "action": e.action,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "details": e.details,
            "current_hash": e.current_hash,
            "previous_hash": e.previous_log_hash,
            "recomputed_ok": checks["recomputed_ok"],
            "link_ok": checks["link_ok"],
        })
    latest_audit = recent_entries[0] if recent_entries else None
    audit_event_dict = None
    if latest_audit:
        audit_event_dict = {
            "id": latest_audit.id,
            "current_hash": latest_audit.current_hash,
            "previous_hash": latest_audit.previous_log_hash,
            "action": latest_audit.action,
            "timestamp": latest_audit.timestamp.isoformat() if latest_audit.timestamp else None,
        }
    # The label states exactly what was checked: the latest entries, locally, not the full chain.
    if not audit_trail:
        audit_label = "No audit entries recorded for this record"
    elif all(a["recomputed_ok"] and a["link_ok"] for a in audit_trail):
        audit_label = f"Latest {len(audit_trail)} audit entries verified (local check; full chain: see audit ledger)"
    else:
        audit_label = "Audit entry failed local verification"

    # Log lookup in audit trail with privacy preservation
    log_audit_event(
        db=db,
        action="DOCUMENT_VERIFY_LOOKUP",
        user_id=current_user.id if current_user else None,
        case_id=matched_case.id,
        details=f"SHA-256 lookup match for registered published case: {matched_case.case_no} (type={matched_type})",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    matched_summary = MatchedCaseSummary(
        id=matched_case.id,
        case_no=matched_case.case_no,
        title=matched_case.title,
        court=matched_case.court,
        year=matched_case.year,
        judge=matched_case.judge or "Hon'ble Court",
        disposition=matched_case.disposition or matched_case.outcome or "Allowed",
        act_tags=matched_case.act_tags or [],
        section_tags=matched_case.section_tags or [],
        source_url=matched_case.source_url,
        source_verification_state=matched_case.source_verification_state or "unverified",
        precedential_status=matched_case.precedential_status or "Precedential status not checked",
        expected_hash=matched_case.file_hash,
        file_hash=matched_case.file_hash,
        composite_seal=matched_case.redacted_file_hash,
        matched_hash_type=matched_type,
        h_meta=h_meta,
        h_text=h_text,
        approved_at=matched_case.approved_at,
        verified_at=datetime.now(timezone.utc),
    )

    return HashLookupResponse(
        matched=True,
        query_hash=cleaned_hash,
        message="Cryptographic match confirmed against a registered, published judicial document.",
        case=matched_summary,
        hash_label="SHA-256 matched",
        audit_label=audit_label,
        audit_event=audit_event_dict,
        audit_trail=audit_trail,
        # REGISTRY_MATCH: the digest equals the registered digest. The file on disk is NOT
        # re-read here; use /verification/documents/{id}/stream or /cases/{id}/verify-integrity.
        integrity_status="REGISTRY_MATCH",
    )


@router.get("/lookup/{sha256_hash}", response_model=HashLookupResponse, dependencies=[Depends(rate_limit(max_requests=60, window_seconds=60))])
def lookup_by_hash_path(
    sha256_hash: str,
    request: Request,
    current_user: User = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Publicly accessible cryptographic registry lookup.
    Queries repository by SHA-256 hash without requiring file upload.
    Returns matches only for published records.
    """
    return _execute_hash_lookup(sha256_hash, request, db, current_user)


@router.post("/lookup", response_model=HashLookupResponse, dependencies=[Depends(rate_limit(max_requests=60, window_seconds=60))])
def lookup_by_hash_body(
    payload: HashLookupRequest,
    request: Request,
    current_user: User = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Alternative POST endpoint accepting JSON payload with SHA-256 hash.
    Does not accept or upload files.
    """
    return _execute_hash_lookup(payload.sha256_hash, request, db, current_user)


@router.get("/documents/{case_id}/stream")
def stream_verified_document(
    case_id: str,
    request: Request,
    current_user: User = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Authorized document streaming endpoint that streams the actual registered judgment file
    after verifying it against the stored SHA-256 hash on disk.
    Never returns physical filesystem paths to clients.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Judgment record not found in repository."
        )

    is_staff = current_user and current_user.role in ["court_staff", "senior_staff", "staff"]
    if case.status != "published" and not is_staff:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted: document is not published."
        )

    # Determine file to serve
    # Redacted renditions are not implemented. redacted_file_hash holds the composite seal,
    # not a file digest, so it must never be used as an expected file hash.
    if current_user and current_user.role in ["scholar", "public"] and case.redacted_file_path:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Redacted renditions are not implemented for this record.",
        )
    file_path = case.file_path
    expected_hash = case.file_hash

    resolved_path = resolve_case_file_path(file_path)
    if not resolved_path or not os.path.exists(resolved_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Underlying document file is currently unavailable in repository storage."
        )

    # Verify bytes on disk via 64 KB chunked stream before serving
    if not verify_sha256_stream(resolved_path, expected_hash):
        # Quarantine corrupted file
        case.status = "quarantined"
        db.commit()
        log_audit_event(
            db=db,
            action="INTEGRITY_VIOLATION",
            user_id=current_user.id if current_user else None,
            case_id=case.id,
            details=f"SECURITY ALERT: SHA-256 mismatch detected while streaming document for {case.case_no}!",
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document integrity violation: file on disk does not match verified SHA-256 hash. Document quarantined."
        )

    # Log successful secure stream
    log_audit_event(
        db=db,
        action="DOCUMENT_STREAM",
        user_id=current_user.id if current_user else None,
        case_id=case.id,
        details=f"Securely streamed verified document for {case.case_no}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    clean_filename = os.path.basename(resolved_path)
    return FileResponse(
        path=resolved_path,
        media_type="application/pdf",
        filename=clean_filename,
        headers={
            "ETag": f'"{expected_hash}"',
            "Cache-Control": "private, max-age=3600",
            "X-Lexguard-SHA256": expected_hash,
            "X-Lexguard-Verified": "true",
        },
    )
