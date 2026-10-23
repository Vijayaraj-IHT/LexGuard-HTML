from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.case import Case
from app.models.bookmark import Bookmark
from app.services.audit_service import log_audit_event

router = APIRouter()


class BookmarkCreate(BaseModel):
    case_id: str
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
    act_tags: List[str] = []
    section_tags: List[str] = []
    summary: Optional[str] = None
    file_hash: str

    model_config = ConfigDict(from_attributes=True)


class BookmarkResponse(BaseModel):
    id: str
    user_id: str
    case_id: str
    notes: Optional[str] = None
    created_at: datetime
    case: Optional[BookmarkCaseBrief] = None

    model_config = ConfigDict(from_attributes=True)


@router.get("/", response_model=List[BookmarkResponse])
def get_user_bookmarks(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves all saved bookmarks for the current authenticated user.
    """
    bookmarks = (
        db.query(Bookmark)
        .filter(Bookmark.user_id == current_user.id)
        .order_by(Bookmark.created_at.desc())
        .all()
    )
    return bookmarks


@router.post("/", response_model=BookmarkResponse, status_code=status.HTTP_201_CREATED)
def create_bookmark(
    bookmark_in: BookmarkCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Creates a new bookmark for a case.
    """
    target_case = db.query(Case).filter(Case.id == bookmark_in.case_id).first()
    if not target_case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Case record not found.",
        )

    # Check if already bookmarked
    existing = (
        db.query(Bookmark)
        .filter(Bookmark.user_id == current_user.id, Bookmark.case_id == bookmark_in.case_id)
        .first()
    )
    if existing:
        return existing

    new_bm = Bookmark(
        user_id=current_user.id,
        case_id=bookmark_in.case_id,
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
        details=f"Bookmarked case: {target_case.case_no}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return new_bm


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

    return {"status": "success", "message": "Bookmark removed successfully."}
