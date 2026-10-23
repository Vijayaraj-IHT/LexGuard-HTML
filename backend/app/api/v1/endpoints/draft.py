from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import require_role, get_current_user
from app.models.user import User
from app.models.case import Case
from app.models.draft_session import DraftSession
from app.schemas.draft import (
    DraftAnalyzeRequest,
    DraftAnalyzeResponse,
    DraftSessionCreate,
    DraftSessionResponse,
    PrecedentCompareRequest,
    PrecedentCompareResponse,
)
from app.services.local_llm_service import local_llm_service
from app.services.claude_service import claude_service
from app.services.comparator import precedent_comparator
from app.services.audit_service import log_audit_event

router = APIRouter()


@router.post("/analyze", response_model=DraftAnalyzeResponse)
def analyze_draft_petition(
    draft_in: DraftAnalyzeRequest,
    request: Request,
    current_user: User = Depends(require_role(["advocate", "scholar", "court_staff", "senior_staff"])),
    db: Session = Depends(get_db),
):
    """
    AI-Powered Petition Draft Assistant:
    1. Analyzes user petition draft to identify present grounds using Hugging Face models (Qwen/Llama).
    2. Compares against verified precedents to find argument gaps.
    3. Suggests applicable statutory sections and grounded case citations.
    4. Enforces strict citation grounding to prevent legal hallucination.
    """
    # Fetch available published cases to ground citations
    published_cases = (
        db.query(Case)
        .filter(Case.status == "published")
        .order_by(Case.created_at.desc())
        .limit(10)
        .all()
    )

    cases_data = [
        {
            "id": c.id,
            "title": c.title,
            "court": c.court,
            "year": c.year,
            "section_tags": c.section_tags,
            "outcome": c.outcome,
            "summary": c.summary,
        }
        for c in published_cases
    ]

    analysis = local_llm_service.analyze_draft_gap(
        petition_text=draft_in.petition_text,
        available_cases=cases_data,
    )

    log_audit_event(
        db=db,
        action="DRAFT_ANALYZE",
        user_id=current_user.id,
        details="Executed AI petition gap analysis and precedent matching",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return DraftAnalyzeResponse(
        identified_grounds=analysis.get("identified_grounds", []),
        missing_arguments=analysis.get("missing_arguments", []),
        suggested_sections=analysis.get("suggested_sections", []),
        citation_suggestions=analysis.get("citation_suggestions", []),
    )


@router.post("/sessions", response_model=DraftSessionResponse, status_code=status.HTTP_201_CREATED)
def save_draft_session(
    session_in: DraftSessionCreate,
    current_user: User = Depends(require_role(["advocate", "scholar"])),
    db: Session = Depends(get_db),
):
    """Saves or starts a new draft working session for an advocate or scholar."""
    new_session = DraftSession(
        user_id=current_user.id,
        title=session_in.title,
        draft_text=session_in.draft_text,
        citations_inserted=[],
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return new_session


@router.get("/sessions", response_model=List[DraftSessionResponse])
def list_user_draft_sessions(
    current_user: User = Depends(require_role(["advocate", "scholar"])),
    db: Session = Depends(get_db),
):
    """Retrieves all saved petition drafting sessions belonging to the current user."""
    sessions = (
        db.query(DraftSession)
        .filter(DraftSession.user_id == current_user.id)
        .order_by(DraftSession.updated_at.desc())
        .all()
    )
    return sessions


@router.post("/compare-with-precedent", response_model=PrecedentCompareResponse)
def compare_with_precedent(
    compare_in: PrecedentCompareRequest,
    request: Request,
    current_user: User = Depends(require_role(["advocate", "scholar", "court_staff", "senior_staff", "staff"])),
    db: Session = Depends(get_db),
):
    """
    3-Layer Precision Precedent Comparator:
    Layer 1: Statutory Conditions Audit (Fulfilled vs Omitted conditions in draft)
    Layer 2: Ratio Decidendi Alignment Check
    Layer 3: Actionable Boilerplate Legal Suggestions
    """
    case = db.query(Case).filter(Case.id == compare_in.case_id).first()
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Precedent case with ID '{compare_in.case_id}' was not found in repository."
        )

    result = precedent_comparator.compare(draft_text=compare_in.draft_text, case=case)

    log_audit_event(
        db=db,
        action="PRECEDENT_COMPARISON",
        user_id=current_user.id,
        details=f"Audited draft against precedent: {case.title} ({case.case_no})",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return result
