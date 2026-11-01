import pytest
from app.models.case import Case
from app.services.comparator import PrecedentComparatorService, precedent_comparator


@pytest.fixture
def mock_landmark_case():
    return Case(
        id="case-test-shreya-singhal",
        case_no="W.P. (Crl.) No. 167 of 2012",
        title="Shreya Singhal v. Union of India",
        court="Supreme Court of India",
        year=2015,
        summary="Struck down Section 66A of the Information Technology Act for violating Article 19(1)(a).",
        ratio_decidendi="The Court held that liberty of thought and expression cannot be suppressed on vague assertions of causing annoyance or inconvenience. Section 66A IT Act violates Article 19(1)(a).",
        statutory_tests=[
            "Proximity of speech to public disorder or state security under Article 19(2)",
            "Absence of overbreadth, chilling effect, or unconstitutional vagueness in statutory terms",
            "Intermediary safe harbor immunity conditioned on actual court order or government takedown request",
            "Adherence to procedural safeguards and review committee oversight for digital blocking"
        ],
        issues_framed=[
            "Whether Section 66A of IT Act infringes freedom of speech under Article 19(1)(a)?",
            "Whether restrictions satisfy the reasonable restriction test under Article 19(2)?"
        ],
        disposition="Quashed",
        precedents_cited=["Romesh Thappar v. State of Madras", "Maneka Gandhi v. Union of India"],
        section_tags=["Section 66A IT Act", "Article 19(1)(a)"],
        act_tags=["Information Technology Act, 2000", "Constitution of India"]
    )


def test_keyword_extraction():
    service = PrecedentComparatorService()
    text = "The petitioner claims violation of free speech under Article 19(1)(a) of the Constitution."
    keywords = service._extract_keywords(text)
    assert "petitioner" in keywords
    assert "violation" in keywords
    assert "speech" in keywords
    assert "the" not in keywords
    assert "under" not in keywords


def test_layer1_statutory_conditions_audit(mock_landmark_case):
    service = PrecedentComparatorService()
    
    # Draft mentions public disorder and article 19(2), but omits intermediary safe harbor
    draft_text = (
        "The respondent acted arbitrarily. The speech had no proximity to public disorder or state security "
        "under Article 19(2). Furthermore, the statutory phrasing suffers from gross overbreadth and vagueness."
    )
    
    audit = service.audit_statutory_conditions(draft_text, mock_landmark_case.statutory_tests)
    assert len(audit) == len(mock_landmark_case.statutory_tests)
    
    # Check that public disorder test is marked fulfilled
    fulfilled_tests = [item for item in audit if item["status"] == "fulfilled"]
    omitted_tests = [item for item in audit if item["status"] == "omitted"]
    
    assert len(fulfilled_tests) >= 1
    assert len(omitted_tests) >= 1
    assert any("public disorder" in item["test"].lower() for item in fulfilled_tests)
    assert any("safe harbor" in item["test"].lower() for item in omitted_tests)


def test_layer2_ratio_decidendi_alignment(mock_landmark_case):
    service = PrecedentComparatorService()
    
    # Highly aligned draft
    aligned_draft = (
        "It is respectfully submitted that freedom of speech and expression cannot be suppressed on vague "
        "assertions of annoyance or inconvenience. We pray to quash the impugned notice violating Article 19(1)(a)."
    )
    result = service.check_ratio_alignment(aligned_draft, mock_landmark_case)
    assert result["alignment_score"] > 35.0
    assert result["alignment_status"] in ("strong_alignment", "partial_alignment")
    assert "Shreya Singhal" in result["analysis"]
    assert len(result["binding_principle"]) > 0


def test_layer3_boilerplate_generation(mock_landmark_case):
    service = PrecedentComparatorService()
    draft_text = "The petitioner seeks relief against the impugned action."
    
    statutory_audit = service.audit_statutory_conditions(draft_text, mock_landmark_case.statutory_tests)
    suggestions = service.generate_boilerplate_suggestions(draft_text, mock_landmark_case, statutory_audit)
    
    assert len(suggestions) >= 2
    types = {s["clause_type"] for s in suggestions}
    assert "Ground" in types
    assert "Prayer" in types
    
    # Verify content contains precedent details
    ground_clause = next(s for s in suggestions if s["clause_type"] == "Ground")
    assert "Shreya Singhal" in ground_clause["content"]
    assert "Supreme Court of India" in ground_clause["content"]


def test_full_precedent_comparator_orchestration(mock_landmark_case):
    draft_text = (
        "The petitioner challenges the coercive notice under Section 66A. "
        "It is prayed to quash and set aside the proceedings due to lack of proximity to public disorder."
    )
    
    result = precedent_comparator.compare(draft_text=draft_text, case=mock_landmark_case)
    
    assert result["case_id"] == mock_landmark_case.id
    assert result["case_title"] == mock_landmark_case.title
    assert result["total_tests"] == 4
    assert result["fulfilled_count"] >= 1
    assert result["omitted_count"] >= 1
    assert 0 <= result["compliance_percentage"] <= 100
    assert "ratio_alignment" in result
    assert len(result["boilerplate_suggestions"]) >= 2
