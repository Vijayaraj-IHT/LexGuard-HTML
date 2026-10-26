"""Regression tests for the Phase-0 critical-fix roadmap."""

from __future__ import annotations

import re
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text

from app.api.v1.endpoints.search import _extract_matched_snippets
from app.main import app
from app.models.approval_queue import ApprovalQueue
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.services.ai_api_service import AIApiService
from app.services.audit_service import log_audit_event, reseal_audit_chain
from app.core.security import canonical_role, require_role
from app.services.crypto_service import GENESIS_HASH, verify_audit_chain

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"

COURT_STAFF_ID = "00000000-0000-4000-8000-000000000001"
SENIOR_STAFF_ID = "00000000-0000-4000-8000-000000000002"
PUBLISHED_CASE_ID = "10000000-0000-4000-8000-000000000001"
PENDING_CASE_ID = "10000000-0000-4000-8000-000000000002"


def login_client(email: str, password: str):
    client = TestClient(app)
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    data = response.json()
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    if data.get("csrf_token"):
        headers["X-CSRF-Token"] = data["csrf_token"]
    return client, headers, data


def make_pending_case(db, *, uploader_id: str, case_no: str) -> str:
    case_id = str(uuid.uuid4())
    case = Case(
        id=case_id,
        case_no=case_no,
        title=f"Pending {case_no}",
        court="Madras High Court (Principal Seat, Chennai)",
        year=2026,
        judge="Hon'ble Justice Test",
        parties="Petitioner v. State",
        act_tags=[],
        section_tags=[],
        keyword_tags=[],
        summary="Phase-0 governance regression case",
        outcome="Pending",
        facts="Facts",
        issues_framed=[],
        ratio_decidendi="Pending",
        statutory_tests=[],
        disposition="Pending",
        precedents_cited=[],
        full_text="Phase-0 governance regression full text",
        page_count=1,
        file_path="phase0-governance.pdf",
        file_hash="b" * 64,
        status="pending_approval",
        uploaded_by_id=uploader_id,
    )
    db.add(case)
    db.flush()
    db.add(
        ApprovalQueue(
            case_id=case_id,
            submitted_by_id=uploader_id,
            status="pending",
        )
    )
    db.commit()
    return case_id


def test_backend_compiles_on_supported_python_and_bookmark_export_source_is_valid():
    source = (BACKEND_DIR / "app/api/v1/endpoints/bookmarks.py").read_text()
    compile(source, "bookmarks.py", "exec")
    assert app.title


def test_ai_embedding_fallback_uses_existing_batch_method():
    service = AIApiService(base_url="http://127.0.0.1:1", timeout=0.01)
    vectors = service.generate_embeddings(["Bail application under Section 438 CrPC"])
    assert len(vectors) == 1
    assert len(vectors[0]) == 384


def test_search_snippets_escape_judgment_html_before_highlighting():
    snippets, keywords = _extract_matched_snippets(
        "<script>alert('x')</script> bail application",
        ["bail"],
    )
    assert keywords == ["bail"]
    assert snippets
    assert "<script>" not in snippets[0]
    assert "&lt;script&gt;" in snippets[0]
    assert "<mark>bail</mark>" in snippets[0]


def test_audit_single_writer_assigns_seq_and_reseal_preserves_broken_history(db_session):
    log_audit_event(
        db=db_session,
        action="PHASE0_ONE",
        user_id=SENIOR_STAFF_ID,
        details="first event",
        ip_address="127.0.0.1",
    )
    log_audit_event(
        db=db_session,
        action="PHASE0_TWO",
        user_id=SENIOR_STAFF_ID,
        details="second event",
        ip_address="127.0.0.1",
    )

    logs = db_session.query(AuditLog).order_by(AuditLog.seq.asc()).all()
    assert [log.seq for log in logs] == [1, 2]
    assert [log.segment for log in logs] == [1, 1]
    assert verify_audit_chain(logs)["is_valid"] is True

    # Simulate the historical contamination that a disclosed reseal is meant
    # to supersede without rewriting rows.
    logs[0].details = "tampered after hashing"
    db_session.commit()
    db_session.expire_all()
    broken_logs = db_session.query(AuditLog).order_by(AuditLog.seq.asc()).all()
    assert verify_audit_chain(broken_logs)["is_valid"] is False

    reseal = reseal_audit_chain(
        db_session,
        user_id=SENIOR_STAFF_ID,
        reason="Phase-0 disclosed remediation of legacy chain",
    )
    assert reseal.segment == 2
    assert reseal.action == "CHAIN_RESEALED"

    log_audit_event(
        db=db_session,
        action="PHASE0_AFTER_RESEAL",
        user_id=SENIOR_STAFF_ID,
        details="active segment event",
        ip_address="127.0.0.1",
    )
    all_logs = (
        db_session.query(AuditLog)
        .order_by(AuditLog.segment.asc(), AuditLog.seq.asc())
        .all()
    )
    result = verify_audit_chain(all_logs)
    assert result["is_valid"] is True
    assert result["active_segment"] == 2
    assert result["segments"][0]["is_valid"] is False
    assert result["segments"][1]["is_valid"] is True
    # Historical rows were preserved, not corrected in place.
    assert all_logs[0].details == "tampered after hashing"


