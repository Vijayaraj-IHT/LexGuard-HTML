"""
Comprehensive unit test suite for Step 2: LexGuard PDF Extraction Engine.
Validates Madras High Court (Principal Seat & Madurai Bench) layout parsing,
CNR bench mapping, dual dates normalization, verbatim prayer, counsel,
statutory sliding window extraction, dual IPC/BNS cross-referencing,
and Law Reporter summary generation.
"""

import os
import pytest
from app.services.extraction_service import (
    ExtractionService,
    VALID_DISPOSITIONS,
    PETITION_TYPE_LOOKUP,
    STATUTORY_CROSS_REFERENCES,
)


SEED_CORPUS_DIR = os.path.join(os.path.dirname(__file__), "..", "seed_corpus", "pdfs")


def test_madras_hc_madurai_bench_real_pdf():
    """Verify extraction on real Madurai Bench bail appeal PDF."""
    pdf_path = os.path.join(SEED_CORPUS_DIR, "01_crl-a-md-1150-2026.pdf")
    if not os.path.exists(pdf_path):
        pytest.skip("Seed PDF not found on disk")

    data = ExtractionService.extract_from_pdf(pdf_path, extract_passes=[1, 2, 3])

    # 1. Court & Bench
    assert data["court"] == "Madras High Court"
    assert data["bench"] == "Madurai Bench"
    assert data["cnr"] == "HCMD011350712026"
    assert "1150" in data["case_no"]
    assert data["year"] == 2026

    # 2. Coram & Bench Type
    assert "S.KARTHIKEYAN" in data["judge"]
    assert data["bench_type"] == "Single Bench"

    # 3. Litigants & Parties
    assert "Karuppasamy" in data["petitioner"]
    assert "State" in data["respondent"] or "Tamil Nadu" in data["respondent"]

    # 4. Counsel
    assert data["counsel_petitioner"] is not None
    assert "Palanisami" in data["counsel_petitioner"]
    assert data["counsel_respondent"] is not None
    assert "Government Advocate" in data["counsel_respondent"] or "Kumar" in data["counsel_respondent"]

    # 5. Dual Dates
    assert data["dates"]["date_pronounced"] == "2026-10-09"

    # 6. Verbatim Prayer
    assert "Section 14-A(2)" in data["prayer"]
    assert "SC/ST" in data["prayer"]
    assert "bail" in data["prayer"].lower()

    # 7. Disposition Enum
    assert data["disposition"] in VALID_DISPOSITIONS
    assert data["outcome"] == "Allowed"

    # 8. Statutory Tags & Sliding Window Extraction
    assert any("BNS" in a or "Bharatiya" in a for a in data["act_tags"])
    assert any("SC/ST" in a or "Scheduled" in a for a in data["act_tags"])
    assert len(data["section_tags"]) >= 4
    assert any("3(1)(r)" in s or "191(2)" in s or "14-A(2)" in s for s in data["section_tags"])
    assert len(data["canonical_sections"]) > 0

    # 9. Law Reporter Summary & Ratio Decidendi
    assert "[" in data["summary"] and "]" in data["summary"]
    assert "CRIMINAL APPEAL" in data["summary"]
    assert data["ratio_decidendi"] is not None
    assert data["legal_issue"] is not None
    assert data["overall_confidence"] >= 0.85


def test_madras_hc_principal_seat_real_pdf():
    """Verify extraction on real Principal Seat Chennai criminal original petition PDF."""
    pdf_path = os.path.join(SEED_CORPUS_DIR, "06_crl-op-26284-2026.pdf")
    if not os.path.exists(pdf_path):
        pytest.skip("Seed PDF not found on disk")

    data = ExtractionService.extract_from_pdf(pdf_path, extract_passes=[1, 2, 3])

    # 1. Court & Bench
    assert data["court"] == "Madras High Court"
    assert data["bench"] == "Principal Seat, Chennai"
    assert data["cnr"] == "HCMA012140432026"
    assert "26284" in data["case_no"]
    assert data["year"] == 2026

    # 2. Coram & Litigants
    assert "RAMESH" in data["judge"]
    assert "Silu Chhinchani" in data["petitioner"]

    # 3. Dates & Source URL
    assert data["dates"]["date_pronounced"] == "2026-10-09"
    assert "https://www.mhc.tn.gov.in/judis" in data["source_url"]

    # 4. Operative Disposition
    assert data["disposition"] in VALID_DISPOSITIONS
    assert data["outcome"] == "Allowed"

    # 5. Dual Statutory Cross-References (BNSS <-> CrPC)
    assert len(data["cross_reference_tags"]) > 0
    assert any("BNSS" in x or "CrPC" in x for x in data["cross_reference_tags"])


