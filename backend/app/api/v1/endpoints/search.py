from typing import List, Optional
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.core.database import get_db
from app.core.security import get_optional_current_user
from app.models.user import User
from app.models.case import Case
from app.schemas.search import (
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)
from app.services.local_llm_service import local_llm_service
from app.services.claude_service import claude_service
from app.services.embedding_service import embedding_service
from app.services.audit_service import log_audit_event

router = APIRouter()


import re


def _extract_matched_snippets(text: str, tokens: List[str], max_snippets: int = 2) -> tuple[List[str], List[str]]:
    if not text or not tokens:
        return [], []
    snippets = []
    matched_kws = set()
    lines = text.split("\n")
    current_page = 1
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("--- PAGE "):
            m_pg = re.search(r'\d+', stripped)
            if m_pg:
                try:
                    current_page = int(m_pg.group())
                except Exception:
                    pass
            continue
        line_lower = stripped.lower()
        for tok in tokens:
            if tok in line_lower:
                matched_kws.add(tok)
                if len(snippets) < max_snippets:
                    # Highlight match with <mark> tags
                    pattern = re.compile(re.escape(tok), re.IGNORECASE)
                    highlighted = pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", stripped)
                    if len(highlighted) > 220:
                        # Trim around the first match
                        m_pos = highlighted.lower().find("<mark>")
                        start_pos = max(0, m_pos - 40)
                        end_pos = min(len(highlighted), m_pos + 160)
                        highlighted = ("..." if start_pos > 0 else "") + highlighted[start_pos:end_pos] + ("..." if end_pos < len(highlighted) else "")
                    snippets.append(f"[Page {current_page}] {highlighted}")
    return snippets, list(matched_kws)


