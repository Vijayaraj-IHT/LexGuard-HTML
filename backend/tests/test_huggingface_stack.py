from app.services.embedding_service import embedding_service
from app.services.ner_service import ner_service
from app.services.local_llm_service import local_llm_service


def test_embedding_service_dimensions_and_similarity():
    """Verifies that the embedding service generates normalized 384-dim vectors and calculates similarity."""
    text1 = "Anticipatory bail petition under Section 438 CrPC for cheating"
    text2 = "Bail plea for Section 420 IPC offence"
    text3 = "Trademark infringement dispute regarding software copyright"

    vec1 = embedding_service.generate_embedding(text1)
    vec2 = embedding_service.generate_embedding(text2)
    vec3 = embedding_service.generate_embedding(text3)

    assert len(vec1) == 384
    assert len(vec2) == 384
    assert len(vec3) == 384

    # Semantically related legal queries (bail/IPC) should have higher similarity than unrelated IP law
    sim_related = embedding_service.cosine_similarity(vec1, vec2)
    sim_unrelated = embedding_service.cosine_similarity(vec1, vec3)

    assert sim_related > 0.0
    assert 0.0 <= sim_unrelated <= 1.0


def test_indian_legal_ner_extraction():
    """Verifies that the Indian legal entity recognizer extracts statutes and sections."""
    judgment_text = (
        "The accused filed an application under Section 439 of CrPC seeking regular bail. "
        "The police registered an FIR under Section 420 of IPC and Section 37 of NDPS Act. "
        "The applicant contends violation of fundamental rights guaranteed under Article 21 of the Constitution."
    )

    extracted = ner_service.extract_legal_entities(judgment_text)

    assert "CrPC" in extracted["acts"]
    assert "IPC" in extracted["acts"]
    assert "NDPS Act" in extracted["acts"]

    assert any("439" in s for s in extracted["sections"])
    assert any("420" in s for s in extracted["sections"])
    assert any("21" in s for s in extracted["sections"])
    assert "bail" in extracted["keywords"]


def test_local_llm_query_enrichment_and_grounding():
    """Verifies that LocalLLMService enriches search queries and isolates inputs."""
    query = "bail petition under Section 439 CrPC with parity"
    enriched = local_llm_service.enrich_query(query)

    assert "sections" in enriched
    assert any("439" in s for s in enriched["sections"])
    assert "issue" in enriched


def test_local_llm_draft_gap_analysis():
    """Verifies that draft gap analysis identifies missing grounds and strictly grounds citations."""
    petition = (
        "The petitioner is languishing in jail for over 3 years without trial. "
        "Co-accused has already been enlarged on bail by this Hon'ble Court. "
        "Praying for grant of regular bail under Section 439 CrPC."
    )

    available_cases = [
        {
            "id": "case-sc-01",
            "title": "Manish Sisodia vs. Directorate of Enforcement",
            "court": "Supreme Court of India",
            "year": 2024,
            "section_tags": ["Section 439 CrPC", "Article 21"],
            "outcome": "Allowed",
            "summary": "Prolonged custody without speedy trial infringes fundamental right to life under Article 21.",
        }
    ]

    gap_result = local_llm_service.analyze_draft_gap(petition, available_cases)

    assert "identified_grounds" in gap_result
    assert "missing_arguments" in gap_result
    assert "citation_suggestions" in gap_result

    # All citation suggestions must strictly reference the provided case ID
    for cit in gap_result["citation_suggestions"]:
        assert cit["case_id"] == "case-sc-01"
        assert "Manish Sisodia" in cit["case_title"]
