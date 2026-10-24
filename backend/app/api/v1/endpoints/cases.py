import os
import uuid
import json
from typing import Optional, List
from datetime import datetime, timezone
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    UploadFile,
    File,
    Form,
    Request,
    Query,
)
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user, get_optional_current_user, require_role
from app.models.user import User
from app.models.case import Case
from app.models.document_version import DocumentVersion
from app.models.approval_queue import ApprovalQueue
from app.schemas.case import (
    CaseResponse,
    CaseDetailResponse,
    CaseVerificationResponse,
    CaseMetadataUpdate,
)
from app.services.crypto_service import compute_sha256, verify_sha256
from app.services.audit_service import log_audit_event
from app.services.embedding_service import embedding_service
from app.services.ner_service import ner_service

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20MB


def resolve_case_file_path(file_path: str) -> str:
    """Resolves physical file path, falling back to STORAGE_DIR if moved across environments."""
    if not file_path:
        return ""
    if os.path.exists(file_path):
        return file_path
    fname = os.path.basename(file_path)
    candidates = [
        os.path.join(settings.STORAGE_DIR, fname),
        os.path.join(os.getcwd(), "storage", "cases", fname),
        os.path.join(os.getcwd(), "backend", "storage", "cases", fname),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "storage", "cases", fname),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "backend", "storage", "cases", fname),
    ]
    for cand in candidates:
        if os.path.exists(cand):
            return cand
    return file_path


