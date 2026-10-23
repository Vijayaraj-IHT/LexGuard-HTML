import re
import uuid
from typing import List, Dict, Any
from app.models.case import Case


class PrecedentComparatorService:
    """
    3-Layer Precision Precedent Comparator:
    Layer 1: Statutory Conditions Audit (fulfilled vs omitted tests)
    Layer 2: Ratio Alignment (prayer & legal grounds alignment with binding ratio)
    Layer 3: Actionable Drafting Suggestions (1-click insertable boilerplate paragraphs)
    """

    STOPWORDS = {
        "the", "of", "and", "a", "to", "in", "is", "that", "it", "with", "as", "for", "was",
        "on", "are", "by", "this", "be", "or", "from", "at", "which", "an", "under", "court",
        "order", "shall", "any", "all", "must"
    }

    def _extract_keywords(self, text: str) -> set:
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        return {w for w in words if w not in self.STOPWORDS}

    def _find_matching_snippet(self, draft_text: str, keywords: set) -> str:
        sentences = re.split(r'[.\n;]+', draft_text)
        best_sentence = ""
        max_matches = 0

        for sentence in sentences:
            sentence_clean = sentence.strip()
            if not sentence_clean:
                continue
            s_words = set(re.findall(r'\b[a-zA-Z]{3,}\b', sentence_clean.lower()))
            common = s_words.intersection(keywords)
            if len(common) > max_matches:
                max_matches = len(common)
                best_sentence = sentence_clean

        if max_matches >= 2:
            return best_sentence[:200]
        return ""

    def audit_statutory_conditions(self, draft_text: str, statutory_tests: List[str]) -> List[Dict[str, Any]]:
        audit_results = []
        draft_lower = draft_text.lower()

        for test in statutory_tests:
            test_keywords = self._extract_keywords(test)
            matched_snippet = self._find_matching_snippet(draft_text, test_keywords)

            # Check direct phrase or high keyword overlap
            matched = False
            if matched_snippet:
                matched = True
            else:
                # Secondary check for key root terms
                overlap_count = sum(1 for kw in test_keywords if kw in draft_lower)
                if len(test_keywords) > 0 and (overlap_count / len(test_keywords)) >= 0.4:
                    matched = True
                    matched_snippet = f"Relevant ground identified addressing statutory condition: '{test[:80]}...'"

            if matched:
                audit_results.append({
                    "test": test,
                    "status": "fulfilled",
                    "matched_clause": matched_snippet if matched_snippet else "Addressed in petition grounds.",
                    "recommendation": None
                })
            else:
                audit_results.append({
                    "test": test,
                    "status": "omitted",
                    "matched_clause": None,
                    "recommendation": f"Add an explicit averment/ground addressing: '{test}' to align with the binding test in this precedent."
                })

        return audit_results

    def check_ratio_alignment(self, draft_text: str, case: Case) -> Dict[str, Any]:
        ratio = case.ratio_decidendi or case.summary or ""
        ratio_keywords = self._extract_keywords(ratio)
        draft_keywords = self._extract_keywords(draft_text)

        overlap = ratio_keywords.intersection(draft_keywords)
        overlap_ratio = len(overlap) / max(len(ratio_keywords), 1)

        # Look for explicit prayers or grounds keywords
        has_prayer = bool(re.search(r'\b(pray|prayed|prayer|quash|grant|bail|set aside|declare|relief)\b', draft_text, re.I))
        has_violation_claim = bool(re.search(r'\b(arbitrary|violation|illegal|contrary|failed to|unlawful|unconstitutional)\b', draft_text, re.I))

        # Base score on overlap and structure
        score = min(round((overlap_ratio * 120) + (15 if has_prayer else 0) + (15 if has_violation_claim else 0), 1), 100.0)

        if score >= 65.0:
            status = "strong_alignment"
            analysis = (
                f"The draft petition demonstrates strong doctrinal alignment with the binding ratio of {case.title}. "
                f"The grounds directly rely on core principles of {', '.join(case.section_tags or ['the relevant enactments'])} "
                f"and reflect the procedural mandates affirmed by the {case.court}."
            )
        elif score >= 35.0:
            status = "partial_alignment"
            analysis = (
                f"The draft partially aligns with {case.title}, but key judicial arguments from the ratio decidendi "
                f"are underdeveloped. While statutory subject matter is referenced, the specific legal tests established "
                f"by the {case.court} should be articulated more explicitly."
            )
        else:
            status = "divergent"
            analysis = (
                f"The draft currently diverges or lacks essential legal touchpoints established in {case.title}. "
                f"To strengthen maintainability, the advocate should incorporate the ratio decidendi and statutory prerequisite "
                f"clauses provided below."
            )

        return {
            "alignment_status": status,
            "alignment_score": score,
            "analysis": analysis,
            "binding_principle": ratio
        }

    def generate_boilerplate_suggestions(self, draft_text: str, case: Case, statutory_audit: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        suggestions = []
        omitted_tests = [item["test"] for item in statutory_audit if item["status"] == "omitted"]
        sections_str = ", ".join(case.section_tags) if case.section_tags else "the relevant statute"
        acts_str = ", ".join(case.act_tags) if case.act_tags else "law"

        # 1. Ground Clause
        suggestions.append({
            "id": f"sug-{uuid.uuid4().hex[:8]}",
            "title": f"Precedent Ground based on {case.title}",
            "clause_type": "Ground",
            "content": (
                f"FOR THAT the impugned actions/order of the Respondent run directly contrary to the binding law "
                f"and ratio decidendi laid down by the Hon'ble {case.court} in {case.title} [{case.case_no}], "
                f"wherein the Court categorically held that: \"{case.ratio_decidendi or case.summary}\". "
                f"The Respondent's failure to adhere to the mandate of {sections_str} renders the entire proceedings "
                f"manifestly illegal, void ab initio, and liable to be quashed."
            )
        })

        # 2. Statutory Audit Averment (addressing omitted tests)
        if omitted_tests:
            checklist_items = "; ".join([f"({chr(97 + idx)}) {t}" for idx, t in enumerate(omitted_tests[:3])])
            suggestions.append({
                "id": f"sug-{uuid.uuid4().hex[:8]}",
                "title": f"Statutory Compliance Averment ({case.title} Checklist)",
                "clause_type": "Averment",
                "content": (
                    f"That the Petitioner respectfully submits that in accordance with the mandatory judicial tests "
                    f"established in {case.title}, the authorities were under an inviolable legal obligation to satisfy: "
                    f"{checklist_items}. In the present case, not a single prerequisite was fulfilled, resulting in "
                    f"grave prejudice and irreparable infringement of statutory and constitutional rights."
                )
            })

        # 3. Actionable Prayer Clause
        disposition_relief = "grant appropriate statutory relief"
        if case.disposition == "Quashed":
            disposition_relief = "quash and set aside the impugned order / proceedings"
        elif case.disposition in ("Allowed", "Partly Allowed"):
            disposition_relief = f"allow the petition and grant relief strictly in conformity with the law declared in {case.title}"
        elif case.outcome and "bail" in case.outcome.lower():
            disposition_relief = "grant regular / anticipatory bail to the Petitioner on suitable terms"

        suggestions.append({
            "id": f"sug-{uuid.uuid4().hex[:8]}",
            "title": "Tailored Prayer Clause",
            "clause_type": "Prayer",
            "content": (
                f"In the light of the above facts, grounds, and the settled principle of law enunciated by the "
                f"Hon'ble {case.court} in {case.title}, it is most respectfully prayed that this Hon'ble Court may "
                f"graciously be pleased to: (i) {disposition_relief}; and (ii) pass such further or other orders as this "
                f"Hon'ble Court may deem fit and proper in the interests of justice."
            )
        })

        return suggestions

    def compare(self, draft_text: str, case: Case) -> Dict[str, Any]:
        statutory_audit = self.audit_statutory_conditions(draft_text, case.statutory_tests or [])
        ratio_alignment = self.check_ratio_alignment(draft_text, case)
        boilerplate_suggestions = self.generate_boilerplate_suggestions(draft_text, case, statutory_audit)

        total_tests = len(statutory_audit)
        fulfilled_count = sum(1 for item in statutory_audit if item["status"] == "fulfilled")
        omitted_count = total_tests - fulfilled_count
        compliance_pct = round((fulfilled_count / max(total_tests, 1)) * 100, 1)

        return {
            "case_id": case.id,
            "case_title": case.title,
            "citation": getattr(case, "case_no", None),
            "court": case.court,
            "year": case.year,
            "ratio_decidendi": case.ratio_decidendi or case.summary or "Binding precedent principle.",
            "statutory_audit": statutory_audit,
            "total_tests": total_tests,
            "fulfilled_count": fulfilled_count,
            "omitted_count": omitted_count,
            "compliance_percentage": compliance_pct,
            "ratio_alignment": ratio_alignment,
            "boilerplate_suggestions": boilerplate_suggestions
        }


precedent_comparator = PrecedentComparatorService()
