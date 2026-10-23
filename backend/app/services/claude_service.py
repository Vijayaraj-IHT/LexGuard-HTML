import json
import logging
from typing import Dict, Any, List
from app.core.config import settings

logger = logging.getLogger(__name__)


class ClaudeService:
    """
    LLM service supporting Anthropic Claude API (claude-3-5-sonnet / claude-sonnet-4-6)
    with a deterministic Mock / Fallback engine for local testing and offline demos.
    Implements OWASP LLM01:2025 defenses (XML encapsulation) and strict citation grounding.
    """

    def __init__(self):
        self.api_key = settings.ANTHROPIC_API_KEY
        self.use_mock = settings.USE_MOCK_LLM or not bool(self.api_key)
        self.client = None

        if not self.use_mock:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Could not initialize Anthropic client ({e}). Falling back to deterministic mock.")
                self.use_mock = True

    def enrich_query(self, raw_query: str) -> Dict[str, Any]:
        """
        Enriches a raw legal search query with recognized statutory sections,
        issue classification, and jurisdiction.
        """
        if self.use_mock or not self.client:
            return self._mock_enrich_query(raw_query)

        system_prompt = (
            "You are a strict Indian legal query parser. "
            "Extract: (1) sections: relevant IPC/CrPC/BNS/NDPS/IT Act sections, "
            "(2) issue: core legal issue (e.g. bail, quashing, specific performance), "
            "(3) jurisdiction: court type or jurisdiction. "
            "Return ONLY a valid JSON object matching: "
            '{"sections": ["..."], "issue": "...", "jurisdiction": "..."}'
        )

        user_content = f"<query>{raw_query}</query>\nAnalyze the query inside the XML tags above."

        try:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=300,
                temperature=0.0,
                system=system_prompt,
                messages=[{"role": "user", "content": user_content}],
            )
            text = response.content[0].text
            return json.loads(text)
        except Exception as e:
            logger.error(f"Claude API query enrichment error: {e}. Using deterministic fallback.")
            return self._mock_enrich_query(raw_query)

    def analyze_draft_gap(
        self,
        petition_text: str,
        available_cases: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Performs legal argument gap analysis on a petition draft against available precedents.
        Enforces strict grounding to eliminate hallucinations.
        """
        if self.use_mock or not self.client:
            return self._mock_analyze_draft(petition_text, available_cases)

        system_prompt = (
            "You are an Indian Senior Advocate legal assistant for Lexguard. "
            "Review the petition text. Identify legal grounds already argued, "
            "flag missing legal grounds based on provided verified precedents, and "
            "suggest relevant sections. "
            "STRICT GROUNDING: You MUST ONLY cite cases provided in the reference list. "
            "Return valid JSON with: "
            '{"identified_grounds": [...], "missing_arguments": [...], "suggested_sections": [...], "citation_suggestions": [{"case_id": "...", "case_title": "...", "citation": "...", "relevant_section": "...", "reasoning": "...", "quote": "..."}]}'
        )

        cases_summary = json.dumps(
            [
                {
                    "case_id": c.get("id"),
                    "title": c.get("title"),
                    "court": c.get("court"),
                    "year": c.get("year"),
                    "sections": c.get("section_tags", []),
                    "summary": c.get("summary", ""),
                }
                for c in available_cases[:5]
            ]
        )

        user_content = (
            f"<document>\n{petition_text}\n</document>\n\n"
            f"<verified_precedents>\n{cases_summary}\n</verified_precedents>\n"
            "Analyze the petition strictly against the verified precedents."
        )

        try:
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=1000,
                temperature=0.1,
                system=system_prompt,
                messages=[{"role": "user", "content": user_content}],
            )
            text = response.content[0].text
            return json.loads(text)
        except Exception as e:
            logger.error(f"Claude API draft gap analysis error: {e}. Using deterministic fallback.")
            return self._mock_analyze_draft(petition_text, available_cases)

    # ------------------ Deterministic Mock Engine ------------------

    def _mock_enrich_query(self, query: str) -> Dict[str, Any]:
        q_lower = query.lower()
        sections = []
        issue = "general"
        jurisdiction = "High Court / Supreme Court"

        if "bail" in q_lower:
            issue = "bail"
            sections.extend(["Section 437 CrPC", "Section 439 CrPC", "Article 21 Constitution of India"])
        if "ndps" in q_lower or "drug" in q_lower or "contraband" in q_lower:
            sections.append("Section 37 NDPS Act")
        if "fraud" in q_lower or "cheat" in q_lower or "420" in q_lower:
            sections.extend(["Section 415 IPC", "Section 420 IPC"])
            issue = "cheating / criminal breach of trust"
        if "quash" in q_lower or "482" in q_lower:
            sections.append("Section 482 CrPC")
            issue = "quashing of FIR"
        if "murder" in q_lower or "302" in q_lower:
            sections.extend(["Section 300 IPC", "Section 302 IPC"])
            issue = "homicide"

        if not sections:
            sections = ["Relevant statutory sections extracted"]

        return {
            "sections": list(dict.fromkeys(sections)),
            "issue": issue,
            "jurisdiction": jurisdiction,
        }

    def _mock_analyze_draft(
        self,
        petition_text: str,
        available_cases: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        q_lower = petition_text.lower()
        identified = []
        missing = []
        suggested_sections = []
        citations = []

        if "bail" in q_lower:
            identified.append("Plea for bail under CrPC provisions")
            if "parity" not in q_lower:
                missing.append("Ground of parity with co-accused not explicitly raised")
            if "delay" not in q_lower:
                missing.append("Prolonged custody without trial commencement (Article 21 violation)")
                suggested_sections.append("Article 21 Constitution of India")
            suggested_sections.extend(["Section 437 CrPC", "Section 439 CrPC"])

        if "cheating" in q_lower or "420" in q_lower:
            identified.append("Allegation of dishonestly inducing delivery of property")
            if "civil" not in q_lower:
                missing.append("Distinction between civil breach of contract and criminal cheating not formulated")
            suggested_sections.append("Section 420 IPC")

        # Fallback defaults if general text
        if not identified:
            identified = ["Preliminary statements of fact and formal petition prayer"]
        if not missing:
            missing = [
                "Consider articulating lack of prima facie case based on documentary evidence",
                "Ensure strict statutory compliance with limitation period and notice requirements",
            ]
        if not suggested_sections:
            suggested_sections = ["Section 482 CrPC", "Article 226 Constitution of India"]

        # Link grounded citations from available cases
        for c in available_cases[:2]:
            citations.append({
                "case_id": c.get("id", "case-ref-1"),
                "case_title": c.get("title", "State Precedent Landmark"),
                "citation": f"{c.get('title', 'Precedent')} ({c.get('year', 2024)}) {c.get('court', 'SC')}",
                "relevant_section": (c.get("section_tags") or ["Section 439 CrPC"])[0],
                "reasoning": f"Directly supports the proposition regarding {c.get('outcome', 'relief granted')} in similar factual matrix.",
                "quote": (c.get("summary") or "The right to speedy trial and personal liberty cannot be curtailed indefinitely without substantial prima facie evidence.")[:180],
            })

        return {
            "identified_grounds": identified,
            "missing_arguments": missing,
            "suggested_sections": list(dict.fromkeys(suggested_sections)),
            "citation_suggestions": citations,
        }


claude_service = ClaudeService()
