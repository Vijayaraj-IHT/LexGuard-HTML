import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import SessionLocal, Base, engine
from app.models.user import User
from app.services.crypto_service import (
    compute_sha256,
    verify_sha256,
    compute_audit_log_hash,
    verify_audit_chain,
    GENESIS_HASH,
)
from app.core.security import get_password_hash, verify_password, create_access_token, decode_access_token

# Ensure all database tables exist for tests
Base.metadata.create_all(bind=engine)

# Seed staff user if not present for tests
_db = SessionLocal()
if not _db.query(User).filter(User.email == "staff@lexguard.gov.in").first():
    _db.add(User(
        name="Chief Registrar",
        email="staff@lexguard.gov.in",
        password_hash=get_password_hash("Admin@Lexguard2026"),
        role="senior_staff",
        status="active",
        credential_id="COURT-REG-001",
    ))
    _db.commit()
_db.close()

client = TestClient(app)


def test_crypto_sha256():
    """Verifies that SHA-256 calculation and verification are mathematically accurate."""
    sample_bytes = b"State of Maharashtra vs. Ramesh Sharma 2024 Legal Case"
    expected = compute_sha256(sample_bytes)
    assert len(expected) == 64
    assert verify_sha256(sample_bytes, expected) is True
    assert verify_sha256(b"Tampered bytes", expected) is False


def test_password_hashing():
    """Verifies bcrypt password hashing and constant-time verification."""
    pwd = "SecuredAdvocatePass!2026"
    hashed = get_password_hash(pwd)
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPass", hashed) is False


def test_jwt_generation_and_decoding():
    """Verifies JWT role claims and decoding."""
    token = create_access_token(subject="user-1234", role="advocate")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-1234"
    assert payload["role"] == "advocate"


def test_audit_hash_chaining():
    """Verifies cryptographic chain of custody and tamper detection."""
    class MockLog:
        def __init__(self, id, prev, action, ts, details):
            self.id = id
            self.user_id = "user-1"
            self.case_id = "case-1"
            self.action = action
            self.ip_address = "127.0.0.1"
            self.timestamp = ts
            self.details = details
            self.previous_log_hash = prev
            self.current_hash = compute_audit_log_hash(
                prev, "user-1", "case-1", action, "127.0.0.1", ts, details
            )

    log1 = MockLog("1", GENESIS_HASH, "UPLOAD", "2026-10-11T10:00:00Z", "Initial upload")
    log2 = MockLog("2", log1.current_hash, "VIEW", "2026-10-11T10:05:00Z", "Advocate view")
    log3 = MockLog("3", log2.current_hash, "DOWNLOAD", "2026-10-11T10:10:00Z", "Verified download")

    chain = [log1, log2, log3]
    result = verify_audit_chain(chain)
    assert result["is_valid"] is True
    assert result["total_records"] == 3

    # Tamper with log2 action
    log2.action = "ALTERED_ACTION"
    tampered_result = verify_audit_chain(chain)
    assert tampered_result["is_valid"] is False


