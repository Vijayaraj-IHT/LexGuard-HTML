"""
Statutes and Codified Bare Acts API Endpoints.
Serves legislative text, judicial commentaries, and linked precedent cases for Acts Explorer.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import cast, String
from app.core.database import get_db
from app.models.statute import StatuteSection
from app.models.case import Case

router = APIRouter()


@router.get("/")
def list_statute_sections(
    act: Optional[str] = Query(None, description="Filter by act code, e.g. CRPC, IPC, NI_ACT, CONST"),
    db: Session = Depends(get_db),
):
    """Returns codified bare act sections with live case counts."""
    query = db.query(StatuteSection)
    if act:
        query = query.filter(StatuteSection.act_code == act.upper())
    
    sections = query.order_by(StatuteSection.act_code, StatuteSection.section_no).all()
    return [
        {
            "id": s.id,
            "act_code": s.act_code,
            "act_title": s.act_title,
            "section_no": s.section_no,
            "section_title": s.section_title,
            "bare_text": s.bare_text,
            "explanation": s.explanation,
            "case_count": s.case_count,
        }
        for s in sections
    ]


@router.get("/acts")
def list_unique_acts(db: Session = Depends(get_db)):
    """Returns overview of all available Acts with section and case counts."""
    sections = db.query(StatuteSection).all()
    acts_map = {}
    for s in sections:
        if s.act_code not in acts_map:
            acts_map[s.act_code] = {
                "act_code": s.act_code,
                "act_title": s.act_title,
                "section_count": 0,
                "total_cases": 0,
                "sections": []
            }
        acts_map[s.act_code]["section_count"] += 1
        acts_map[s.act_code]["total_cases"] += s.case_count
        acts_map[s.act_code]["sections"].append({
            "section_no": s.section_no,
            "section_title": s.section_title,
            "case_count": s.case_count
        })

    return list(acts_map.values())


@router.get("/{act_code}/{section_no}")
def get_statute_section(
    act_code: str,
    section_no: str,
    db: Session = Depends(get_db),
):
    """Retrieves a specific codified section and all matching cases in LexGuard."""
    sec = db.query(StatuteSection).filter(
        StatuteSection.act_code == act_code.upper(),
        StatuteSection.section_no == section_no
    ).first()

    if not sec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Statute section {section_no} of {act_code} not found in codified database."
        )

    # Find matching cases in database
    sec_tag = f"%{section_no}%"
    matching_cases = db.query(Case).filter(
        Case.status == "published",
        (cast(Case.section_tags, String).ilike(sec_tag)) |
        (Case.full_text.ilike(f"%Section {section_no}%"))
    ).limit(30).all()

    return {
        "id": sec.id,
        "act_code": sec.act_code,
        "act_title": sec.act_title,
        "section_no": sec.section_no,
        "section_title": sec.section_title,
        "bare_text": sec.bare_text,
        "explanation": sec.explanation,
        "case_count": len(matching_cases),
        "cases": [
            {
                "id": c.id,
                "case_no": c.case_no,
                "title": c.title,
                "court": c.court,
                "year": c.year,
                "case_type": c.case_type,
                "outcome": c.outcome,
                "ratio_decidendi": c.ratio_decidendi[:200] if c.ratio_decidendi else None,
                "official_citation": c.official_citation,
            }
            for c in matching_cases
        ]
    }
