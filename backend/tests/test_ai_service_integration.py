"""
Integration and Unit Tests for LexGuard AI Microservice & Client.
Validates:
1. LegalNEREngine entity and statute extraction.
2. LegalEmbeddingEngine 384-dimensional dense vector embeddings.
3. LegalSummarizationEngine abstractive summary generation.
4. RatioExtractionEngine ratio decidendi synthesis.
5. GapAnalysisEngine draft petition gap and weakness analysis.
6. AIApiService fallback and client interface.
7. Multi-pass ExtractionService integrating AI intelligence.
"""

import os
import sys
import pytest

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ai_service.models import (
    ner_engine,
    embedding_engine,
    summarization_engine,
    ratio_engine,
    gap_engine,
)
from ai_service.schemas import PrecedentItem
from app.services.ai_api_service import ai_api_service
from app.services.extraction_service import ExtractionService


SAMPLE_JUDGMENT = """
CRL OP No. 26284 of 2026
IN THE HIGH COURT OF JUDICATURE AT MADRAS
DATED: 09-10-2026
CORAM
THE HON'BLE MR.JUSTICE N.RAMESH
CRL OP No. 26284 of 2026
CNR: {HCMA012140432026}
Silu Chhinchani
..Petitioner(s)
Vs
State Rep.by,
The Inspector of Police
PEW - Tambaram Police Station,
Tambaram, Cr.No.52 of 2025.
..Respondent(s)
PRAYER: This criminal original petition filed under Section 482 BNSS Act to
enlarge on bail in CC.No.758 of 2025 in Cr.No.52 of 2025 pending on the file
of the I Additional Special Judge, Special Court for EC and NDPS Act,
Chennai.
For Petitioner(s): Mr.S.Karthikeyan
For Respondent(s): Mr.E.Raj Thilak, Additional Public Prosecutor
ORDER
16. Accordingly, this Criminal Original Petition is allowed and the
petitioner is ordered to be released on bail on his executing a bond.
https://www.mhc.tn.gov.in/judis
"""


def test_ner_engine_extraction():
    """Verify LegalNEREngine extracts acts, sections, judges, and parties."""
    res = ner_engine.extract_entities(SAMPLE_JUDGMENT, court_context="Madras High Court")
    assert any("BNSS" in s or "482" in s for s in res.sections)
    assert any("NDPS" in a or "BNSS" in a for a in res.acts)
    assert any("N.RAMESH" in j for j in res.judges)
    assert "Silu Chhinchani" in res.parties
    assert len(res.entities) > 0


def test_embedding_engine():
    """Verify LegalEmbeddingEngine outputs normalized 384-dimensional vectors."""
    texts = ["Anticipatory bail petition under Section 482 BNSS", "Commercial quantity NDPS contraband seizure"]
    res = embedding_engine.embed_texts(texts)
    assert len(res.embeddings) == 2
    assert res.dimension == 384
    assert len(res.embeddings[0]) == 384
    # Check normalization: sum of squares ≈ 1.0
    norm = sum(x * x for x in res.embeddings[0])
    assert abs(norm - 1.0) < 0.05


def test_summarization_engine():
    """Verify LegalSummarizationEngine produces legal abstracts."""
    res = summarization_engine.summarize(
        text=SAMPLE_JUDGMENT,
        max_sentences=2,
        court="Madras High Court",
        case_no="CRL OP No. 26284 of 2026",
    )
    assert "Madras High Court" in res.summary
    assert "CRL OP No. 26284 of 2026" in res.summary
    assert res.sentence_count <= 2


def test_ratio_extraction_engine():
    """Verify RatioExtractionEngine identifies core ratio decidendi."""
    res = ratio_engine.extract_ratio(
        text=SAMPLE_JUDGMENT,
        prayer="enlarge on bail under Section 482 BNSS",
        outcome="Allowed",
        acts_cited=["NDPS Act", "BNSS Act"],
    )
    assert res.ratio_decidendi is not None
    assert "NDPS Act" in res.ratio_decidendi or "statutory" in res.ratio_decidendi
    assert res.binding_nature in ("Binding Precedent", "Persuasive Ruling")


def test_gap_analysis_engine():
    """Verify GapAnalysisEngine detects missing statutory sections and arguments."""
    draft_petition = """
    IN THE HIGH COURT OF JUDICATURE AT MADRAS
    CRIMINAL ORIGINAL PETITION
    The petitioner is an innocent citizen wrongfully arrested in connection with a commercial transaction.
    The police failed to follow proper investigation guidelines.
    WHEREFORE, the petitioner prays that this Hon'ble Court may be pleased to grant bail.
    """

    precedents = [
        PrecedentItem(
            title="State of Haryana v. Bhajan Lal",
            court="Supreme Court of India",
            ratio="Quashing guidelines under CrPC Section 482",
            sections=["Section 482 CrPC", "Section 41A CrPC"],
        )
    ]

    res = gap_engine.analyze_gap(draft_text=draft_petition, precedents=precedents)
    assert 0.0 <= res.alignment_score <= 1.0
    assert "Section 41A CrPC" in res.missing_sections or len(res.missing_sections) > 0
    assert len(res.recommendations) > 0


def test_ai_api_service_fallback():
    """Verify AIApiService graceful in-process fallback when microservice is offline."""
    ner = ai_api_service.extract_ner("Section 482 BNSS Act and Section 37 NDPS Act")
    assert any("482" in s for s in ner["sections"])
    assert any("NDPS" in a or "BNSS" in a for a in ner["acts"])

    vecs = ai_api_service.generate_embeddings(["Bail application"])
    assert len(vecs) == 1
    assert len(vecs[0]) == 384


def test_extraction_service_with_ai():
    """Verify 3-pass extraction pipeline processes court text with AI intelligence."""
    data, confidence = ExtractionService._pass1_structural(
        first_page=SAMPLE_JUDGMENT,
        last_pages=SAMPLE_JUDGMENT,
        full_text=SAMPLE_JUDGMENT,
        page_count=1,
    )
    data, confidence = ExtractionService._pass2_statutes_and_ner(data, confidence, SAMPLE_JUDGMENT)
    data, confidence = ExtractionService._pass3_ratio_and_summary(data, confidence, SAMPLE_JUDGMENT)

    assert "Madras High Court" in data["court"]
    assert "Allowed" in data["outcome"]
    assert len(data["section_tags"]) > 0
    assert data["summary"] is not None
    assert data["ratio_decidendi"] is not None