def test_dual_dates_normalization():
    """Verify date strings are converted to standard ISO YYYY-MM-DD."""
    assert ExtractionService._normalize_date_string("09-10-2026") == "2026-10-09"
    assert ExtractionService._normalize_date_string("01.10.2026") == "2026-10-01"
    assert ExtractionService._normalize_date_string("9/10/2026") == "2026-10-09"
    assert ExtractionService._normalize_date_string("9th October, 2026") == "2026-10-09"
    assert ExtractionService._normalize_date_string("09th day of October, 2026") == "2026-10-09"


def test_cnr_bench_mapping_heuristics():
    """Verify CNR prefix accurately determines the judicial bench."""
    test_madurai_text = """
    BEFORE THE MADURAI BENCH OF MADRAS HIGH COURT
    CORAM: THE HON'BLE MR.JUSTICE S.KARTHIKEYAN
    CRL OP(MD) No. 100 of 2026
    CNR: {TNMD010012342026}
    Petitioner .. Petitioner
    Vs
    State .. Respondent
    """
    data, _ = ExtractionService._pass1_structural(
        first_page=test_madurai_text,
        last_pages=test_madurai_text,
        full_text=test_madurai_text,
        page_count=1,
    )
    assert data["bench"] == "Madurai Bench"
    assert data["cnr"] == "TNMD010012342026"

    test_chennai_text = """
    IN THE HIGH COURT OF JUDICATURE AT MADRAS
    CORAM: THE HON'BLE MR.JUSTICE N.RAMESH
    CRL OP No. 200 of 2026
    CNR: {TNCH010056782026}
    Petitioner .. Petitioner
    Vs
    State .. Respondent
    """
    data_ch, _ = ExtractionService._pass1_structural(
        first_page=test_chennai_text,
        last_pages=test_chennai_text,
        full_text=test_chennai_text,
        page_count=1,
    )
    assert data_ch["bench"] == "Principal Seat, Chennai"
    assert data_ch["cnr"] == "TNCH010056782026"


def test_valid_disposition_constraint():
    """Verify disposition strictly conforms to the approved 7-item judicial enum."""
    for disp in VALID_DISPOSITIONS:
        assert disp in ["Allowed", "Dismissed", "Disposed", "Quashed", "Bail Granted", "Bail Rejected", "Remanded"]


# ---------------------------------------------------------------------------
# Date normalisation across registry date idioms
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("ORDER DATED: 30/10/2026", "2026-10-30"),
    ("17.08.2026", "2026-08-17"),
    ("21 September, 2020", "2020-09-21"),
    ("OCTOBER 22, 2026.", "2026-10-22"),                      # Bombay 'DATE :' line
    ("DATED THIS THE 14TH DAY OF OCTOBER, 2026", "2026-10-14"),  # Karnataka
    ("18TH DAY OF NOVEMBER 2022", "2022-11-18"),                # Kerala dual-era
    ("WEDNESDAY, THE 2nd DAY OF SEPTEMBER 2026", "2026-09-02"), # Telangana/Andhra
    ("Date of Decision: 30.10.2026", "2026-10-30"),
])
def test_date_idioms_normalise(raw, expected):
    assert ExtractionService._normalize_date_string(raw) == expected


def test_unparseable_date_returns_none():
    assert ExtractionService._normalize_date_string("sometime next week") is None


def test_extraction_passes_are_offline_and_deterministic(monkeypatch):
    """Ingestion must not call the AI microservice, Ollama, or load model weights."""
    pdf_path = os.path.join(SEED_CORPUS_DIR, "01_crl-a-md-1150-2026.pdf")
    if not os.path.exists(pdf_path):
        pytest.skip("Seed PDF not found on disk")

    from app.services.ai_api_service import ai_api_service
    from app.services.local_llm_service import local_llm_service

    def forbid_network_or_model(*args, **kwargs):
        raise AssertionError("offline ingestion attempted a network/model call")

    for method in ("check_health", "extract_ner", "summarize", "extract_ratio"):
        monkeypatch.setattr(ai_api_service, method, forbid_network_or_model, raising=False)
    monkeypatch.setattr(local_llm_service, "summarize_judgment", forbid_network_or_model, raising=False)
    monkeypatch.setattr(local_llm_service, "_load_model", forbid_network_or_model, raising=False)
    monkeypatch.setattr(local_llm_service, "_call_ollama", forbid_network_or_model, raising=False)

    first = ExtractionService.extract_from_pdf(pdf_path, extract_passes=[1, 2, 3])
    second = ExtractionService.extract_from_pdf(pdf_path, extract_passes=[1, 2, 3])

    keys = [
        "court", "bench", "case_no", "year", "cnr", "judge", "petitioner",
        "respondent", "dates", "prayer", "outcome", "disposition", "facts",
        "fact_sheet", "section_map", "act_tags", "section_tags", "summary",
        "ratio_decidendi", "overall_confidence",
    ]
    assert {k: first.get(k) for k in keys} == {k: second.get(k) for k in keys}
    assert first["confidence_scores"]["act_tags"]["source"] == "pass2_regex"
    assert first["confidence_scores"]["summary"]["source"] == "pass3_deterministic"
    assert first["fact_sheet"].get("police_stations") is not None