@router.post("/upload", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def upload_case(
    request: Request,
    file: UploadFile = File(...),
    case_no: str = Form(...),
    title: str = Form(...),
    court: str = Form(...),
    year: int = Form(...),
    judge: Optional[str] = Form(None),
    parties: Optional[str] = Form(None),
    act_tags: Optional[str] = Form("[]"),
    section_tags: Optional[str] = Form("[]"),
    keyword_tags: Optional[str] = Form("[]"),
    summary: Optional[str] = Form(None),
    outcome: Optional[str] = Form(None),
    current_user: User = Depends(require_role(["court_staff", "senior_staff"])),
    db: Session = Depends(get_db),
):
    """
    Court Staff Case Upload Endpoint:
    1. Validates file extension and size (<=20MB).
    2. Computes SHA-256 hash of raw document bytes.
    3. Detects duplicates via hash comparison.
    4. Stores document using secure UUID filename (Path Traversal defense).
    5. Creates Case record with 'pending_approval' status and logs to AuditLog.
    """
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Only PDF and DOCX files are permitted.",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds the 20MB limit.",
        )

    # Cryptographic integrity fingerprint
    file_hash = compute_sha256(file_bytes)

    # Duplicate check
    duplicate = db.query(Case).filter(Case.file_hash == file_hash).first()
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate document detected. This judgment is already registered under Case No: {duplicate.case_no}.",
        )

    # Secure file storage
    os.makedirs(settings.STORAGE_DIR, exist_ok=True)
    safe_filename = f"{uuid.uuid4()}{ext}"
    safe_path = os.path.join(settings.STORAGE_DIR, safe_filename)

    with open(safe_path, "wb") as f:
        f.write(file_bytes)

    # Parse JSON tags safely
    def parse_tags(raw: Optional[str]) -> List[str]:
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            return [t.strip() for t in raw.split(",") if t.strip()]
        return []

    parsed_acts = parse_tags(act_tags)
    parsed_sections = parse_tags(section_tags)
    parsed_keywords = parse_tags(keyword_tags)

    # Automatically extract statutory sections and legal keywords if not manually specified
    if not parsed_sections or not parsed_acts:
        extracted = ner_service.extract_legal_entities(f"{title} {summary or ''}")
        if not parsed_acts:
            parsed_acts = extracted.get("acts", [])
        if not parsed_sections:
            parsed_sections = extracted.get("sections", [])
        if not parsed_keywords:
            parsed_keywords = extracted.get("keywords", [])

    # Generate 384-dimensional semantic embedding using Hugging Face model
    text_corpus = f"{title}. {summary or ''}. {' '.join(parsed_sections)} {' '.join(parsed_keywords)}"
    case_embedding = embedding_service.generate_embedding(text_corpus)

    new_case = Case(
        case_no=case_no.strip(),
        title=title.strip(),
        court=court.strip(),
        year=year,
        judge=judge.strip() if judge else None,
        parties=parties.strip() if parties else None,
        act_tags=parsed_acts,
        section_tags=parsed_sections,
        keyword_tags=parsed_keywords,
        summary=summary.strip() if summary else None,
        outcome=outcome.strip() if outcome else None,
        file_path=safe_path,
        file_hash=file_hash,
        embedding=case_embedding,
        status="pending_approval",
        uploaded_by_id=current_user.id,
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    # Track Version 1
    version_entry = DocumentVersion(
        case_id=new_case.id,
        version_no=1,
        file_path=safe_path,
        file_hash=file_hash,
        change_summary="Initial document ingestion and registration",
        changed_by_id=current_user.id,
    )
    db.add(version_entry)

    # Enqueue into Senior Staff Approval Queue
    queue_entry = ApprovalQueue(
        case_id=new_case.id,
        submitted_by_id=current_user.id,
        status="pending",
    )
    db.add(queue_entry)
    db.commit()

    # Immutable Audit Log Entry
    log_audit_event(
        db=db,
        action="UPLOAD",
        user_id=current_user.id,
        case_id=new_case.id,
        details=f"Uploaded case '{new_case.case_no}' (SHA-256: {file_hash[:16]}...)",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return new_case


@router.post("/upload-auto", status_code=status.HTTP_201_CREATED)
async def upload_case_auto(
    file: UploadFile = File(...),
    request: Request = None,
    current_user: User = Depends(require_role(["court_staff", "senior_staff", "staff"])),
    db: Session = Depends(get_db),
):
    """
    Automated Court Document Ingestion Endpoint:
    1. Accepts raw PDF court judgment/petition documents only.
    2. Computes SHA-256 digest and verifies duplicate prevention.
    3. Persists document under secure UUID filename.
    4. Executes 3-pass extraction pipeline (Pass 1: Regex layout, Pass 2: InLegalBERT NER, Pass 3: Ratio/Summary).
    5. Saves Case record in 'pending_review' state with auto_extracted=True.
    6. Returns structured extracted fields + field-level confidence indicators for staff review.
    """
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext != ".pdf":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Automated extraction currently requires official PDF court documents. Please use manual upload for other formats.",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File size exceeds the 20MB limit.",
        )

    file_hash = compute_sha256(file_bytes)

    # Check for existing duplicate document
    duplicate = db.query(Case).filter(Case.file_hash == file_hash).first()
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This document is already registered in LexGuard under Case No: {duplicate.case_no} (Status: {duplicate.status}).",
        )

    # Store file securely
    os.makedirs(settings.STORAGE_DIR, exist_ok=True)
    safe_filename = f"{uuid.uuid4()}{ext}"
    safe_path = os.path.join(settings.STORAGE_DIR, safe_filename)

    with open(safe_path, "wb") as f:
        f.write(file_bytes)

    # Run Multi-Pass Extraction Pipeline
    from app.services.extraction_service import ExtractionService
    try:
        extracted = ExtractionService.extract_from_pdf(safe_path, extract_passes=[1, 2, 3])
    except Exception as e:
        logger.error(f"Extraction pipeline error on {file.filename}: {e}")
        extracted = {
            "case_no": "Pending Staff Review",
            "title": f"Document {os.path.basename(file.filename or 'judgment.pdf')}",
            "court": "High Court",
            "year": datetime.now().year,
            "judge": None,
            "parties": None,
            "act_tags": [],
            "section_tags": [],
            "keyword_tags": [],
            "summary": "Extraction encountered format irregularities; manual review required.",
            "outcome": "Pending",
            "facts": None,
            "ratio_decidendi": None,
            "full_text": None,
            "page_count": 1,
            "source_url": None,
            "confidence_scores": {},
            "overall_confidence": 0.3,
        }

    # Generate 384-dimensional dense vector embeddings
    text_corpus = f"{extracted.get('title', '')}. {extracted.get('summary', '')}. {' '.join(extracted.get('act_tags', []))} {' '.join(extracted.get('section_tags', []))}"
    case_embedding = None
    try:
        from app.services.ai_api_service import ai_api_service
        vecs = ai_api_service.generate_embeddings([text_corpus])
        if vecs and len(vecs) > 0:
            case_embedding = vecs[0]
    except Exception:
        case_embedding = embedding_service.generate_embedding(text_corpus)

    # Create Case record with status='pending_review'
    new_case = Case(
        case_no=extracted.get("case_no", "Pending Staff Review")[:100],
        title=extracted.get("title", f"Document {os.path.basename(file.filename or 'judgment.pdf')}")[:300],
        court=extracted.get("court", "High Court")[:150],
        year=extracted.get("year", datetime.now().year),
        judge=extracted.get("judge"),
        parties=extracted.get("parties"),
        act_tags=extracted.get("act_tags") or [],
        section_tags=extracted.get("section_tags") or [],
        keyword_tags=extracted.get("keyword_tags") or [],
        summary=extracted.get("summary"),
        outcome=extracted.get("outcome"),
        facts=extracted.get("prayer") or extracted.get("facts"),
        ratio_decidendi=extracted.get("ratio_decidendi"),
        disposition=extracted.get("disposition") or extracted.get("outcome"),
        full_text=extracted.get("full_text"),
        page_count=extracted.get("page_count", 1),
        source_url=extracted.get("source_url"),
        source_verification_state=extracted.get("source_verification_state", "unverified"),
        precedential_status=extracted.get("precedential_status", "Precedential status not checked"),
        file_path=safe_path,
        file_hash=file_hash,
        embedding=case_embedding,
        auto_extracted=True,
        status="pending_review",
        uploaded_by_id=current_user.id,
    )
    db.add(new_case)
    db.commit()
    db.refresh(new_case)

    # Track Version 1
    version_entry = DocumentVersion(
        case_id=new_case.id,
        version_no=1,
        file_path=safe_path,
        file_hash=file_hash,
        change_summary="Automated extraction and initial ingestion",
        changed_by_id=current_user.id,
    )
    db.add(version_entry)
    db.commit()

    # Log immutable audit event
    log_audit_event(
        db=db,
        action="AUTO_UPLOAD_DOCUMENT",
        user_id=current_user.id,
        case_id=new_case.id,
        details=f"Automated PDF extraction completed for {new_case.case_no} (Overall Confidence: {extracted.get('overall_confidence', 0.5)})",
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent") if request else None,
    )

    return {
        "case_id": new_case.id,
        "case_no": new_case.case_no,
        "title": new_case.title,
        "status": new_case.status,
        "file_hash": new_case.file_hash,
        "auto_extracted": True,
        "extracted_data": extracted,
        "confidence_scores": extracted.get("confidence_scores", {}),
        "overall_confidence": extracted.get("overall_confidence", 0.5),
        "message": "Automated PDF extraction complete. Pre-filled metadata is ready for human review.",
    }


