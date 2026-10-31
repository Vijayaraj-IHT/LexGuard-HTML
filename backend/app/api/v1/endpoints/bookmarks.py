from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.case import Case
from app.models.bookmark import Bookmark
from app.services.audit_service import log_audit_event

router = APIRouter()


class BookmarkCreate(BaseModel):
    case_id: str
    binder_name: Optional[str] = "General Research"
    notes: Optional[str] = None


class BookmarkUpdate(BaseModel):
    binder_name: Optional[str] = None
    notes: Optional[str] = None


class BookmarkCaseBrief(BaseModel):
    id: str
    case_no: str
    title: str
    court: str
    year: int
    outcome: Optional[str] = None
    disposition: Optional[str] = None
    judge: Optional[str] = None
    legal_domain: Optional[str] = None
    act_tags: List[str] = []
    section_tags: List[str] = []
    summary: Optional[str] = None
    ratio_decidendi: Optional[str] = None
    precedential_status: Optional[str] = "Good Law"
    official_citation: Optional[str] = None
    file_hash: str

    model_config = ConfigDict(from_attributes=True)


class BookmarkResponse(BaseModel):
    id: str
    user_id: str
    case_id: str
    binder_name: Optional[str] = "General Research"
    notes: Optional[str] = None
    created_at: datetime
    case: Optional[BookmarkCaseBrief] = None

    model_config = ConfigDict(from_attributes=True)


