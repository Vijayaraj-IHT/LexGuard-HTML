import os
import sys
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from app.main import app
from app.core.database import SessionLocal
from app.models.user import User

client = TestClient(app)


def test_all_four_roles_can_login_and_access_endpoints():
    test_credentials = [
        ("staff@court.gov.in", "staff123", "staff"),
        ("advocate@bar.in", "advocate123", "advocate"),
        ("scholar@law.edu", "scholar123", "scholar"),
        ("public@citizen.in", "public123", "public"),
    ]

    for email, password, expected_role in test_credentials:
        # 1. Login
        login_res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert login_res.status_code == 200, f"Login failed for {email}: {login_res.text}"
        data = login_res.json()
        assert data["role"] == expected_role, f"Role mismatch for {email}: expected {expected_role}, got {data['role']}"
        assert "access_token" in data
        assert "csrf_token" in data

        # 2. Check /api/v1/auth/me
        me_res = client.get("/api/v1/auth/me")
        assert me_res.status_code == 200, f"/auth/me failed for {email}: {me_res.text}"
        me_data = me_res.json()
        assert me_data["email"] == email
        assert me_data["role"] == expected_role
        assert me_data["status"] == "active"

        # 3. Check /api/v1/users/me alias
        users_me_res = client.get("/api/v1/users/me")
        assert users_me_res.status_code == 200, f"/users/me failed for {email}: {users_me_res.text}"
        assert users_me_res.json()["email"] == email

        # 4. Role-specific permission verification
        if expected_role in ["staff", "senior_staff"]:
            # Staff can access approval queue
            queue_res = client.get("/api/v1/admin/queue")
            assert queue_res.status_code == 200
        elif expected_role in ["advocate", "scholar"]:
            # Non-staff receives 403 on staff routes
            queue_res = client.get("/api/v1/admin/queue")
            assert queue_res.status_code == 403

        # Logout before next user
        csrf = data["csrf_token"]
        logout_res = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
        assert logout_res.status_code == 200


def test_public_user_cannot_access_draft_assistant():
    login_res = client.post("/api/v1/auth/login", json={"email": "public@citizen.in", "password": "public123"})
    assert login_res.status_code == 200
    csrf = login_res.json()["csrf_token"]

    draft_res = client.post(
        "/api/v1/draft/analyze",
        json={"petition_text": "This is a petition draft under Article 226."},
        headers={"X-CSRF-Token": csrf},
    )
    assert draft_res.status_code == 403

    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})


def test_advocate_can_access_draft_assistant():
    login_res = client.post("/api/v1/auth/login", json={"email": "advocate@bar.in", "password": "advocate123"})
    assert login_res.status_code == 200
    csrf = login_res.json()["csrf_token"]

    draft_res = client.post(
        "/api/v1/draft/analyze",
        json={"petition_text": "The petitioner seeks anticipatory bail under Section 438 of the Code of Criminal Procedure."},
        headers={"X-CSRF-Token": csrf},
    )
    assert draft_res.status_code == 200
    data = draft_res.json()
    assert "identified_grounds" in data
    assert "missing_arguments" in data
    assert "suggested_sections" in data
    assert "citation_suggestions" in data

    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
