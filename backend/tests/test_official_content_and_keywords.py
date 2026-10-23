import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.models.case import Case

client = TestClient(app)


def test_official_case_content_endpoint():
    """Verify official content returns pages, word counts and hash."""
    db = SessionLocal()
    case = db.query(Case).filter(Case.full_text != None).first()
    db.close()

    assert case is not None, "At least one case with full_text should be seeded"

    response = client.get(
        f"/api/v1/cases/{case.id}/official-content",
        headers={"Cookie": "lexguard_user_role=advocate"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == case.id
    assert data["page_count"] >= 1
    assert data["total_words"] > 0
    assert len(data["pages"]) >= 1
    assert "page" in data["pages"][0]
    assert "content" in data["pages"][0]


def test_search_keywords_in_case_endpoint():
    """Verify in-document keyword search returns page number and highlighted snippet."""
    db = SessionLocal()
    case = db.query(Case).filter(Case.full_text != None).first()
    db.close()

    assert case is not None

    # Pick a common word from the case's title or text
    query_word = case.title.split()[0]
    response = client.get(
        f"/api/v1/cases/{case.id}/search-keywords?q={query_word}",
        headers={"Cookie": "lexguard_user_role=advocate"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == case.id
    assert data["query"] == query_word
    assert data["total_matches"] >= 1
    assert len(data["pages_matched"]) >= 1
    assert "<mark>" in data["occurrences"][0]["snippet"]


def test_global_search_returns_official_snippets():
    """Verify search returns matched_snippets from the official text."""
    response = client.post(
        "/api/v1/search/",
        json={"query": "bail application", "limit": 5}
    )
    assert response.status_code == 200
    data = response.json()
    assert "results" in data
    assert len(data["results"]) > 0
    # At least one result should have matched snippets or relevance score
    first = data["results"][0]
    assert "matched_snippets" in first
    assert "matched_keywords" in first
    assert first["relevance_score"] > 0