def test_audit_writer_never_appends_to_legacy_segment_zero(db_session):
    legacy = log_audit_event(
        db=db_session,
        action="LEGACY_EVENT",
        user_id=SENIOR_STAFF_ID,
        details="restored legacy row",
        ip_address="127.0.0.1",
    )
    legacy.segment = 0
    db_session.commit()

    active = log_audit_event(
        db=db_session,
        action="ACTIVE_EVENT",
        user_id=SENIOR_STAFF_ID,
        details="new application write",
        ip_address="127.0.0.1",
    )

    assert active.segment == 1
    assert active.previous_log_hash == GENESIS_HASH
    assert active.seq == 2


def test_phase0_migration_backfills_legacy_segment_and_moves_only_orphan_seals(tmp_path):
    import migrate_phase0

    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id VARCHAR PRIMARY KEY)"))
        conn.execute(text("INSERT INTO users VALUES ('u')"))
        conn.execute(
            text(
                "CREATE TABLE audit_logs ("
                "id VARCHAR PRIMARY KEY, "
                "user_id VARCHAR REFERENCES users(id) ON DELETE SET NULL, "
                "case_id VARCHAR REFERENCES cases(id) ON DELETE SET NULL, "
                "timestamp DATETIME, previous_log_hash VARCHAR, "
                "current_hash VARCHAR)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO audit_logs VALUES "
                "('b', 'u', '1', '2026-01-02 00:00:00', 'x', 'y'), "
                "('a', 'u', '2', '2026-01-01 00:00:00', '0', 'x')"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE cases ("
                "id VARCHAR PRIMARY KEY, redacted_file_hash VARCHAR, "
                "redacted_file_path VARCHAR)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO cases VALUES "
                "('1', 'orphan-seal', NULL), "
                "('2', 'real-redacted-hash', 'redacted.pdf')"
            )
        )

    first = migrate_phase0.migrate(engine)
    second = migrate_phase0.migrate(engine)

    assert first["audit_seq_backfilled"] == 2
    assert first["judicial_seals_moved"] == 1
    assert first["audit_foreign_keys_restricted"] == 2
    assert second["audit_seq_backfilled"] == 0
    assert second["judicial_seals_moved"] == 0
    assert second["audit_foreign_keys_restricted"] == 0

    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT id, seq, segment FROM audit_logs ORDER BY seq")
        ).fetchall() == [("a", 1, 0), ("b", 2, 0)]
        assert conn.execute(
            text(
                "SELECT id, judicial_seal, redacted_file_hash "
                "FROM cases ORDER BY id"
            )
        ).fetchall() == [
            ("1", "orphan-seal", None),
            ("2", None, "real-redacted-hash"),
        ]

    with engine.connect() as conn:
        fk_actions = {
            row[3]: row[6]
            for row in conn.execute(text("PRAGMA foreign_key_list(audit_logs)"))
        }
    assert fk_actions == {"user_id": "RESTRICT", "case_id": "RESTRICT"}

    indexes = {index["name"] for index in inspect(engine).get_indexes("audit_logs")}
    assert "uq_audit_segment_previous_hash" in indexes
    assert "uq_audit_segment_current_hash" in indexes
    engine.dispose()


def _unescape_pg_copy(value: str):
    if value == r"\N":
        return None
    return (
        value.replace("\\\\", "\0")
        .replace(r"\n", "\n")
        .replace(r"\r", "\r")
        .replace(r"\t", "\t")
        .replace("\0", "\\")
    )


