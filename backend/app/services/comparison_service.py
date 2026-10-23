import re
from typing import List, Set, Dict, Any
from app.models.case import Case
from app.schemas.comparison import (
    CaseComparisonRequest,
    CaseComparisonResponse,
    DimensionComparisonResult,
    PrecedentSummary,
    MultiCaseComparisonRequest,
    MultiCaseComparisonResponse,
)


class CaseComparisonService:
    """
    Transparent deterministic legal case comparator.
    Evaluates 4 core Indian-law judicial dimensions:
    1. Legal Issues & Statutory Provisions (35%)
    2. Facts / Factual Matrix (35%)
    3. Court & Jurisdiction (15%)
    4. Remedy & Procedural Posture (15%)

    If a dimension is omitted or the user case is pending, the dimension is
    marked 'not_comparable' and excluded from the denominator, with remaining
    active weights renormalized.
    """

    STOPWORDS: Set[str] = {
        "the", "of", "and", "a", "to", "in", "is", "that", "it", "with", "as", "for", "was",
        "on", "are", "by", "this", "be", "or", "from", "at", "which", "an", "under", "court",
        "order", "shall", "any", "all", "must", "state", "union", "india", "petitioner",
        "respondent", "versus", "case", "honble", "matter", "appellant", "applicant"
    }

    WEIGHT_LEGAL: float = 0.35
    WEIGHT_FACTS: float = 0.35
    WEIGHT_JURISDICTION: float = 0.15
    WEIGHT_REMEDY: float = 0.15

    def _tokenize(self, text: str) -> Set[str]:
        if not text:
            return set()
        words = re.findall(r"\b[a-zA-Z0-9]{3,}\b", text.lower())
        return {w for w in words if w not in self.STOPWORDS}

    def _normalize_str(self, text: str) -> str:
        return re.sub(r"\s+", " ", (text or "").strip().lower())

    def compare_case(self, req: CaseComparisonRequest, precedent: Case) -> CaseComparisonResponse:
        dimensions: List[DimensionComparisonResult] = []

        # -------------------------------------------------------------
        # Dimension 1: Legal Issues & Statutory Provisions (35%)
        # -------------------------------------------------------------
        user_provisions = [p.strip() for p in (req.statutory_provisions or []) if p.strip()]
        user_issues = [i.strip() for i in (req.legal_issues or []) if i.strip()]
        user_legal_combined = " ".join(user_provisions + user_issues)

        prec_sections = precedent.section_tags or []
        prec_acts = precedent.act_tags or []
        prec_issues = precedent.issues_framed or []
        prec_legal_combined = " ".join(prec_sections + prec_acts + prec_issues)

        if not user_provisions and not user_issues:
            dimensions.append(DimensionComparisonResult(
                dimension_name="Legal Issues & Statutory Provisions",
                user_value="Not specified",
                precedent_value=", ".join(prec_sections[:3]) if prec_sections else "Precedent statutes",
                match_state="not_comparable",
                weight_assigned=self.WEIGHT_LEGAL,
                effective_weight_percentage=0.0,
                dimension_score=0.0,
                explanation="No statutory provisions or legal issues were provided in your case. Excluded from score denominator.",
                is_included_in_score=False,
            ))
        else:
            user_tokens = self._tokenize(user_legal_combined)
            prec_tokens = self._tokenize(prec_legal_combined)
            overlap = user_tokens.intersection(prec_tokens)

            # Check direct statutory provisions match
            user_prov_set = {self._normalize_str(p) for p in user_provisions}
            prec_sec_set = {self._normalize_str(s) for s in prec_sections}
            exact_sec_matches = user_prov_set.intersection(prec_sec_set)

            if len(exact_sec_matches) >= 1 or (len(user_tokens) > 0 and len(overlap) / len(user_tokens) >= 0.7):
                match_state = "exact"
                score = 100.0 if len(exact_sec_matches) >= 1 else 90.0
                explanation = (
                    f"Substantial statutory alignment. Matched key statutory provisions/doctrine: "
                    f"'{', '.join(list(exact_sec_matches or overlap)[:3])}'."
                )
            elif len(overlap) >= 2 or (len(user_tokens) > 0 and len(overlap) / len(user_tokens) >= 0.25):
                match_state = "partial"
                overlap_ratio = len(overlap) / max(len(user_tokens), 1)
                score = round(min(50.0 + (overlap_ratio * 40.0), 85.0), 1)
                explanation = (
                    f"Partial legal overlap on concepts: '{', '.join(list(overlap)[:3])}'. "
                    f"Related legislative framework with differing specific sub-clauses."
                )
            else:
                match_state = "different"
                score = 15.0
                explanation = "Statutory provisions and legal grounds rely on different legal frameworks or enactments."

            dimensions.append(DimensionComparisonResult(
                dimension_name="Legal Issues & Statutory Provisions",
                user_value=", ".join(user_provisions[:3]) if user_provisions else user_issues[0][:60],
                precedent_value=", ".join(prec_sections[:3]) if prec_sections else "Precedent statutes",
                match_state=match_state,
                weight_assigned=self.WEIGHT_LEGAL,
                effective_weight_percentage=0.0,
                dimension_score=score,
                explanation=explanation,
                is_included_in_score=True,
            ))

        # -------------------------------------------------------------
        # Dimension 2: Facts / Factual Matrix (35%)
        # -------------------------------------------------------------
        user_facts = (req.facts_summary or "").strip()
        prec_facts = (precedent.facts or precedent.summary or "").strip()

        if not user_facts:
            dimensions.append(DimensionComparisonResult(
                dimension_name="Facts & Dispute Context",
                user_value="Not specified",
                precedent_value=prec_facts[:80] + "..." if len(prec_facts) > 80 else prec_facts,
                match_state="not_comparable",
                weight_assigned=self.WEIGHT_FACTS,
                effective_weight_percentage=0.0,
                dimension_score=0.0,
                explanation="Factual summary was not entered for your case. Excluded from score denominator.",
                is_included_in_score=False,
            ))
        else:
            user_fact_tokens = self._tokenize(user_facts)
            prec_fact_tokens = self._tokenize(prec_facts)
            fact_overlap = user_fact_tokens.intersection(prec_fact_tokens)
            fact_ratio = len(fact_overlap) / max(len(user_fact_tokens), 1)

            if fact_ratio >= 0.45:
                match_state = "exact"
                score = min(round(85.0 + (fact_ratio * 25.0), 1), 100.0)
                explanation = f"High factual similarity in dispute context. Overlapping factual concepts: '{', '.join(list(fact_overlap)[:4])}'."
            elif fact_ratio >= 0.18:
                match_state = "partial"
                score = round(40.0 + (fact_ratio * 40.0), 1)
                explanation = f"Partial factual correspondence across transactional/dispute aspects: '{', '.join(list(fact_overlap)[:3])}'."
            else:
                match_state = "different"
                score = 20.0
                explanation = "Factual matrix of the dispute diverges significantly from the precedent's factual circumstances."

            dimensions.append(DimensionComparisonResult(
                dimension_name="Facts & Dispute Context",
                user_value=user_facts[:80] + "..." if len(user_facts) > 80 else user_facts,
                precedent_value=prec_facts[:80] + "..." if len(prec_facts) > 80 else prec_facts,
                match_state=match_state,
                weight_assigned=self.WEIGHT_FACTS,
                effective_weight_percentage=0.0,
                dimension_score=score,
                explanation=explanation,
                is_included_in_score=True,
            ))

        # -------------------------------------------------------------
        # Dimension 3: Court & Jurisdiction (15%)
        # -------------------------------------------------------------
        user_court = (req.court_jurisdiction or "").strip()
        prec_court = (precedent.court or "").strip()

        if not user_court:
            dimensions.append(DimensionComparisonResult(
                dimension_name="Court & Jurisdiction",
                user_value="Not specified",
                precedent_value=prec_court,
                match_state="not_comparable",
                weight_assigned=self.WEIGHT_JURISDICTION,
                effective_weight_percentage=0.0,
                dimension_score=0.0,
                explanation="Court jurisdiction was omitted in input. Excluded from score denominator.",
                is_included_in_score=False,
            ))
        else:
            norm_user_court = self._normalize_str(user_court)
            norm_prec_court = self._normalize_str(prec_court)

            if norm_user_court == norm_prec_court:
                match_state = "exact"
                score = 100.0
                explanation = f"Identical judicial forum: {prec_court}."
            elif "supreme court" in norm_prec_court:
                # Supreme Court of India is binding precedent under Article 141
                match_state = "partial"
                score = 90.0
                explanation = "The precedent is from the Supreme Court of India, which is binding law across all Indian High Courts and subordinate courts under Article 141."
            elif "high court" in norm_user_court and "high court" in norm_prec_court:
                match_state = "partial"
                score = 70.0
                explanation = f"Inter-High Court precedent. Judgment from {prec_court} carries strong persuasive value before {user_court}."
            else:
                match_state = "different"
                score = 30.0
                explanation = f"Distinct court jurisdictions ({user_court} vs {prec_court}). Persuasive authority depends on appellate hierarchy."

            dimensions.append(DimensionComparisonResult(
                dimension_name="Court & Jurisdiction",
                user_value=user_court,
                precedent_value=prec_court,
                match_state=match_state,
                weight_assigned=self.WEIGHT_JURISDICTION,
                effective_weight_percentage=0.0,
                dimension_score=score,
                explanation=explanation,
                is_included_in_score=True,
            ))

        # -------------------------------------------------------------
        # Dimension 4: Remedy & Procedural Posture (15%)
        # -------------------------------------------------------------
        user_remedy = (req.remedy_sought or req.procedural_status or "").strip()
        prec_remedy = (precedent.disposition or precedent.outcome or "Judicial Order").strip()

        if not user_remedy:
            dimensions.append(DimensionComparisonResult(
                dimension_name="Remedy & Procedural Posture",
                user_value="Not specified",
                precedent_value=prec_remedy,
                match_state="not_comparable",
                weight_assigned=self.WEIGHT_REMEDY,
                effective_weight_percentage=0.0,
                dimension_score=0.0,
                explanation="No remedy sought or procedural posture provided. Excluded from score denominator.",
                is_included_in_score=False,
            ))
        else:
            u_rem_tokens = self._tokenize(user_remedy)
            p_rem_tokens = self._tokenize(f"{prec_remedy} {precedent.summary or ''}")
            rem_overlap = u_rem_tokens.intersection(p_rem_tokens)

            # Check core legal prayer keywords
            bail_match = ("bail" in user_remedy.lower()) and ("bail" in prec_remedy.lower() or "bail" in (precedent.summary or "").lower())
            quash_match = ("quash" in user_remedy.lower()) and ("quash" in prec_remedy.lower() or "quash" in (precedent.summary or "").lower())

            if bail_match or quash_match or (len(u_rem_tokens) > 0 and len(rem_overlap) >= 1):
                match_state = "exact"
                score = 95.0
                explanation = f"Matching procedural remedy category ({user_remedy}). Precedent granted equivalent form of relief: {prec_remedy}."
            else:
                match_state = "partial"
                score = 50.0
                explanation = f"Procedural posture differs slightly ({user_remedy} vs {prec_remedy}), though comparable statutory principles apply."

            dimensions.append(DimensionComparisonResult(
                dimension_name="Remedy & Procedural Posture",
                user_value=user_remedy,
                precedent_value=prec_remedy,
                match_state=match_state,
                weight_assigned=self.WEIGHT_REMEDY,
                effective_weight_percentage=0.0,
                dimension_score=score,
                explanation=explanation,
                is_included_in_score=True,
            ))

        # -------------------------------------------------------------
        # Dimension 5: Case Outcome (Pending Exclusion Rule)
        # -------------------------------------------------------------
        user_outcome = (req.outcome or "").strip()
        if user_outcome and "pending" not in user_outcome.lower():
            # If user case has a finalized outcome, display as comparable
            prec_outcome = precedent.outcome or precedent.disposition or "Decided"
            is_same = self._normalize_str(user_outcome) == self._normalize_str(prec_outcome)
            dimensions.append(DimensionComparisonResult(
                dimension_name="Outcome Comparability",
                user_value=user_outcome,
                precedent_value=prec_outcome,
                match_state="exact" if is_same else "different",
                weight_assigned=0.0,  # Informational bonus, doesn't dilute 4 core weights
                effective_weight_percentage=0.0,
                dimension_score=100.0 if is_same else 40.0,
                explanation=f"User case outcome is recorded as '{user_outcome}' compared to precedent outcome '{prec_outcome}'.",
                is_included_in_score=False,
            ))
        else:
            # Pending case: explicitly mark not_comparable and never count as mismatch
            dimensions.append(DimensionComparisonResult(
                dimension_name="Outcome Comparability",
                user_value="Pending / Unadjudicated",
                precedent_value=precedent.outcome or precedent.disposition or "Decided",
                match_state="not_comparable",
                weight_assigned=0.0,
                effective_weight_percentage=0.0,
                dimension_score=0.0,
                explanation="Your case is pending or outcome is unadjudicated. Excluded from score denominator to prevent penalizing ongoing litigation.",
                is_included_in_score=False,
            ))

        # -------------------------------------------------------------
        # Renormalize Active Dimension Weights
        # -------------------------------------------------------------
        active_dims = [d for d in dimensions if d.is_included_in_score]
        total_active_weight = sum(d.weight_assigned for d in active_dims)

        if total_active_weight > 0:
            for d in active_dims:
                d.effective_weight_percentage = round((d.weight_assigned / total_active_weight) * 100.0, 1)

            weighted_sum = sum(d.dimension_score * (d.weight_assigned / total_active_weight) for d in active_dims)
            overall_score = round(min(max(weighted_sum, 0.0), 100.0), 1)
        else:
            overall_score = 0.0

        precedent_summary = PrecedentSummary(
            case_id=precedent.id,
            title=precedent.title,
            case_no=precedent.case_no,
            court=precedent.court,
            year=precedent.year,
            source_url=precedent.source_url,
            file_hash=precedent.file_hash,
            precedential_status=precedent.precedential_status or "Precedential status not checked",
        )

        return CaseComparisonResponse(
            overall_score=overall_score,
            score_method="lexguard-deterministic-v1.0",
            dimensions=dimensions,
            precedent=precedent_summary,
        )

    def compare_multi(
        self,
        req: MultiCaseComparisonRequest,
        precedents: List[Case],
    ) -> MultiCaseComparisonResponse:
        """
        Executes parallel comparison of the user matter against 1 to 3 selected precedents.
        Calculates individual dimensional scores, cross-precedent statutory divergence,
        and identifies the highest-alignment ruling.
        """
        results: List[CaseComparisonResponse] = []
        best_id = None
        best_score = -1.0

        for prec in precedents:
            single_req = CaseComparisonRequest(
                precedent_case_id=prec.id,
                case_title=req.case_title,
                court_jurisdiction=req.court_jurisdiction,
                practice_area=req.practice_area,
                facts_summary=req.facts_summary,
                legal_issues=req.legal_issues,
                statutory_provisions=req.statutory_provisions,
                remedy_sought=req.remedy_sought,
                procedural_status=req.procedural_status,
                outcome=req.outcome,
            )
            res = self.compare_case(single_req, prec)
            results.append(res)
            if res.overall_score > best_score:
                best_score = res.overall_score
                best_id = prec.id

        # Build cross-statutory matrix
        user_provs = [p.strip() for p in (req.statutory_provisions or []) if p.strip()]
        statutory_matrix = {
            "user_provisions": user_provs,
            "precedents": [
                {
                    "case_id": prec.id,
                    "case_no": prec.case_no,
                    "title": prec.title,
                    "court": prec.court,
                    "year": prec.year,
                    "disposition": prec.disposition or prec.outcome or "Allowed",
                    "precedential_status": prec.precedential_status or "Good Law",
                    "act_tags": prec.act_tags or [],
                    "section_tags": prec.section_tags or [],
                    "ratio_decidendi": prec.ratio_decidendi or "",
                }
                for prec in precedents
            ],
        }

        return MultiCaseComparisonResponse(
            results=results,
            best_match_id=best_id,
            best_match_score=best_score if best_score >= 0.0 else 0.0,
            cross_statutory_matrix=statutory_matrix,
        )


comparison_service = CaseComparisonService()
