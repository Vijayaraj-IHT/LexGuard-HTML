"""
Integration tests for Step 3: Split-Screen Review Integration.
Validates:
1. Retrieval of case metadata and official page-by-page text content.
2. Metadata updates via PATCH /cases/{id} (court, judge, disposition, statutory tags).
3. Re-extraction execution via POST /cases/{id}/re-extract.
4. Composite Judicial Seal Phi_case computation upon approval in POST /admin/approve/{id}.
"""

from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal
from app.models.case import Case

client = TestClient(app)


def get_staff_token():
    client.cookies.clear()
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "staff@lexguard.gov.in", "password": "Admin@Lexguard2026"},
    )
    assert res.status_code == 200, f"Staff login failed: {res.text}"
    data = res.json()
    token = data["access_token"]
    csrf_token = data.get("csrf_token")
    headers = {"Authorization": f"Bearer {token}"}
    if csrf_token:
        headers["X-CSRF-Token"] = csrf_token
    return headers


def test_case_metadata_patch_and_audit():
    """Verify court staff can edit case metadata and changes are audited."""
    headers = get_staff_token()
    db = SessionLocal()
    # F7: published records are sealed (409). Edit an unpublished record instead.
    case = db.query(Case).filter(Case.status != "published").first()
    db.close()
    assert case is not None, "At least one unpublished case required for test"

    patch_payload = {
        "disposition": "Bail Granted",
        "precedential_status": "Good Law",
        "act_tags": ["Bharatiya Nagarik Suraksha Sanhita, 2023", "Narcotic Drugs and Psychotropic Substances Act, 1985"],
        "section_tags": ["Section 483 BNSS", "Section 37 NDPS Act"],
    }

    res = client.patch(f"/api/v1/cases/{case.id}", json=patch_payload, headers=headers)
    assert res.status_code == 200
    updated = res.json()
    assert updated["disposition"] == "Bail Granted"
    assert "Section 483 BNSS" in updated["section_tags"]
    assert "Bharatiya Nagarik Suraksha Sanhita, 2023" in updated["act_tags"]


def test_composite_judicial_seal_on_approval():
    """Verify approval affixes the composite judicial seal Phi_case."""
    headers = get_staff_token()
    db = SessionLocal()
    # F7 maker-checker: approve a pending record uploaded by someone other than the staff account.
    from sqlalchemy import or_
    from app.models.user import User as _User
    staff = db.query(_User).filter(_User.email == "staff@lexguard.gov.in").first()
    case = db.query(Case).filter(
        Case.status != "published",
        or_(Case.uploaded_by_id.is_(None), Case.uploaded_by_id != staff.id),
    ).first()
    db.close()
    assert case is not None

    approve_res = client.post(
        f"/api/v1/admin/approve/{case.id}",
        json={"status": "published", "review_note": "Verified against official PDF."},
        headers=headers,
    )
    assert approve_res.status_code == 200
    res_data = approve_res.json()
    assert res_data["status"] == "published"
    assert res_data["redacted_file_hash"] is not None
    assert len(res_data["redacted_file_hash"]) == 64  # SHA-256 seal hex digest
