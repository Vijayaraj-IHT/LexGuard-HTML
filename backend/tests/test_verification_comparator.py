import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.core.database import Base, get_db
from app.models.case import Case
from app.models.user import User
from app.core.security import get_password_hash, create_access_token

# Test client
client = TestClient(app)

def test_document_verification_lookup_not_found():
    """Verify that an unknown SHA-256 hash returns matched=False without error."""
    unknown_hash = "0000000000000000000000000000000000000000000000000000000000000000"
    response = client.get(f"/api/v1/verification/lookup/{unknown_hash}")
    assert response.status_code == 200
    data = response.json()
    assert data["matched"] is False
    assert data["query_hash"] == unknown_hash
    assert "No registered published document matches" in data["message"]

def test_document_verification_invalid_hash():
    """Verify that an invalid hash length or character set is rejected."""
    response = client.get("/api/v1/verification/lookup/not-a-valid-sha256")
    assert response.status_code in (400, 422)

def test_comparator_precedent_list():
    """Verify that published precedents endpoint returns a list of cases."""
    response = client.get("/api/v1/comparison/precedents")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    for c in data:
        assert "id" in c
        assert "title" in c
        assert "precedential_status" in c
        assert "source_verification_state" in c

def test_comparator_renormalized_weights_and_missing_dimensions():
    """
    Test comparator algorithm:
    1. Missing dimensions must be excluded from the score denominator.
    2. Pending outcomes must be excluded from the score.
    3. Renormalized weights must sum to 100%.
    """
    # Fetch a precedent to compare against
    precedents_resp = client.get("/api/v1/comparison/precedents")
    precedents = precedents_resp.json()
    if not precedents:
        pytest.skip("No precedents in database for comparison test")

    target_precedent = precedents[0]

    # Payload matching CaseComparisonRequest with missing statutory provisions/issues and pending outcome
    payload = {
        "precedent_case_id": target_precedent["id"],
        "case_title": "Bail Application of A v. State",
        "court_jurisdiction": target_precedent.get("court") or "Supreme Court of India",
        "procedural_status": "Bail Application",
        "remedy_sought": "Bail",
        "statutory_provisions": [],  # Missing provisions
        "legal_issues": [],  # Missing issues -> Dimension 1 excluded
        "facts_summary": "Accused detained without proper compliance of statutory requirements.",
        "outcome": "Pending (Sub Judice)"  # Pending outcome -> Outcome excluded
    }

    response = client.post("/api/v1/comparison/compare", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert "overall_score" in data
    assert "dimensions" in data
    assert "precedent" in data

    dimensions = data["dimensions"]
    active_dims = [d for d in dimensions if d["is_included_in_score"]]
    excluded_dims = [d for d in dimensions if not d["is_included_in_score"]]

    # Both Dimension 1 (Legal Issues & Statutory Provisions) and Outcome should be excluded
    assert len(excluded_dims) >= 2
    
    # Renormalized effective weights of active dimensions must sum to 100%
    total_effective_weight = sum(d["effective_weight_percentage"] for d in active_dims)
    assert round(total_effective_weight, 1) == 100.0

def test_public_registration_cannot_assign_staff_role():
    """Verify that public registration endpoint rejects staff roles."""
    payload = {
        "email": "malicious_staff@lexguard.test",
        "username": "fake_admin",
        "full_name": "Fake Admin",
        "password": "Password123!",
        "role": "staff"
    }
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 422  # Pydantic validation rejects 'staff' role

def test_csrf_middleware_protection():
    """Verify that state-modifying requests with cookie auth require matching CSRF token."""
    from app.core.config import settings
    csrf_client = TestClient(app, cookies={settings.COOKIE_NAME: "test-session-token"})
    response = csrf_client.post(
        "/api/v1/comparison/compare",
        json={"precedent_case_id": "dummy-id"}
    )
    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]