def test_canonical_dump_legacy_audit_chain_is_replayed_and_disclosed_invalid():
    dump_path = REPO_ROOT / "database" / "database_dump.sql"
    lines = dump_path.read_text(encoding="utf-8", errors="ignore").splitlines()

    header_index = next(
        i for i, line in enumerate(lines) if line.startswith("COPY public.audit_logs ")
    )
    columns_match = re.search(r"\((.*)\) FROM stdin;", lines[header_index])
    assert columns_match is not None
    columns = [c.strip().strip('"') for c in columns_match.group(1).split(",")]

    records = []
    for line in lines[header_index + 1 :]:
        if line == r"\.":
            break
        values = [_unescape_pg_copy(v) for v in line.split("\t")]
        assert len(values) == len(columns)
        row = dict(zip(columns, values))
        row["timestamp"] = datetime.fromisoformat(row["timestamp"])
        records.append(SimpleNamespace(**row))

    assert len(records) == 1393
    result = verify_audit_chain(records)
    # This is the disclosed Phase-0 finding: the shipped legacy ledger must
    # be archived as segment 0 and explicitly resealed, not presented valid.
    assert result["is_valid"] is False
    assert result["active_segment"] == 0
    assert result["broken_at_index"] == 31


def test_staff_role_aliases_are_canonical_and_senior_checks_are_strict():
    assert canonical_role("staff") == "court_staff"
    assert canonical_role("junior_staff") == "court_staff"
    assert canonical_role("senior_staff") == "senior_staff"

    junior = SimpleNamespace(role="junior_staff")
    senior = SimpleNamespace(role="senior_staff")

    ordinary_staff_checker = require_role(["court_staff"])
    assert ordinary_staff_checker(junior) is junior
    assert ordinary_staff_checker(senior) is senior

    senior_checker = require_role(["senior_staff"])
    assert senior_checker(senior) is senior
    with pytest.raises(HTTPException) as exc_info:
        senior_checker(junior)
    assert exc_info.value.status_code == 403