@router.get("/", response_model=List[BookmarkResponse])
def get_user_bookmarks(
    request: Request,
    binder: Optional[str] = Query(None, description="Filter by research binder name"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves all saved bookmarks for the current authenticated user,
    optionally filtered by research binder.
    """
    query = db.query(Bookmark).filter(Bookmark.user_id == current_user.id)
    if binder and binder.strip() and binder.lower() != "all":
        query = query.filter(Bookmark.binder_name.ilike(binder.strip()))

    bookmarks = query.order_by(Bookmark.created_at.desc()).all()
    return bookmarks


@router.get("/binders")
def list_user_binders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns the user's research binders with bookmark counts.
    """
    counts = (
        db.query(
            func.coalesce(Bookmark.binder_name, "General Research").label("binder_name"),
            func.count(Bookmark.id).label("count")
        )
        .filter(Bookmark.user_id == current_user.id)
        .group_by("binder_name")
        .all()
    )

    binders = [{"binder_name": row[0], "count": row[1]} for row in counts]
    if not binders:
        binders = [{"binder_name": "General Research", "count": 0}]
    return binders


@router.post("/", response_model=BookmarkResponse, status_code=status.HTTP_201_CREATED)
def create_bookmark(
    bookmark_in: BookmarkCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Creates or updates a bookmark in a specified research binder.
    """
    target_case = db.query(Case).filter(Case.id == bookmark_in.case_id).first()
    if not target_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case record not found in repository.",
        )

    binder = (bookmark_in.binder_name or "General Research").strip()

    # Check if already bookmarked
    existing = (
        db.query(Bookmark)
        .filter(Bookmark.user_id == current_user.id, Bookmark.case_id == bookmark_in.case_id)
        .first()
    )
    if existing:
        if bookmark_in.notes:
            existing.notes = bookmark_in.notes
        if bookmark_in.binder_name:
            existing.binder_name = binder
        db.commit()
        db.refresh(existing)
        return existing

    new_bm = Bookmark(
        user_id=current_user.id,
        case_id=bookmark_in.case_id,
        binder_name=binder,
        notes=bookmark_in.notes,
    )
    db.add(new_bm)
    db.commit()
    db.refresh(new_bm)

    log_audit_event(
        db=db,
        action="BOOKMARK_CREATE",
        user_id=current_user.id,
        case_id=target_case.id,
        details=f"Saved case to binder '{binder}': {target_case.case_no}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return new_bm


@router.put("/{bookmark_id}", response_model=BookmarkResponse)
def update_bookmark(
    bookmark_id: str,
    update_in: BookmarkUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Updates notes or moves a bookmark to another research binder.
    """
    bm = (
        db.query(Bookmark)
        .filter(
            Bookmark.user_id == current_user.id,
            (Bookmark.id == bookmark_id) | (Bookmark.case_id == bookmark_id),
        )
        .first()
    )
    if not bm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bookmark record not found.",
        )

    if update_in.binder_name is not None:
        bm.binder_name = update_in.binder_name.strip() or "General Research"
    if update_in.notes is not None:
        bm.notes = update_in.notes

    db.commit()
    db.refresh(bm)
    return bm


@router.get("/export-memo")
def export_research_memorandum(
    binder: Optional[str] = Query("General Research"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generates a publication-grade Legal Research Memorandum from all cases
    saved inside a research binder.
    """
    query = db.query(Bookmark).filter(Bookmark.user_id == current_user.id)
    if binder and binder.lower() != "all":
        query = query.filter(Bookmark.binder_name.ilike(binder.strip()))

    bookmarks = query.order_by(Bookmark.created_at.asc()).all()

    items = []
    md_lines = [
        f"# LEXGUARD ADVOCATE RESEARCH MEMORANDUM",
        f"**Research Binder:** {binder or 'All Saved Precedents'}",
        f"**Compiled By:** {current_user.name} ({current_user.role.title()})",
        f"**Generated On:** {datetime.now(timezone.utc).strftime('%B %d, %Y %H:%M UTC')}",
        f"**Total Authorities Cited:** {len(bookmarks)}",
        "\n---\n",
    ]

    for idx, b in enumerate(bookmarks, 1):
        c = b.case
        if not c:
            continue
        items.append({
            "index": idx,
            "title": c.title,
            "case_no": c.case_no,
            "court": c.court,
            "year": c.year,
            "official_citation": c.official_citation,
            "precedential_status": c.precedential_status or "Good Law",
            "judge": c.judge,
            "disposition": c.disposition or c.outcome,
            "ratio_decidendi": c.ratio_decidendi,
            "notes": b.notes,
            "file_hash": c.file_hash,
        })

        bench_name = c.judge or "Hon'ble Bench"
        md_lines.extend([
            f"### [{idx}] {c.title}",
            f"- **Court:** {c.court} ({c.year})",
            f"- **Case Number:** {c.case_no}",
            f"- **Official Citation:** {c.official_citation or 'LexGuard Precedent'}",
            f"- **Bench:** {bench_name}",
            f"- **Precedential Authority:** {c.precedential_status or 'Good Law'}",
            f"- **Judicial Ratio:** {c.ratio_decidendi or 'Principles affirmed on record.'}",
            f"- **Advocate Research Note:** {b.notes or 'No private notes attached.'}",
            f"- **Cryptographic Seal:** `{c.file_hash}`",
            "\n",
        ])

    markdown_text = "\n".join(md_lines)
    return {
        "binder_name": binder,
        "total_cases": len(items),
        "items": items,
        "markdown_memorandum": markdown_text,
    }


@router.delete("/{bookmark_id}", status_code=status.HTTP_200_OK)
def delete_bookmark(
    bookmark_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Removes a bookmark by either its bookmark ID or associated case ID.
    """
    bm = (
        db.query(Bookmark)
        .filter(
            Bookmark.user_id == current_user.id,
            (Bookmark.id == bookmark_id) | (Bookmark.case_id == bookmark_id),
        )
        .first()
    )
    if not bm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bookmark record not found.",
        )

    case_id = bm.case_id
    db.delete(bm)
    db.commit()

    log_audit_event(
        db=db,
        action="BOOKMARK_DELETE",
        user_id=current_user.id,
        case_id=case_id,
        details=f"Removed bookmark: {bookmark_id}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return {"detail": "Bookmark removed successfully."}
