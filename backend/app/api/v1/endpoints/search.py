from typing import Any, Dict, List, Optional, Tuple
import re
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, defer
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
from app.services.embedding_service import embedding_service
from app.services.audit_service import log_audit_event

router = APIRouter()


def parse_advanced_query(raw_query: str) -> Dict[str, Any]:
    """
    Parses boolean operators (AND, OR, NOT), exact quotes ("..."), and field prefixes.
    e.g. '"dying declaration" AND burn NOT accidental court:Madras year:2026'
    """
    text = (raw_query or "").strip()
    required_phrases = []
    excluded_terms = []
    and_terms = []
    or_terms = []
    field_filters = {}

    # 1. Extract exact quotes "..."
    quote_matches = re.findall(r'"([^"]+)"', text)
    for qm in quote_matches:
        if qm.strip():
            required_phrases.append(qm.strip().lower())
    text_without_quotes = re.sub(r'"[^"]+"', ' ', text)

    # 2. Extract field prefixes like court:Madras or year:2026 or section:482 or citation:...
    prefix_pattern = re.compile(r'(\b[a-zA-Z_]+):([a-zA-Z0-9_\-\(\)\s\.]+?)(?=\s+[a-zA-Z_]+:|\s+AND\b|\s+OR\b|\s+NOT\b|\s*$)', re.IGNORECASE)
    for m in prefix_pattern.finditer(text_without_quotes):
        field = m.group(1).lower()
        val = m.group(2).strip().strip('"').lower()
        field_filters[field] = val
    text_cleaned = prefix_pattern.sub(' ', text_without_quotes)

    # 3. Check for Boolean operators AND, OR, NOT
    has_boolean = bool(re.search(r'\b(AND|OR|NOT)\b', text_cleaned))

    if has_boolean:
        raw_tokens = text_cleaned.split()
        mode = "AND"
        for tok in raw_tokens:
            tok_upper = tok.upper()
            if tok_upper in ["AND", "OR", "NOT"]:
                mode = tok_upper
                continue
            t_clean = tok.strip().lower()
            if not t_clean or len(t_clean) < 2:
                continue
            if mode == "NOT" or tok.startswith("-"):
                excluded_terms.append(t_clean.lstrip("-"))
            elif mode == "OR":
                or_terms.append(t_clean)
            else:
                and_terms.append(t_clean)
    else:
        # Standard token list
        and_terms = [t.lower() for t in text_cleaned.split() if len(t) > 2]

    is_advanced = bool(required_phrases or excluded_terms or or_terms or field_filters or has_boolean)
    return {
        "required_phrases": required_phrases,
        "excluded_terms": excluded_terms,
        "and_terms": and_terms,
        "or_terms": or_terms,
        "field_filters": field_filters,
        "is_advanced": is_advanced,
    }


def _build_snippets(
    text: str, tokens: List[str], max_snippets: int = 2
) -> Tuple[List[str], List[Dict[str, Any]], List[str]]:
    """Return (plain_lines, snippet_objects, matched_keywords).

    Snippet text is never HTML: highlights are returned as [start, end] ranges so the
    client can escape the text and then wrap the ranges. This removes the injection
    path that existed when the server interleaved <mark> tags into judgment text.
    """
    if not text or not tokens:
        return [], [], []

    plain: List[str] = []
    snippets: List[Dict[str, Any]] = []
    matched_kws = set()
    current_page = 1

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("--- PAGE "):
            m_pg = re.search(r"\d+", stripped)
            if m_pg:
                try:
                    current_page = int(m_pg.group())
                except Exception:
                    pass
            continue

        lower = stripped.lower()
        hits = [t for t in tokens if t and t in lower]
        if not hits:
            continue
        matched_kws.update(hits)
        if len(snippets) >= max_snippets:
            continue

        first = min(lower.find(t) for t in hits)
        start = max(0, first - 60)
        end = min(len(stripped), first + 200)
        window = stripped[start:end]
        spans: List[List[int]] = []
        for tok in hits:
            for m in re.finditer(re.escape(tok), window, re.IGNORECASE):
                spans.append([m.start(), m.end()])
        spans.sort()
        snippets.append({"page": current_page, "text": window, "highlights": spans})
        plain.append(f"[Page {current_page}] {window}")

    return plain, snippets, sorted(matched_kws)


