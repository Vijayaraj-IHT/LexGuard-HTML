import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_compare_multi_with_published_precedents():
    """Verify comparing user matter against 1 to 3 precedents simultaneously."""
    # Fetch available published precedents
    prec_resp = client.get("/api/v1/comparison/precedents")
    assert prec_resp.status_code == 200
    precedents = prec_resp.json()
    if not precedents:
        pytest.skip("No published precedents in database for multi-comparison test")

    selected_ids = [p["id"] for p in precedents[:min(3, len(precedents))]]

    payload = {
        "precedent_case_ids": selected_ids,
        "case_title": "Bail Application of Raman v. State (Madras HC)",
        "court_jurisdiction": "High Court of Judicature at Madras",
        "practice_area": "Criminal Law",
        "facts_summary": "Petitioner detained under Section 438 without statutory notice under 41A CrPC.",
        "legal_issues": ["Whether anticipatory bail is maintainable during active interrogation?"],
        "statutory_provisions": ["Section 438 CrPC", "Section 41A CrPC"],
        "remedy_sought": "Anticipatory Bail",
        "procedural_status": "Pre-arrest Investigation",
        "outcome": "Pending (Sub Judice)",
    }

    response = client.post("/api/v1/comparison/compare-multi", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "results" in data
    assert len(data["results"]) == len(selected_ids)
    assert "best_match_id" in data
    assert data["best_match_id"] in selected_ids
    assert "best_match_score" in data
    assert isinstance(data["best_match_score"], (int, float))
    assert 0.0 <= data["best_match_score"] <= 100.0

    # Cross statutory matrix validation
    assert "cross_statutory_matrix" in data
    matrix = data["cross_statutory_matrix"]
    assert "user_provisions" in matrix
    assert "precedents" in matrix
    assert len(matrix["precedents"]) == len(selected_ids)


def test_compare_multi_boundary_limits():
    """Verify rejection when precedent_case_ids is empty or exceeds 3 items."""
    # 0 precedents -> 422
    payload_empty = {
        "precedent_case_ids": [],
        "case_title": "Test Case",
    }
    resp_empty = client.post("/api/v1/comparison/compare-multi", json=payload_empty)
    assert resp_empty.status_code == 422

    # > 3 precedents -> 422
    payload_too_many = {
        "precedent_case_ids": ["id-1", "id-2", "id-3", "id-4"],
        "case_title": "Test Case",
    }
    resp_too_many = client.post("/api/v1/comparison/compare-multi", json=payload_too_many)
    assert resp_too_many.status_code == 422


def test_compare_multi_nonexistent_precedent():
    """Verify 404 when nonexistent or unpublished precedent IDs are provided."""
    payload = {
        "precedent_case_ids": ["non-existent-case-id-99999"],
        "case_title": "Test Case",
    }
    resp = client.post("/api/v1/comparison/compare-multi", json=payload)
    assert resp.status_code == 404
    assert "None of the specified precedents were found" in resp.json()["detail"]