@router.post("/", response_model=SearchResponse)
def search_cases(
    search_in: SearchRequest,
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Hugging Face Hybrid Legal Precedent Search with Reciprocal Rank Fusion (RRF):
    1. Local LLM / InLegalBERT extracts statutory sections and legal issues from natural language query.
    2. Sentence-Transformers (all-MiniLM-L6-v2) computes 384-dimensional query vector.
    3. RRF Rank Fusion across:
       - Dense Semantic Vector Similarity (Rank 1)
       - Lexical / Keyword / CNR / Full-Text Search (Rank 2)
       - Statutory Section and Act Alignment (Rank 3)
    4. Extracts matched context snippets from official judgment text with page numbers.
    5. Returns rich judicial metadata (court, bench, coram, disposition, ratio decidendi, seals).
    6. Logs search query in the immutable audit trail.
    """
    query_text = (search_in.query or "").strip()

    # Fast-path for empty or short browse query (< 2 characters)
    if len(query_text) < 2:
        query_obj = db.query(Case).filter(Case.status == "published")
        if search_in.filters:
            f = search_in.filters
            if f.court and f.court != "All Courts":
                query_obj = query_obj.filter(Case.court.ilike(f"%{f.court}%"))
            if f.bench and f.bench != "All Benches":
                if "Principal" in f.bench or "Chennai" in f.bench or "TNCH" in f.bench:
                    query_obj = query_obj.filter(
                        or_(Case.court.ilike("%Principal Seat%"), Case.court.ilike("%Chennai%"), Case.case_no.ilike("TNCH%"))
                    )
                elif "Madurai" in f.bench or "TNMD" in f.bench:
                    query_obj = query_obj.filter(
                        or_(Case.court.ilike("%Madurai%"), Case.case_no.ilike("TNMD%"))
                    )
                elif "Supreme" in f.bench:
                    query_obj = query_obj.filter(Case.court.ilike("%Supreme%"))
            if f.year_from:
                query_obj = query_obj.filter(Case.year >= f.year_from)
            if f.year_to:
                query_obj = query_obj.filter(Case.year <= f.year_to)
            disp_filter = f.disposition or f.outcome
            if disp_filter and disp_filter.lower() != "all":
                query_obj = query_obj.filter(
                    or_(Case.disposition.ilike(f"%{disp_filter}%"), Case.outcome.ilike(f"%{disp_filter}%"))
                )
            if f.act and f.act.strip():
                act_str = f.act.strip().lower()
                query_obj = query_obj.filter(
                    or_(
                        Case.title.ilike(f"%{act_str}%"),
                        Case.summary.ilike(f"%{act_str}%"),
                        Case.ratio_decidendi.ilike(f"%{act_str}%"),
                    )
                )

        total_matches = query_obj.count()
        cases_page = (
            query_obj.order_by(Case.created_at.desc())
            .offset(search_in.offset)
            .limit(search_in.limit)
            .all()
        )

        results = [
            SearchResultItem(
                id=c.id,
                case_no=c.case_no,
                title=c.title,
                court=c.court,
                year=c.year,
                matched_sections=[],
                relevance_score=1.0,
                outcome=c.outcome,
                disposition=c.disposition or c.outcome or "Decided",
                judge=c.judge or "Hon'ble Court",
                summary=c.summary,
                ratio_decidendi=c.ratio_decidendi,
                file_hash=c.file_hash,
                redacted_file_hash=c.redacted_file_hash,
                act_tags=c.act_tags or [],
                section_tags=c.section_tags or [],
                keyword_tags=c.keyword_tags or [],
                matched_snippets=[],
                matched_keywords=[],
                source_url=c.source_url,
                rrf_score=1.0,
                cnr_number=c.cnr_number,
                case_type=c.case_type,
                legal_domain=c.legal_domain,
                decision_date=str(c.decision_date) if c.decision_date else None,
                precedential_status=c.precedential_status or "Good Law",
                cited_by_count=c.cited_by_count or 0,
                official_citation=c.official_citation,
                search_mode="Repository Index Browse",
            )
            for c in cases_page
        ]

        log_audit_event(
            db=db,
            action="SEARCH_BROWSE",
            user_id=current_user.id if current_user else None,
            details=f"Browsed {len(results)} of {total_matches} published cases",
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        return SearchResponse(
            total=total_matches,
            results=results,
            query_understanding={"sections": [], "issue": "All Published Cases", "jurisdiction": "All Courts"},
        )

    # 1. AI Query Enrichment (Local Qwen/Llama or InLegalBERT NER)
    enriched = local_llm_service.enrich_query(search_in.query)
    query_sections = enriched.get("sections", [])
    query_acts = enriched.get("acts", [])

    # 2. Vector Embedding for Query
    query_embedding = embedding_service.generate_embedding(search_in.query)

    # 3. Base Query: Only published cases
    query_obj = db.query(Case).filter(Case.status == "published")

    # Apply optional filters
    if search_in.filters:
        f = search_in.filters
        if f.court and f.court != "All Courts":
            query_obj = query_obj.filter(Case.court.ilike(f"%{f.court}%"))
        if f.bench and f.bench != "All Benches":
            if "Principal" in f.bench or "Chennai" in f.bench or "TNCH" in f.bench:
                query_obj = query_obj.filter(
                    or_(Case.court.ilike("%Principal Seat%"), Case.court.ilike("%Chennai%"), Case.case_no.ilike("TNCH%"))
                )
            elif "Madurai" in f.bench or "TNMD" in f.bench:
                query_obj = query_obj.filter(
                    or_(Case.court.ilike("%Madurai%"), Case.case_no.ilike("TNMD%"))
                )
            elif "Supreme" in f.bench:
                query_obj = query_obj.filter(Case.court.ilike("%Supreme%"))
        if f.year_from:
            query_obj = query_obj.filter(Case.year >= f.year_from)
        if f.year_to:
            query_obj = query_obj.filter(Case.year <= f.year_to)
        disp_filter = f.disposition or f.outcome
        if disp_filter and disp_filter.lower() != "all":
            query_obj = query_obj.filter(
                or_(Case.disposition.ilike(f"%{disp_filter}%"), Case.outcome.ilike(f"%{disp_filter}%"))
            )
        if f.act and f.act.strip():
            act_str = f.act.strip().lower()
            query_obj = query_obj.filter(
                or_(
                    Case.title.ilike(f"%{act_str}%"),
                    Case.summary.ilike(f"%{act_str}%"),
                    Case.ratio_decidendi.ilike(f"%{act_str}%"),
                )
            )

    candidates: List[Case] = query_obj.all()
    if not candidates:
        return SearchResponse(total=0, results=[], query_understanding=enriched)

    tokens = [t.lower() for t in search_in.query.split() if len(t) > 2]
    is_cnr_query = bool(re.search(r'(TNCH|TNMD|[A-Z]{4}\d{8,12}|\d{3,5}/\d{4})', query_text, re.IGNORECASE))

    # 4. Compute 3 Component Scores for Reciprocal Rank Fusion (RRF)
    # Channel 1: Semantic Vector Similarity
    # Channel 2: Lexical Keyword / Full-Text / CNR Hit
    # Channel 3: Statutory Section & Act Overlap
    vector_scores = {}
    lexical_scores = {}
    statute_scores = {}
    case_snippets = {}
    case_matched_kws = {}
    case_matched_sections = {}

    for c in candidates:
        # Vector Similarity
        sem_sim = 0.0
        if c.embedding:
            try:
                sem_sim = embedding_service.cosine_similarity(query_embedding, c.embedding)
            except Exception:
                sem_sim = 0.0
        vector_scores[c.id] = max(0.0, float(sem_sim))

        # Lexical Score
        c_no_lower = (c.case_no or "").lower()
        title_lower = (c.title or "").lower()
        full_text_start = (c.full_text or "")[:12000].lower()
        haystack = f"{c_no_lower} {title_lower} {c.summary or ''} {' '.join(c.keyword_tags or [])} {c.facts or ''} {c.ratio_decidendi or ''} {full_text_start}".lower()

        lex_score = 0.0
        # Direct CNR or Case Number Exact Match boost
        if is_cnr_query and any(tok in c_no_lower for tok in tokens):
            lex_score += 50.0
        elif c_no_lower in query_text.lower():
            lex_score += 50.0

        # Title token hits (weight 3.0)
        title_hits = sum(3.0 for tok in tokens if tok in title_lower)
        body_hits = sum(1.0 for tok in tokens if tok in haystack)
        lex_score += title_hits + body_hits
        lexical_scores[c.id] = lex_score

        # Extract Snippets & Matched Keywords
        snips, kws = _extract_matched_snippets(c.full_text or c.summary or "", tokens, max_snippets=2)
        case_snippets[c.id] = snips
        case_matched_kws[c.id] = kws

        # Statutory Score
        matched_secs = []
        c_sections = c.section_tags or []
        for s in query_sections:
            if any(s.lower() in sec.lower() for sec in c_sections):
                matched_secs.append(s)
        case_matched_sections[c.id] = matched_secs

        c_acts = [a.lower() for a in (c.act_tags or [])]
        act_overlap = sum(1.0 for a in query_acts if any(a.lower() in ca for ca in c_acts))
        sec_overlap = len(matched_secs)
        statute_scores[c.id] = (sec_overlap * 2.0) + act_overlap

    # Build Ranks (1-indexed) for each channel
    sorted_by_vector = sorted(candidates, key=lambda c: vector_scores[c.id], reverse=True)
    vector_rank = {c.id: idx + 1 for idx, c in enumerate(sorted_by_vector)}

    sorted_by_lexical = sorted(candidates, key=lambda c: lexical_scores[c.id], reverse=True)
    lexical_rank = {c.id: idx + 1 for idx, c in enumerate(sorted_by_lexical)}

    sorted_by_statute = sorted(candidates, key=lambda c: statute_scores[c.id], reverse=True)
    statute_rank = {c.id: idx + 1 for idx, c in enumerate(sorted_by_statute)}

    # Standard Reciprocal Rank Fusion (RRF) with constant k=60
    # RRF(d) = sum( w_m / (k + rank_m(d)) )
    K_RRF = 60
    W_VECTOR = 0.50
    W_LEXICAL = 0.30
    W_STATUTE = 0.20

    rrf_scored = []
    for c in candidates:
        r_vec = vector_rank[c.id]
        r_lex = lexical_rank[c.id]
        r_stat = statute_rank[c.id]

        raw_rrf = (
            (W_VECTOR / (K_RRF + r_vec))
            + (W_LEXICAL / (K_RRF + r_lex))
            + (W_STATUTE / (K_RRF + r_stat))
        )

        # Scale RRF to standard 0.0 - 1.0 percentage score
        # Max theoretical RRF = 1.0 / 61 = 0.01639. Normalize so top is ~0.95+
        normalized_score = round(min(0.99, raw_rrf * 60.0), 3)

        # Direct boost for exact CNR / case_no match
        if lexical_scores[c.id] >= 50.0:
            normalized_score = 0.99

        # Filter out zero-relevance noise if query tokens provided
        if tokens and lexical_scores[c.id] == 0.0 and vector_scores[c.id] < 0.15 and not case_matched_sections[c.id]:
            continue

        c_timestamp = c.created_at.timestamp() if c.created_at else 0.0
        rrf_scored.append((
            normalized_score,
            raw_rrf,
            c_timestamp,
            SearchResultItem(
                id=c.id,
                case_no=c.case_no,
                title=c.title,
                court=c.court,
                year=c.year,
                matched_sections=case_matched_sections[c.id],
                relevance_score=normalized_score,
                outcome=c.outcome,
                disposition=c.disposition or c.outcome or "Decided",
                judge=c.judge or "Hon'ble Court",
                summary=c.summary,
                ratio_decidendi=c.ratio_decidendi,
                file_hash=c.file_hash,
                redacted_file_hash=c.redacted_file_hash,
                act_tags=c.act_tags or [],
                section_tags=c.section_tags or [],
                keyword_tags=c.keyword_tags or [],
                matched_snippets=case_snippets[c.id],
                matched_keywords=case_matched_kws[c.id],
                source_url=c.source_url,
                rrf_score=round(raw_rrf, 5),
                cnr_number=c.cnr_number,
                case_type=c.case_type,
                legal_domain=c.legal_domain,
                decision_date=str(c.decision_date) if c.decision_date else None,
                precedential_status=c.precedential_status or "Good Law",
                cited_by_count=c.cited_by_count or 0,
                official_citation=c.official_citation,
                search_mode="Hybrid Semantic/Lexical RRF",
            )
        ))

    # Sort descending by normalized RRF score, breaking ties by timestamp
    rrf_scored.sort(key=lambda x: (x[0], x[2]), reverse=True)
    total_matches = len(rrf_scored)

    # Paginate
    paged = [
        item for _, _, _, item in rrf_scored[search_in.offset : search_in.offset + search_in.limit]
    ]

    # 5. Log immutable audit trail
    log_audit_event(
        db=db,
        action="SEARCH",
        user_id=current_user.id if current_user else None,
        details=f"RRF Query: '{search_in.query[:100]}' - Returned {len(paged)} of {total_matches} results",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return SearchResponse(
        total=total_matches,
        results=paged,
        query_understanding=enriched,
    )
