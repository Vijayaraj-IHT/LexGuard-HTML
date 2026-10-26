"""Deterministic, isolated test fixtures for the LexGuard backend.

The test process is forced onto a fresh temporary SQLite database and
temporary case-storage directory before any application module is imported.
Every test then starts from the same demo users and case records; no test
depends on a developer's PostgreSQL database or on another test's writes.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

TEST_ROOT = Path(tempfile.mkdtemp(prefix="lexguard-phase0-tests-"))
TEST_DB_PATH = TEST_ROOT / "lexguard-test.db"
TEST_STORAGE_DIR = TEST_ROOT / "storage" / "cases"
TEST_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# These must be set before importing app.core.config/app.main.
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["ENVIRONMENT"] = "development"
os.environ["SECRET_KEY"] = "lexguard-phase0-test-secret-key-at-least-32-chars"
os.environ["COOKIE_SECURE"] = "False"
os.environ["STORAGE_DIR"] = str(TEST_STORAGE_DIR)
os.environ["USE_LOCAL_LLM"] = "False"
os.environ["USE_MOCK_LLM"] = "True"
os.environ["ANTHROPIC_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, SessionLocal, engine
from app.core.security import get_password_hash
from app.main import app  # importing the app registers every router/model
from app.models.approval_queue import ApprovalQueue
from app.models.case import Case
from app.models.user import User
from app.services.crypto_service import compute_sha256

COURT_STAFF_ID = "00000000-0000-4000-8000-000000000001"
SENIOR_STAFF_ID = "00000000-0000-4000-8000-000000000002"
ADVOCATE_ID = "00000000-0000-4000-8000-000000000003"
SCHOLAR_ID = "00000000-0000-4000-8000-000000000004"
PUBLIC_ID = "00000000-0000-4000-8000-000000000005"

PUBLISHED_CASE_ID = "10000000-0000-4000-8000-000000000001"
PENDING_CASE_ID = "10000000-0000-4000-8000-000000000002"

DEMO_USER_SPECS = [
    {
        "id": COURT_STAFF_ID,
        "name": "Court Registrar",
        "email": "staff@court.gov.in",
        "password": "staff123",
        "role": "staff",
        "credential_id": "COURT-REG-001",
    },
    {
        "id": SENIOR_STAFF_ID,
        "name": "Chief Registrar",
        "email": "staff@lexguard.gov.in",
        "password": "Admin@Lexguard2026",
        "role": "senior_staff",
        "credential_id": "COURT-REG-001",
    },
    {
        "id": ADVOCATE_ID,
        "name": "Senior Advocate",
        "email": "advocate@bar.in",
        "password": "advocate123",
        "role": "advocate",
        "credential_id": "BAR-DL-2024-9912",
    },
    {
        "id": SCHOLAR_ID,
        "name": "Legal Scholar",
        "email": "scholar@law.edu",
        "password": "scholar123",
        "role": "scholar",
        "credential_id": "NLSIU-FAC-4012",
    },
    {
        "id": PUBLIC_ID,
        "name": "Citizen User",
        "email": "public@citizen.in",
        "password": "public123",
        "role": "public",
        "credential_id": None,
    },
]

_PASSWORD_HASH_CACHE: dict[str, str] = {}


def _password_hash(password: str) -> str:
    if password not in _PASSWORD_HASH_CACHE:
        _PASSWORD_HASH_CACHE[password] = get_password_hash(password)
    return _PASSWORD_HASH_CACHE[password]


def _write_case_file(filename: str, content: bytes) -> tuple[str, str]:
    path = TEST_STORAGE_DIR / filename
    path.write_bytes(content)
    return str(path), compute_sha256(content)


def _reset_database() -> None:
    Base.metadata.create_all(bind=engine)

    # Remove files created by the preceding test before reseeding.
    for child in TEST_STORAGE_DIR.iterdir():
        if child.is_file():
            child.unlink()

    db = SessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()

        for spec in DEMO_USER_SPECS:
            db.add(
                User(
                    id=spec["id"],
                    name=spec["name"],
                    email=spec["email"],
                    password_hash=_password_hash(spec["password"]),
                    role=spec["role"],
                    status="active",
                    credential_id=spec["credential_id"],
                )
            )
        db.commit()

        published_path, published_hash = _write_case_file(
            "published-bail-precedent.pdf",
            b"%PDF-1.4\nLexGuard deterministic published bail precedent\n",
        )
        published_case = Case(
            id=PUBLISHED_CASE_ID,
            case_no="Crl.O.P. 1001/2026",
            title="Bail Application of Raman v. State of Tamil Nadu",
            court="Madras High Court (Principal Seat, Chennai)",
            year=2026,
            judge="Hon'ble Justice A. Example",
            parties="Raman v. State of Tamil Nadu",
            petitioner="Raman",
            respondent="State of Tamil Nadu",
            act_tags=["Code of Criminal Procedure, 1973"],
            section_tags=["Section 438 CrPC", "Section 41A CrPC"],
            keyword_tags=["bail", "anticipatory bail"],
            summary="A deterministic published precedent concerning a bail application.",
            outcome="Allowed",
            facts="The petitioner sought anticipatory bail application relief.",
            ratio_decidendi="Bail application liberty interests require proportionate conditions.",
            disposition="Allowed",
            full_text=(
                "--- PAGE 1 ---\n"
                "Bail Application of Raman v. State of Tamil Nadu. "
                "This bail application under Section 438 CrPC is allowed."
            ),
            page_count=1,
            file_path=published_path,
            file_hash=published_hash,
            judicial_seal=compute_sha256(b"lexguard-deterministic-seed-seal"),
            status="published",
            uploaded_by_id=COURT_STAFF_ID,
            approved_by_id=SENIOR_STAFF_ID,
            approved_at=datetime.now(timezone.utc),
            source_verification_state="verified",
            precedential_status="Precedential status not checked",
            official_citation="2026 LexGuard Test 1",
        )
        db.add(published_case)

        pending_path, pending_hash = _write_case_file(
            "pending-review-case.pdf",
            b"%PDF-1.4\nLexGuard deterministic pending review case\n",
        )
        pending_case = Case(
            id=PENDING_CASE_ID,
            case_no="Crl.O.P. 1002/2026",
            title="Pending Review Petitioner v. State of Tamil Nadu",
            court="Madras High Court (Principal Seat, Chennai)",
            year=2026,
            judge="Hon'ble Justice B. Example",
            parties="Pending Review Petitioner v. State of Tamil Nadu",
            act_tags=["Code of Criminal Procedure, 1973"],
            section_tags=["Section 439 CrPC"],
            keyword_tags=["bail", "pending review"],
            summary="A deterministic case awaiting senior-staff approval.",
            outcome="Pending",
            ratio_decidendi="Pending senior review.",
            disposition="Pending",
            full_text="--- PAGE 1 ---\nPending Review Petitioner bail application.",
            page_count=1,
            file_path=pending_path,
            file_hash=pending_hash,
            status="pending_approval",
            uploaded_by_id=COURT_STAFF_ID,
            source_verification_state="unverified",
            precedential_status="Precedential status not checked",
        )
        db.add(pending_case)
        db.flush()
        db.add(
            ApprovalQueue(
                case_id=pending_case.id,
                submitted_by_id=COURT_STAFF_ID,
                status="pending",
                review_note="Awaiting senior-staff review",
            )
        )
        db.commit()
    finally:
        db.close()


# Make the database usable during test-module import as well as test setup.
_reset_database()


@pytest.fixture(autouse=True)
def reset_test_database():
    _reset_database()
    yield


@pytest.fixture
def db_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


@pytest.fixture
def client():
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.cookies.clear()


@pytest.fixture
def demo_users() -> dict[str, dict[str, str]]:
    return {
        spec["role"]: {
            "id": spec["id"],
            "email": spec["email"],
            "password": spec["password"],
            "role": spec["role"],
        }
        for spec in DEMO_USER_SPECS
    }


@pytest.fixture
def published_case(db_session):
    return db_session.query(Case).filter(Case.id == PUBLISHED_CASE_ID).one()


@pytest.fixture
def pending_case(db_session):
    return db_session.query(Case).filter(Case.id == PENDING_CASE_ID).one()