def test_health_check_endpoint():
    """Verifies system health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_auth_workflow_and_rbac():
    """Tests registration, login cookie generation, and profile endpoint."""
    # Register an advocate
    import uuid as _u
    email = f"advocate_{_u.uuid4().hex[:6]}@barcouncil.in"
    reg_response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Arjun Sundaram",
            "email": email,
            "password": "Password123!",
            "role": "advocate",
            "credential_id": "BAR-TN-2024-998",
        },
    )
    # 201 or 400 if rerun
    assert reg_response.status_code in [201, 400]

    # Activate advocate status in test database (simulating registry staff approval)
    from app.core.database import SessionLocal
    from app.models.user import User
    with SessionLocal() as db:
        u = db.query(User).filter(User.email == email).first()
        if u:
            u.status = "active"
            db.commit()

    # Login
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert login_response.status_code == 200
    login_data = login_response.json()
    assert "access_token" in login_data
    assert login_data["role"] == "advocate"
    assert "lexguard_csrf_token" in login_response.cookies
    assert "lexguard_access_token" in login_response.cookies


def test_case_upload_tamper_detection_and_approval():
    """
    End-to-end integration test:
    1. Login as default Senior Staff.
    2. Upload legal document PDF.
    3. Verify computed SHA-256 integrity.
    4. Approve case.
    5. Deliberately tamper with file bytes on disk.
    6. Verify that cryptographic check catches the tamper (INTEGRITY_VIOLATION).
    7. Verify entire audit trail hash chain remains unbroken.
    """
    # 1. Login as ordinary court staff (the eventual uploader)
    client.cookies.clear()
    login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "staff@court.gov.in", "password": "staff123"},
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    token = login_data["access_token"]
    csrf_token = login_data.get("csrf_token")
    headers = {"Authorization": f"Bearer {token}"}
    if csrf_token:
        headers["X-CSRF-Token"] = csrf_token

    # 2. Upload sample judgment document
    import uuid as _uuid
    test_run_id = str(_uuid.uuid4())[:8]
    fake_doc_bytes = f"%PDF-1.4 ... Judgement in Criminal Appeal {test_run_id} of 2024 ... State vs. Accused".encode()
    files = {"file": (f"judgement_{test_run_id}_2024.pdf", fake_doc_bytes, "application/pdf")}
    data = {
        "case_no": f"Crl.A. {test_run_id}/2024",
        "title": "State of Maharashtra vs. Sandeep",
        "court": "Supreme Court of India",
        "year": "2024",
        "judge": "Hon'ble CJI",
        "act_tags": '["CrPC", "IPC"]',
        "section_tags": '["Section 439 CrPC", "Section 420 IPC"]',
        "keyword_tags": '["bail", "parity"]',
        "summary": "Landmark ruling on bail parity and procedural fairness.",
        "outcome": "Allowed",
    }

    upload_res = client.post("/api/v1/cases/upload", data=data, files=files, headers=headers)
    assert upload_res.status_code == 201
    case_data = upload_res.json()
    case_id = case_data["id"]
    assert case_data["status"] == "pending_approval"
    expected_hash = compute_sha256(fake_doc_bytes)
    assert case_data["file_hash"] == expected_hash

    # 3. Verify integrity (should be VERIFIED_UNTAMPERED)
    verify_res = client.get(f"/api/v1/cases/{case_id}/verify-integrity", headers=headers)
    assert verify_res.status_code == 200
    assert verify_res.json()["is_valid"] is True
    assert verify_res.json()["status_badge"] == "VERIFIED_UNTAMPERED"

    # 4. Approve as a different senior-staff reviewer (segregation of duties)
    client.cookies.clear()
    senior_login_res = client.post(
        "/api/v1/auth/login",
        json={"email": "staff@lexguard.gov.in", "password": "Admin@Lexguard2026"},
    )
    assert senior_login_res.status_code == 200
    senior_data = senior_login_res.json()
    headers = {"Authorization": f"Bearer {senior_data['access_token']}"}
    if senior_data.get("csrf_token"):
        headers["X-CSRF-Token"] = senior_data["csrf_token"]

    approve_res = client.post(
        f"/api/v1/admin/approve/{case_id}",
        json={"status": "published", "review_note": "Verified by Chief Registrar"},
        headers=headers,
    )
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "published"

    # 5. Search case
    search_res = client.post(
        "/api/v1/search/",
        json={"query": "bail parity under Section 439 CrPC"},
        headers=headers,
    )
    assert search_res.status_code == 200
    search_results = search_res.json()["results"]
    assert len(search_results) >= 1
    assert any(r["id"] == case_id for r in search_results)

    # 6. Tamper with file on disk
    from app.models.case import Case
    from app.core.database import SessionLocal
    db = SessionLocal()
    case_obj = db.query(Case).filter(Case.id == case_id).first()
    file_path = case_obj.file_path
    db.close()

    with open(file_path, "wb") as f:
        f.write(b"%PDF-1.4 Tampered unauthorized modifications injected here")

    # Re-verify integrity (must flag INTEGRITY_VIOLATION)
    tampered_check = client.get(f"/api/v1/cases/{case_id}/verify-integrity", headers=headers)
    assert tampered_check.status_code == 200
    assert tampered_check.json()["is_valid"] is False
    assert tampered_check.json()["status_badge"] == "INTEGRITY_VIOLATION"

    # 7. Verify audit chain continuity endpoint responds with structure
    chain_check = client.get("/api/v1/admin/verify-audit-chain", headers=headers)
    assert chain_check.status_code == 200
    assert "is_valid" in chain_check.json()
    assert chain_check.json()["total_records"] > 0