def _display_year(case: Case) -> Optional[int]:
    """Prefer the decision date; fall back to the stored year."""
    try:
        if case.decision_date:
            return case.decision_date.year
    except Exception:
        pass
    return case.year


def _citation_display(case: Case) -> str:
    parts = [case.case_no, case.court]
    year = _display_year(case)
    if year:
        parts.append(str(year))
    return " · ".join(p for p in parts if p)


def _source_verified(case: Case) -> bool:
    return (case.source_verification_state or "").strip().lower() == "verified"


def _repository_id(case: Case) -> str:
    return f"LG-{(case.id or '')[:8].upper()}"


@router.post("/", response_model=SearchResponse)
def search_cases(
    search_in: SearchRequest,
    request: Request,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
):
    """
    Advanced Boolean, Citation & Reciprocal Rank Fusion (RRF) Legal Search Engine:
    1. Parses exact quotes ("..."), Boolean logic (AND, OR, NOT), and field prefixes.
    2. Local LLM / InLegalBERT extracts statutory sections and legal issues.
    3. Sentence-Transformers computes 384-dimensional query vector.
    4. RRF Rank Fusion across:
       - Dense Semantic Vector Similarity (Rank 1)
       - Lexical / Exact Phrase / Boolean Keyword / Citation Hit (Rank 2)
       - Statutory Section and Act Alignment (Rank 3)
    5. Extracts matched context snippets with page numbers.
    6. Returns rich judicial metadata, precedential validity stamps, and citation counts.
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
                relevance_score=None,
                match_type="browse",
                citation_display=_citation_display(c),
                source_verified=_source_verified(c),
                repository_id=_repository_id(c),
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

    # 1. Parse Advanced Boolean & Field Query
    adv_query = parse_advanced_query(query_text)

    # 2. AI Query Enrichment (Local Qwen/Llama or InLegalBERT NER)
    clean_search_text = " ".join(adv_query["and_terms"] + adv_query["required_phrases"] + adv_query["or_terms"]) or query_text
    enriched = local_llm_service.enrich_query(clean_search_text)
    query_sections = enriched.get("sections", [])
    query_acts = enriched.get("acts", [])

    # 3. Vector Embedding for Query (LRU Cached)
    query_embedding = embedding_service.encode_query(clean_search_text)

    # 4. Base Query: Only published cases, deferring heavy full_text RAM hydration
    query_obj = db.query(Case).options(defer(Case.full_text)).filter(Case.status == "published")

    # Apply UI filters
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

    # Apply Field Prefixes parsed directly from query (court:..., year:..., etc.)
    ff = adv_query["field_filters"]
    if "court" in ff:
        query_obj = query_obj.filter(Case.court.ilike(f"%{ff['court']}%"))
    if "year" in ff:
        try:
            query_obj = query_obj.filter(Case.year == int(ff["year"]))
        except Exception:
            pass
    if "judge" in ff:
        query_obj = query_obj.filter(Case.judge.ilike(f"%{ff['judge']}%"))
    if "cnr" in ff:
        query_obj = query_obj.filter(Case.cnr_number.ilike(f"%{ff['cnr']}%"))

    candidates: List[Case] = query_obj.all()
    if not candidates:
        return SearchResponse(total=0, results=[], query_understanding=enriched)

    tokens = [t.lower() for t in clean_search_text.split() if len(t) > 2]
    all_query_terms = adv_query["and_terms"] + adv_query["required_phrases"]
    is_cnr_query = bool(re.search(r'(TNCH|TNMD|[A-Z]{4}\d{8,12}|\d{3,5}/\d{4})', query_text, re.IGNORECASE))
    is_citation_query = bool(re.search(r'(\d{4}\s+(?:SCC|AIR|SCR)|SCC\s+OnLine|\d+\s+of\s+\d{4})', query_text, re.IGNORECASE))

    # 5. Compute 3 Component Scores for Reciprocal Rank Fusion (RRF)
    vector_scores = {}
    lexical_scores = {}
    statute_scores = {}
    case_snippets = {}
    case_snippet_objs = {}
    case_matched_kws = {}
    case_matched_sections = {}
    case_search_modes = {}

    for c in candidates:
        c_no_lower = (c.case_no or "").lower()
        title_lower = (c.title or "").lower()
        official_cit_lower = (c.official_citation or "").lower()
        full_text_start = (c.full_text or "")[:15000].lower()
        haystack = f"{c_no_lower} {title_lower} {official_cit_lower} {c.summary or ''} {' '.join(c.keyword_tags or [])} {c.facts or ''} {c.ratio_decidendi or ''} {full_text_start}".lower()

        # Boolean Excluded Terms Check (NOT)
        if any(ex in haystack for ex in adv_query["excluded_terms"]):
            vector_scores[c.id] = 0.0
            lexical_scores[c.id] = -100.0
            statute_scores[c.id] = 0.0
            continue

        # Quoted Phrases Check ("...")
        phrase_miss = False
        phrase_bonus = 0.0
        for phrase in adv_query["required_phrases"]:
            if phrase in haystack:
                phrase_bonus += 120.0
            else:
                phrase_miss = True

        # Vector Similarity
        sem_sim = 0.0
        if c.embedding:
            try:
                sem_sim = embedding_service.cosine_similarity(query_embedding, c.embedding)
            except Exception:
                sem_sim = 0.0
        vector_scores[c.id] = max(0.0, float(sem_sim))

        # Lexical Score
        lex_score = 0.0
        mode_label = "Hybrid Semantic/Lexical RRF"

        # Exact Official Citation Match (e.g. (2014) 2 SCC 1)
        if official_cit_lower and (official_cit_lower in query_text.lower() or query_text.lower() in official_cit_lower):
            lex_score += 300.0
            mode_label = "Exact Citation Lookup"
        elif is_citation_query and any(tok in haystack for tok in tokens):
            lex_score += 60.0
            mode_label = "Citation Search Match"

        # Exact CNR or Case Number Match
        if is_cnr_query and any(tok in c_no_lower for tok in tokens):
            lex_score += 150.0
            mode_label = "Case / CNR Number Match"
        elif c_no_lower in query_text.lower():
            lex_score += 100.0
            mode_label = "Exact Case Number Match"

        # Boolean and Exact Phrase Bonuses
        if adv_query["required_phrases"]:
            if not phrase_miss:
                lex_score += phrase_bonus
                mode_label = "Exact Phrase Match"
            else:
                # Penalize missing mandatory quoted phrase
                lex_score -= 50.0

        # Title & Body token hits
        title_hits = sum(4.0 for tok in tokens if tok in title_lower)
        body_hits = sum(1.5 for tok in tokens if tok in haystack)
        lex_score += title_hits + body_hits
        lexical_scores[c.id] = lex_score
        case_search_modes[c.id] = mode_label

        # Extract Snippets & Matched Keywords
        snip_tokens = all_query_terms or tokens
        plain_snips, snip_objs, kws = _build_snippets(
            c.full_text or c.summary or "", snip_tokens, max_snippets=2
        )
        case_snippets[c.id] = plain_snips
        case_snippet_objs[c.id] = snip_objs
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

    # Filter out excluded cases (negative lexical score)
    valid_candidates = [c for c in candidates if lexical_scores.get(c.id, 0.0) >= 0]
    if not valid_candidates:
        return SearchResponse(total=0, results=[], query_understanding=enriched)

    # Build Ranks (1-indexed) for each channel
    sorted_by_vector = sorted(valid_candidates, key=lambda c: vector_scores.get(c.id, 0.0), reverse=True)
    vector_rank = {c.id: idx + 1 for idx, c in enumerate(sorted_by_vector)}

    sorted_by_lexical = sorted(valid_candidates, key=lambda c: lexical_scores.get(c.id, 0.0), reverse=True)
    lexical_rank = {c.id: idx + 1 for idx, c in enumerate(sorted_by_lexical)}

    sorted_by_statute = sorted(valid_candidates, key=lambda c: statute_scores.get(c.id, 0.0), reverse=True)
    statute_rank = {c.id: idx + 1 for idx, c in enumerate(sorted_by_statute)}

    k = 60
    rrf_scored = []
    max_raw_rrf = 0.0

    for c in valid_candidates:
        v_r = vector_rank.get(c.id, 999)
        l_r = lexical_rank.get(c.id, 999)
        s_r = statute_rank.get(c.id, 999)

        # Weighting:
        # If exact phrase/citation, weight lexical higher
        if lexical_scores.get(c.id, 0.0) > 80.0:
            raw_rrf = (0.2 / (k + v_r)) + (0.7 / (k + l_r)) + (0.1 / (k + s_r))
        else:
            raw_rrf = (0.5 / (k + v_r)) + (0.35 / (k + l_r)) + (0.15 / (k + s_r))

        if raw_rrf > max_raw_rrf:
            max_raw_rrf = raw_rrf
        rrf_scored.append((c, raw_rrf))

    if max_raw_rrf == 0.0:
        max_raw_rrf = 1.0

    results_tuples = []
    for c, raw_rrf in rrf_scored:
        norm_score = round(raw_rrf / max_raw_rrf, 4)
        if statute_scores.get(c.id, 0.0) > 0:
            match_type = "statute"
        elif lexical_scores.get(c.id, 0.0) > 0:
            match_type = "keyword"
        else:
            match_type = "related"
        c_ts = c.created_at.timestamp() if c.created_at else 0.0
        results_tuples.append((
            norm_score,
            raw_rrf,
            c_ts,
            SearchResultItem(
                id=c.id,
                case_no=c.case_no,
                title=c.title,
                court=c.court,
                year=c.year,
                matched_sections=case_matched_sections.get(c.id, []),
                relevance_score=norm_score,
                match_type=match_type,
                citation_display=_citation_display(c),
                source_verified=_source_verified(c),
                repository_id=_repository_id(c),
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
                matched_snippets=case_snippets.get(c.id, []),
                snippets=case_snippet_objs.get(c.id, []),
                matched_keywords=case_matched_kws.get(c.id, []),
                source_url=c.source_url,
                rrf_score=round(raw_rrf, 5),
                cnr_number=c.cnr_number,
                case_type=c.case_type,
                legal_domain=c.legal_domain,
                decision_date=str(c.decision_date) if c.decision_date else None,
                precedential_status=c.precedential_status or "Good Law",
                cited_by_count=c.cited_by_count or 0,
                official_citation=c.official_citation,
                search_mode=case_search_modes.get(c.id, "Hybrid Semantic/Lexical RRF"),
            )
        ))

    results_tuples.sort(key=lambda x: (x[0], x[2]), reverse=True)
    total_matches = len(results_tuples)

    paged = [item for _, _, _, item in results_tuples[search_in.offset : search_in.offset + search_in.limit]]

    log_audit_event(
        db=db,
        action="SEARCH",
        user_id=current_user.id if current_user else None,
        details=f"Query: '{query_text[:100]}' (Adv: {adv_query['is_advanced']}) - Returned {len(paged)} of {total_matches} results",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return SearchResponse(
        total=total_matches,
        results=paged,
        query_understanding={
            "sections": query_sections,
            "acts": query_acts,
            "required_phrases": adv_query["required_phrases"],
            "excluded_terms": adv_query["excluded_terms"],
            "is_advanced_syntax": adv_query["is_advanced"],
        },
    )