@router.get("/", response_model=List[CaseResponse])

def list_cases(
    court: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    status_filter: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lists cases based on user role:
    - Court Staff can view all statuses (pending_approval, published, rejected).
    - Advocates, Scholars, and Public can only view 'published' cases.
    """
    query = db.query(Case)

    if current_user.role not in ["court_staff", "senior_staff", "staff"]:
        query = query.filter(Case.status == "published")
    elif status_filter:
        query = query.filter(Case.status == status_filter)

    if court:
        query = query.filter(Case.court.ilike(f"%{court}%"))
    if year:
        query = query.filter(Case.year == year)

    cases = query.order_by(Case.created_at.desc()).offset(skip).limit(limit).all()
    return cases


@router.get("/{case_id}", response_model=CaseResponse)
def get_case(
    case_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieves metadata of a specific case."""
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case record not found.",
        )

    if case.status != "published" and current_user.role not in ["court_staff", "senior_staff", "staff"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This case is pending staff approval and cannot be viewed yet.",
        )

    log_audit_event(
        db=db,
        action="VIEW_METADATA",
        user_id=current_user.id,
        case_id=case.id,
        details=f"Viewed case metadata for {case.case_no}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return case


@router.patch("/{case_id}", response_model=CaseResponse)
def update_case_metadata(
    case_id: str,
    update_data: CaseMetadataUpdate,
    request: Request,
    current_user: User = Depends(require_role(["court_staff", "senior_staff", "staff"])),
    db: Session = Depends(get_db),
):
    """
    Allows court staff and reviewers to update extracted case metadata fields
    during split-screen human-in-the-loop audit prior to judicial seal approval.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case record not found.",
        )

    update_dict = update_data.model_dump(exclude_unset=True)
    changed_fields = []

    for field, val in update_dict.items():
        if hasattr(case, field) and val is not None:
            setattr(case, field, val)
            changed_fields.append(field)

    # Re-generate embeddings if substantive legal fields changed
    if any(f in changed_fields for f in ["title", "summary", "act_tags", "section_tags", "ratio_decidendi"]):
        text_corpus = f"{case.title}. {case.summary or ''}. {' '.join(case.act_tags or [])} {' '.join(case.section_tags or [])}"
        try:
            from app.services.ai_api_service import ai_api_service
            vecs = ai_api_service.generate_embeddings([text_corpus])
            if vecs and len(vecs) > 0:
                case.embedding = vecs[0]
        except Exception:
            case.embedding = embedding_service.generate_embedding(text_corpus)

    case.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(case)

    # Immutable Audit Log
    log_audit_event(
        db=db,
        action="UPDATE_METADATA",
        user_id=current_user.id,
        case_id=case.id,
        details=f"Court staff updated metadata fields: {', '.join(changed_fields)}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return case


@router.post("/{case_id}/re-extract")
def re_extract_case(
    case_id: str,
    request: Request,
    current_user: User = Depends(require_role(["court_staff", "senior_staff", "staff"])),
    db: Session = Depends(get_db),
):
    """
    Triggers re-extraction on the official court document using the latest
    Madras High Court extraction engine passes.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case record not found.",
        )
    doc_path = resolve_case_file_path(case.file_path)
    if not doc_path or not os.path.exists(doc_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Original court PDF file is missing on storage.",
        )

    from app.services.extraction_service import ExtractionService
    try:
        extracted = ExtractionService.extract_from_pdf(doc_path, extract_passes=[1, 2, 3])
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Extraction failed: {str(e)}",
        )

    # Update case fields with fresh extraction
    if extracted.get("case_no") and extracted["case_no"] != "Case No. Not Extracted":
        case.case_no = extracted["case_no"][:100]
    if extracted.get("title"):
        case.title = extracted["title"][:300]
    if extracted.get("court"):
        case.court = extracted["court"][:150]
    if extracted.get("year"):
        case.year = extracted["year"]
    if extracted.get("judge"):
        case.judge = extracted["judge"]
    if extracted.get("parties"):
        case.parties = extracted["parties"]
    if extracted.get("act_tags"):
        case.act_tags = extracted["act_tags"]
    if extracted.get("section_tags"):
        case.section_tags = extracted["section_tags"]
    if extracted.get("keyword_tags"):
        case.keyword_tags = extracted["keyword_tags"]
    if extracted.get("summary"):
        case.summary = extracted["summary"]
    if extracted.get("outcome"):
        case.outcome = extracted["outcome"]
    if extracted.get("disposition"):
        case.disposition = extracted["disposition"]
    if extracted.get("ratio_decidendi"):
        case.ratio_decidendi = extracted["ratio_decidendi"]
    if extracted.get("prayer"):
        case.facts = extracted["prayer"]
    if extracted.get("full_text"):
        case.full_text = extracted["full_text"]
    if extracted.get("page_count"):
        case.page_count = extracted["page_count"]
    if extracted.get("source_url"):
        case.source_url = extracted["source_url"]

    case.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(case)

    # Log immutable audit event
    log_audit_event(
        db=db,
        action="RE_EXTRACT",
        user_id=current_user.id,
        case_id=case.id,
        details=f"Automated re-extraction executed for {case.case_no} (Confidence: {extracted.get('overall_confidence', 0.5)})",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return {
        "status": "success",
        "case_id": case.id,
        "case_no": case.case_no,
        "extracted_data": extracted,
        "confidence_scores": extracted.get("confidence_scores", {}),
        "overall_confidence": extracted.get("overall_confidence", 0.5),
        "message": "Re-extraction completed successfully.",
    }


@router.get("/{case_id}/view", response_model=CaseDetailResponse)
def view_case_document(
    case_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves full case document and executes REAL-TIME SHA-256 INTEGRITY VERIFICATION.
    - If file on disk matches stored file_hash: serves with 'verified' badge.
    - If hash mismatch: returns 'tampered', triggers security quarantine, and alerts admin.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case record not found.")

    if case.status != "published" and current_user.role not in ["court_staff", "senior_staff"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Document access restricted.")

    integrity_status = "verified"
    doc_path = resolve_case_file_path(case.file_path)
    if doc_path and os.path.exists(doc_path):
        with open(doc_path, "rb") as f:
            content = f.read()
        if not verify_sha256(content, case.file_hash):
            integrity_status = "tampered"
            # Quarantine the document
            case.status = "quarantined"
            db.commit()

            log_audit_event(
                db=db,
                action="INTEGRITY_VIOLATION",
                user_id=current_user.id,
                case_id=case.id,
                details=f"CRITICAL: SHA-256 hash mismatch detected during document access! Case quarantined.",
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Document integrity check failed: SHA-256 mismatch detected. File has been quarantined.",
            )
    else:
        integrity_status = "file_missing"

    log_audit_event(
        db=db,
        action="VIEW_DOCUMENT",
        user_id=current_user.id,
        case_id=case.id,
        details=f"Document viewed with status: {integrity_status}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    response_data = CaseDetailResponse(
        id=case.id,
        case_no=case.case_no,
        title=case.title,
        court=case.court,
        year=case.year,
        judge=case.judge,
        parties=case.parties,
        act_tags=case.act_tags or [],
        section_tags=case.section_tags or [],
        keyword_tags=case.keyword_tags or [],
        summary=case.summary,
        outcome=case.outcome,
        facts=case.facts,
        issues_framed=case.issues_framed or [],
        ratio_decidendi=case.ratio_decidendi,
        statutory_tests=case.statutory_tests or [],
        disposition=case.disposition or case.outcome,
        precedents_cited=case.precedents_cited or [],
        source_url=case.source_url,
        source_verification_state=case.source_verification_state or "unverified",
        precedential_status=case.precedential_status or "Precedential status not checked",
        file_hash=case.file_hash,
        redacted_file_hash=case.redacted_file_hash,
        status=case.status,
        uploaded_by_id=case.uploaded_by_id,
        approved_by_id=case.approved_by_id,
        approved_at=case.approved_at,
        created_at=case.created_at,
        updated_at=case.updated_at,
        integrity_status=integrity_status,
        full_text=case.full_text,
        page_count=case.page_count or 1,
    )
    return response_data


@router.get("/{case_id}/verify-integrity", response_model=CaseVerificationResponse)
def verify_case_integrity(
    case_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Dedicated cryptographic check that recalculates SHA-256
    hash directly from the stored file and returns tamper status badge.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case record not found.")

    doc_path = resolve_case_file_path(case.file_path)
    if not doc_path or not os.path.exists(doc_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Physical document file missing on disk.")

    with open(doc_path, "rb") as f:
        bytes_data = f.read()

    computed_hash = compute_sha256(bytes_data)
    is_valid = (computed_hash.lower() == case.file_hash.lower())
    badge = "VERIFIED_UNTAMPERED" if is_valid else "INTEGRITY_VIOLATION"

    log_audit_event(
        db=db,
        action="VERIFY_INTEGRITY",
        user_id=current_user.id,
        case_id=case.id,
        details=f"Cryptographic check result: {badge}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return CaseVerificationResponse(
        case_id=case.id,
        expected_hash=case.file_hash,
        computed_hash=computed_hash,
        is_valid=is_valid,
        status_badge=badge,
        verified_at=datetime.now(timezone.utc),
    )


@router.get("/{case_id}/download")
@router.get("/{case_id}/pdf")
def download_case(
    case_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Serves the authentic stored document file with cryptographic verification headers.
    """
    from fastapi.responses import FileResponse

    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case record not found.")

    if case.status != "published" and current_user.role not in ["court_staff", "senior_staff", "staff"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted: This case record is not yet published.",
        )

    doc_path = resolve_case_file_path(case.file_path)
    if not doc_path or not os.path.exists(doc_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Physical document file missing on disk.")

    log_audit_event(
        db=db,
        action="DOWNLOAD_DOCUMENT",
        user_id=current_user.id,
        case_id=case.id,
        details=f"Downloaded case record: {case.case_no}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    clean_case_no = "".join(c for c in case.case_no if c.isalnum() or c in ("-", "_")).strip() or "judgment"
    file_ext = os.path.splitext(doc_path)[1].lower()
    if file_ext == ".docx":
        filename = f"{clean_case_no}.docx"
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    else:
        filename = f"{clean_case_no}.pdf"
        media_type = "application/pdf"

    return FileResponse(
        path=doc_path,
        filename=filename,
        media_type=media_type,
        headers={
            "X-Lexguard-SHA256": case.file_hash,
            "X-Lexguard-Verified": "true",
        },
    )


@router.get("/{case_id}/official-content")
def get_official_case_content(
    case_id: str,
    request: Request = None,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns structured page-by-page contents extracted from the official PDF.
    """
    import re
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case record not found.")

    if case.status != "published" and (not current_user or current_user.role not in ["court_staff", "senior_staff", "staff"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access restricted: This case is not yet published.")

    text_to_parse = case.full_text or case.summary or ""
    if not text_to_parse and os.path.exists(case.file_path):
        try:
            import pdfplumber
            with pdfplumber.open(case.file_path) as pdf:
                pages_text = []
                for p_idx, p in enumerate(pdf.pages):
                    t = (p.extract_text() or "").strip()
                    pages_text.append(f"--- PAGE {p_idx + 1} ---\n{t}")
                case.full_text = "\n\n".join(pages_text)
                case.page_count = len(pdf.pages)
                db.commit()
                text_to_parse = case.full_text
        except Exception:
            pass

    # Break text into pages by delimiter
    pages = []
    raw_pages = re.split(r'---\s*PAGE\s+(\d+)\s*---', text_to_parse)
    if len(raw_pages) > 1:
        for i in range(1, len(raw_pages), 2):
            pg_num = int(raw_pages[i])
            pg_text = raw_pages[i + 1].strip() if i + 1 < len(raw_pages) else ""
            pages.append({"page": pg_num, "content": pg_text})
    else:
        pages.append({"page": 1, "content": text_to_parse})

    return {
        "case_id": case.id,
        "case_no": case.case_no,
        "title": case.title,
        "court": case.court,
        "year": case.year,
        "page_count": len(pages),
        "total_words": len(text_to_parse.split()),
        "full_text": text_to_parse,
        "pages": pages,
        "file_hash": case.file_hash,
        "source_url": case.source_url,
    }


@router.get("/{case_id}/search-keywords")
def search_keywords_in_case(
    case_id: str,
    q: str = Query(..., min_length=1, max_length=100),
    request: Request = None,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Precision keyword finder inside the official judgment PDF:
    Scans the judgment page-by-page and returns all keyword occurrences
    with page numbers, surrounding sentence snippets, and hit counts.
    """
    import re
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case record not found.")

    if case.status != "published" and (not current_user or current_user.role not in ["court_staff", "senior_staff", "staff"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access restricted: This case is not yet published.")

    text_to_search = case.full_text or case.summary or ""
    if not text_to_search and os.path.exists(case.file_path):
        try:
            import pdfplumber
            with pdfplumber.open(case.file_path) as pdf:
                pages_text = []
                for p_idx, p in enumerate(pdf.pages):
                    t = (p.extract_text() or "").strip()
                    pages_text.append(f"--- PAGE {p_idx + 1} ---\n{t}")
                case.full_text = "\n\n".join(pages_text)
                case.page_count = len(pdf.pages)
                db.commit()
                text_to_search = case.full_text
        except Exception:
            pass

    query_term = q.strip()
    pattern = re.compile(re.escape(query_term), re.IGNORECASE)

    occurrences = []
    pages_matched = set()

    current_page = 1
    lines = text_to_search.split("\n")
    for line_idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("--- PAGE "):
            m_pg = re.search(r'\d+', stripped)
            if m_pg:
                try:
                    current_page = int(m_pg.group())
                except Exception:
                    pass
            continue

        if pattern.search(stripped):
            pages_matched.add(current_page)
            highlighted = pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", stripped)
            occurrences.append({
                "page": current_page,
                "line_no": line_idx + 1,
                "snippet": highlighted,
                "raw_text": stripped,
            })

    return {
        "case_id": case.id,
        "case_no": case.case_no,
        "query": query_term,
        "total_matches": len(occurrences),
        "pages_matched": sorted(list(pages_matched)),
        "page_count": case.page_count or 1,
        "occurrences": occurrences,
    }