def test_case_approval_is_senior_only_non_self_and_transition_checked(db_session):
    junior_client, junior_headers, _ = login_client("staff@court.gov.in", "staff123")
    forbidden = junior_client.post(
        f"/api/v1/admin/approve/{PENDING_CASE_ID}",
        json={"status": "published", "review_note": "Junior attempt"},
        headers=junior_headers,
    )
    assert forbidden.status_code == 403

    senior_client, senior_headers, _ = login_client(
        "staff@lexguard.gov.in", "Admin@Lexguard2026"
    )

    self_case_id = make_pending_case(
        db_session,
        uploader_id=SENIOR_STAFF_ID,
        case_no="PHASE0-SELF/2026",
    )
    self_approval = senior_client.post(
        f"/api/v1/admin/approve/{self_case_id}",
        json={"status": "published", "review_note": "Self approval"},
        headers=senior_headers,
    )
    assert self_approval.status_code == 403

    approved = senior_client.post(
        f"/api/v1/admin/approve/{PENDING_CASE_ID}",
        json={"status": "published", "review_note": "Verified"},
        headers=senior_headers,
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "published"
    assert body["judicial_seal"] and len(body["judicial_seal"]) == 64
    assert body["redacted_file_hash"] is None

    illegal = senior_client.post(
        f"/api/v1/admin/approve/{PENDING_CASE_ID}",
        json={"status": "rejected", "review_note": "Published cannot be rejected directly"},
        headers=senior_headers,
    )
    assert illegal.status_code == 409

    rejected_case_id = make_pending_case(
        db_session,
        uploader_id=COURT_STAFF_ID,
        case_no="PHASE0-REJECT/2026",
    )
    rejected = senior_client.post(
        f"/api/v1/admin/approve/{rejected_case_id}",
        json={"status": "rejected", "review_note": "Incomplete"},
        headers=senior_headers,
    )
    assert rejected.status_code == 200
    illegal_republish = senior_client.post(
        f"/api/v1/admin/approve/{rejected_case_id}",
        json={"status": "published", "review_note": "Skip resubmission"},
        headers=senior_headers,
    )
    assert illegal_republish.status_code == 409


def test_senior_user_administration_endpoints():
    senior_client, senior_headers, senior_data = login_client(
        "staff@lexguard.gov.in", "Admin@Lexguard2026"
    )
    advocate_client, advocate_headers, advocate_data = login_client(
        "advocate@bar.in", "advocate123"
    )

    assert advocate_client.get("/api/v1/admin/users", headers=advocate_headers).status_code == 403

    users = senior_client.get("/api/v1/admin/users", headers=senior_headers)
    assert users.status_code == 200
    assert any(user["email"] == "staff@court.gov.in" for user in users.json())

    created = senior_client.post(
        "/api/v1/admin/users",
        json={
            "name": "Phase Zero Clerk",
            "email": "phase0.clerk@court.gov.in",
            "password": "ClerkPass123!",
            "role": "court_staff",
            "status": "active",
            "credential_id": "COURT-CLERK-P0",
        },
        headers=senior_headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "court_staff"

    suspended = senior_client.patch(
        f"/api/v1/admin/users/{advocate_data['user_id']}",
        json={"status": "suspended"},
        headers=senior_headers,
    )
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "suspended"

    suspended_login = TestClient(app).post(
        "/api/v1/auth/login",
        json={"email": "advocate@bar.in", "password": "advocate123"},
    )
    assert suspended_login.status_code == 403

    self_demote = senior_client.patch(
        f"/api/v1/admin/users/{senior_data['user_id']}",
        json={"role": "court_staff"},
        headers=senior_headers,
    )
    assert self_demote.status_code == 400


def test_senior_reseal_endpoint_requires_csrf_and_starts_new_segment():
    senior_client, senior_headers, senior_data = login_client(
        "staff@lexguard.gov.in", "Admin@Lexguard2026"
    )
    payload = {"reason": "Phase-0 endpoint reseal regression test"}

    missing_csrf_headers = {"Authorization": senior_headers["Authorization"]}
    missing = senior_client.post(
        "/api/v1/admin/reseal-audit-chain",
        json=payload,
        headers=missing_csrf_headers,
    )
    assert missing.status_code == 403

    wrong_headers = dict(senior_headers)
    wrong_headers["X-CSRF-Token"] = "x" * len(senior_data["csrf_token"])
    wrong = senior_client.post(
        "/api/v1/admin/reseal-audit-chain",
        json=payload,
        headers=wrong_headers,
    )
    assert wrong.status_code == 403

    resealed = senior_client.post(
        "/api/v1/admin/reseal-audit-chain",
        json=payload,
        headers=senior_headers,
    )
    assert resealed.status_code == 200, resealed.text
    assert resealed.json()["segment"] == 2

    verification = senior_client.get(
        "/api/v1/admin/verify-audit-chain",
        headers=senior_headers,
    )
    assert verification.status_code == 200
    assert verification.json()["active_segment"] == 2
    assert verification.json()["is_valid"] is True


def test_download_verifies_hash_before_claiming_verified(db_session):
    advocate_client, advocate_headers, _ = login_client(
        "advocate@bar.in", "advocate123"
    )

    ok = advocate_client.get(
        f"/api/v1/cases/{PUBLISHED_CASE_ID}/download",
        headers=advocate_headers,
    )
    assert ok.status_code == 200
    assert ok.headers["x-lexguard-verified"] == "true"

    case = db_session.query(Case).filter(Case.id == PUBLISHED_CASE_ID).one()
    Path(case.file_path).write_bytes(b"tampered document bytes")

    blocked = advocate_client.get(
        f"/api/v1/cases/{PUBLISHED_CASE_ID}/download",
        headers=advocate_headers,
    )
    assert blocked.status_code == 409

    db_session.expire_all()
    refreshed = db_session.query(Case).filter(Case.id == PUBLISHED_CASE_ID).one()
    assert refreshed.status == "quarantined"


def test_frontend_cookie_only_and_cause_list_contracts():
    auth_js = (REPO_ROOT / "frontend/js/lexguard-auth.js").read_text()
    api_js = (REPO_ROOT / "frontend/js/lexguard-api.js").read_text()
    cause_js = (REPO_ROOT / "frontend/js/pages/cause-list.js").read_text()
    audit_js = (REPO_ROOT / "frontend/js/pages/audit-ledger.js").read_text()

    assert "auth_role" not in auth_js
    assert "demo_role" not in auth_js
    assert "localStorage.setItem" not in auth_js
    assert "localStorage.removeItem" in auth_js  # legacy JWT cleanup
    assert "Authorization'] = 'Bearer '" not in api_js
    assert "LG.api.cases.search" not in cause_js
    assert "LG.api.search.query" in cause_js
    assert "#dc3545" in audit_js
    assert "Audit Chain Invalid" in audit_js

    frontend_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in (REPO_ROOT / "frontend").rglob("*")
        if path.is_file() and path.suffix in {".html", ".js"}
    )
    assert "auth_role=" not in frontend_text


def test_all_frontend_javascript_parses():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not available for frontend syntax checks")

    for script in sorted((REPO_ROOT / "frontend/js").rglob("*.js")):
        result = subprocess.run(
            [node, "--check", str(script)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"{script}: {result.stderr}"


def test_csrf_comparisons_use_constant_time_helper():
    security_source = (BACKEND_DIR / "app/core/security.py").read_text()
    main_source = (BACKEND_DIR / "app/main.py").read_text()
    assert "verify_csrf_token(" in security_source
    assert "verify_csrf_token(" in main_source
    assert "csrf_token !=" not in security_source
    assert "csrf_header !=" not in main_source
    assert "X-XSS-Protection" not in main_source
