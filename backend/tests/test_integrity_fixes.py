"""
Regression tests for the integrity-audit fixes (F0-F8).

Runs against a temporary SQLite database. DATABASE_URL is set BEFORE the app is
imported, so the repository's lexguard.db is never opened for writing.

Run from backend/:
    python -m pytest tests/test_integrity_fixes.py -q

Run this file on its own (or before other app-importing test modules): the
database engine is created once per process.
"""

import datetime
import hashlib
import time
import os
import subprocess
import sys
import tempfile

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

_TMP = tempfile.mkdtemp(prefix="lg_integrity_test_")
_TEST_DB = os.path.join(_TMP, "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ.pop("LEXGUARD_ALLOW_TEST_WRITES", None)

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main_module  # noqa: E402  (F0: this import used to raise SyntaxError)
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import get_current_user, get_optional_current_user  # noqa: E402
from app.models.audit_log import AuditLog  # noqa: E402
from app.models.case import Case  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.audit_service import build_audit_entry, get_chain_head_hash, log_audit_event  # noqa: E402
from app.services.crypto_service import (  # noqa: E402
    compute_sha256_stream,
    normalize_timestamp,
    verify_audit_chain,
    verify_sha256_stream,
)

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
app = main_module.app
client = TestClient(app)  # no `with` block: lifespan seeding is skipped


_CREATED_CASE_IDS = set()
_CREATED_USER_IDS = set()


@pytest.fixture(scope="module", autouse=True)
def _schema():
    Base.metadata.create_all(bind=engine)
    yield
    app.dependency_overrides.clear()
    _cleanup_shared_db()


def _cleanup_shared_db():
    """
    Leave no quarantined/pending rows behind.

    In a full-suite run the engine may be bound to the repository's lexguard.db
    (the engine is created once per process, so this module's DATABASE_URL is
    ignored), and other modules then pick "any non-published case" when they
    exercise approval. A leftover quarantined row from this module therefore makes
    those tests order-dependent. Their assertions here are unchanged; only the
    end state is reset.
    """
    try:
        db = SessionLocal()
    except Exception:  # pragma: no cover - defensive
        return
    try:
        for case_id in list(_CREATED_CASE_IDS):
            row = db.query(Case).filter(Case.id == case_id).first()
            if row is not None and row.status == "quarantined":
                row.status = "pending_review"
        db.commit()
    except Exception:  # pragma: no cover - best effort cleanup
        db.rollback()
    finally:
        db.close()


def _user(db, email, role):
    """Creates a user and returns a detached snapshot (ORM objects expire after the session closes)."""
    import types
    u = User(name=email.split("@")[0], email=email, password_hash="x", role=role, status="active")
    db.add(u)
    db.commit()
    db.refresh(u)
    return types.SimpleNamespace(id=u.id, email=u.email, role=u.role, name=u.name, status=u.status)


def _as(user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_optional_current_user] = lambda: user


def _isolated_session():
    """A private SQLite DB for chain tests, so rows written by other test modules can't interfere."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    path = os.path.join(_TMP, f"chain_{os.urandom(4).hex()}.db")
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(bind=eng)
    return sessionmaker(bind=eng)()


def _case_with_file(db, uploader, body: bytes, status="pending_review", **extra):
    # Unique bytes per call: lookups match on file hash, so repeated test data must not collide.
    body = body + os.urandom(16)
    path = os.path.join(_TMP, f"doc_{os.urandom(4).hex()}.pdf")
    with open(path, "wb") as fh:
        fh.write(body)
    c = Case(
        case_no=f"WP/{os.urandom(2).hex()}/2024",
        title="Test v State",
        court="Madras High Court",
        year=2024,
        file_path=path,
        file_hash=hashlib.sha256(body).hexdigest(),
        status=status,
        uploaded_by_id=uploader.id,
        judge="Justice A",
        disposition="Allowed",
        full_text="Operative part of the judgment.",
        **extra,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    _CREATED_CASE_IDS.add(c.id)
    return c


# ---------------------------------------------------------------- F0 / F1


def test_f0_app_imports_on_this_python():
    assert app.title is not None


def test_f1_timestamp_normalization_is_one_rule_for_all_forms():
    ist_dt = datetime.datetime(2030, 1, 1, 5, 30, tzinfo=IST)  # = 2030-01-01T00:00 UTC
    assert normalize_timestamp(ist_dt) == "2030-01-01T00:00:00"
    assert normalize_timestamp("2030-01-01T05:30:00+05:30") == "2030-01-01T00:00:00"
    assert normalize_timestamp("2030-01-01 05:30:00.123+05:30") == "2030-01-01T00:00:00"
    # Naive values are UTC by convention (previously: server local time).
    assert normalize_timestamp(datetime.datetime(2030, 1, 1, 0, 0)) == "2030-01-01T00:00:00"


def test_f1_mixed_timestamp_sources_form_a_verifiable_chain():
    db = _isolated_session()
    # 1. Normal app path (aware UTC, now).
    log_audit_event(db, action="F1_APP_EVENT", details="app path")
    # 2. Backdated IST-aware entry through the shared builder.
    db.add(AuditLog(**build_audit_entry(
        get_chain_head_hash(db), action="F1_IST", timestamp=datetime.datetime(2030, 1, 1, 5, 30, tzinfo=IST),
        details="ist aware",
    )))
    db.commit()
    # 3. Naive timestamp (treated as UTC).
    db.add(AuditLog(**build_audit_entry(
        get_chain_head_hash(db), action="F1_NAIVE", timestamp=datetime.datetime(2030, 1, 1, 12, 0),
        details="naive",
    )))
    db.commit()
    # 4. Aware UTC.
    db.add(AuditLog(**build_audit_entry(
        get_chain_head_hash(db), action="F1_UTC", timestamp=datetime.datetime(2030, 1, 2, tzinfo=datetime.timezone.utc),
        details="utc",
    )))
    db.commit()
    db.close()

    # Fresh session: values come back from SQLite (tzinfo dropped), exactly as in production.
    reader = db.__class__(bind=db.get_bind())
    logs = reader.query(AuditLog).order_by(AuditLog.timestamp.asc()).all()
    reader.close()
    result = verify_audit_chain(logs)
    assert result["is_valid"], result


def test_f1_builder_stores_utc_so_sqlite_round_trip_verifies():
    db = _isolated_session()
    entry = build_audit_entry(
        get_chain_head_hash(db), action="F1_ROUNDTRIP",
        timestamp=datetime.datetime(2030, 3, 1, 9, 0, tzinfo=IST), details="rt",
    )
    assert entry["timestamp"].utcoffset() == datetime.timedelta(0)
    db.add(AuditLog(**entry))
    db.commit()
    row = db.query(AuditLog).filter(AuditLog.action == "F1_ROUNDTRIP").one()
    db.close()
    from app.services.crypto_service import compute_audit_log_hash
    assert compute_audit_log_hash(
        row.previous_log_hash, row.user_id, row.case_id, row.action, row.ip_address, row.timestamp, row.details
    ) == row.current_hash


# ---------------------------------------------------------------- F2


def test_f2_test_writer_refuses_without_opt_in():
    import importlib
    mod = importlib.import_module("tests.test_7_tables")
    db = SessionLocal()
    before = db.query(AuditLog).count()
    db.close()
    with pytest.raises(SystemExit) as exc:
        mod.run_full_7_table_check()
    assert "LEXGUARD_ALLOW_TEST_WRITES" in str(exc.value)
    db = SessionLocal()
    assert db.query(AuditLog).count() == before
    db.close()


# ---------------------------------------------------------------- F3 / F4


def test_f3_same_size_tamper_with_restored_mtime_is_detected(tmp_path):
    p = tmp_path / "doc.pdf"
    p.write_bytes(b"A" * 4096)
    good = hashlib.sha256(b"A" * 4096).hexdigest()
    assert verify_sha256_stream(str(p), good)
    st = os.stat(p)
    p.write_bytes(b"B" + b"A" * 4095)           # same size
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))  # restore mtime
    assert not verify_sha256_stream(str(p), good)
    assert compute_sha256_stream(str(p)) != good


def test_f4_download_serves_only_verified_bytes_and_quarantines_tampered(tmp_path):
    db = SessionLocal()
    staff = _user(db, f"up_{os.urandom(3).hex()}@t.in", "senior_staff")
    reader = _user(db, f"rd_{os.urandom(3).hex()}@t.in", "advocate")
    body = b"%PDF-1.4 original judgment bytes " * 50
    case = _case_with_file(db, staff, body, status="published")
    case_id, path = case.id, case.file_path
    db.close()

    _as(reader)
    ok = client.get(f"/api/v1/cases/{case_id}/download")
    assert ok.status_code == 200, ok.text
    assert ok.headers.get("x-lexguard-verified") == "true"

    st = os.stat(path)
    with open(path, "r+b") as fh:
        fh.write(b"X")                            # same-size tamper
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))

    bad = client.get(f"/api/v1/cases/{case_id}/download")
    assert bad.status_code == 409, bad.text
    assert "x-lexguard-verified" not in bad.headers

    db = SessionLocal()
    assert db.query(Case).filter(Case.id == case_id).one().status == "quarantined"
    assert db.query(AuditLog).filter(AuditLog.case_id == case_id, AuditLog.action == "INTEGRITY_VIOLATION").count() == 1
    db.close()


# ---------------------------------------------------------------- F5


def _publish(db, uploader, approver, body=b"%PDF judgment " * 40):
    c = _case_with_file(db, uploader, body, status="pending_review")
    _as(approver)
    r = client.post(f"/api/v1/admin/approve/{c.id}", json={"status": "published", "review_note": "ok"})
    assert r.status_code == 200, r.text
    db.expire_all()
    return c.id


def test_f5_lookup_reports_registry_match_and_checked_trail():
    db = SessionLocal()
    uploader = _user(db, f"u5_{os.urandom(3).hex()}@t.in", "senior_staff")
    approver = _user(db, f"a5_{os.urandom(3).hex()}@t.in", "senior_staff")
    reader = _user(db, f"r5_{os.urandom(3).hex()}@t.in", "advocate")
    case_id = _publish(db, uploader, approver, body=b"%PDF lookup doc " * 40)
    file_hash = db.query(Case).filter(Case.id == case_id).one().file_hash
    db.close()

    _as(reader)
    r = client.get(f"/api/v1/verification/lookup/{file_hash}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["integrity_status"] == "REGISTRY_MATCH"
    assert data["audit_trail"], "lookup must return the checked audit trail"
    assert all(e["recomputed_ok"] and e["link_ok"] for e in data["audit_trail"])
    assert "Latest" in data["audit_label"]

    # Tamper with one audit row for this case; the trail must now say so.
    db = SessionLocal()
    row = db.query(AuditLog).filter(AuditLog.case_id == case_id).first()
    row.details = "edited after the fact"
    db.commit()
    db.close()
    r2 = client.get(f"/api/v1/verification/lookup/{file_hash}").json()
    assert any(not e["recomputed_ok"] for e in r2["audit_trail"])
    assert r2["audit_label"] == "Audit entry failed local verification"


# ---------------------------------------------------------------- F6


def test_f6_seal_reproduces_then_detects_drift_and_redacted_path_is_501():
    db = SessionLocal()
    uploader = _user(db, f"u6_{os.urandom(3).hex()}@t.in", "senior_staff")
    approver = _user(db, f"a6_{os.urandom(3).hex()}@t.in", "senior_staff")
    case_id = _publish(db, uploader, approver, body=b"%PDF seal doc " * 40)
    _as(approver)

    r = client.get(f"/api/v1/admin/cases/{case_id}/seal-check")
    assert r.status_code == 200, r.text
    assert r.json()["sealed"] is True
    assert r.json()["reproducible"] is True
    assert r.json()["approve_log_found"] is True

    c = db.query(Case).filter(Case.id == case_id).one()
    c.judge = "Someone Else"
    db.commit()
    db.expire_all()
    r2 = client.get(f"/api/v1/admin/cases/{case_id}/seal-check").json()
    assert r2["reproducible"] is False
    assert r2["reason"]

    # A redacted path must not be served as if it were verified against the seal.
    c = db.query(Case).filter(Case.id == case_id).one()
    c.redacted_file_path = "/nonexistent/redacted.pdf"
    db.commit()
    db = SessionLocal()
    pub = _user(db, f"p6_{os.urandom(3).hex()}@t.in", "public")
    db.close()
    _as(pub)
    s = client.get(f"/api/v1/verification/documents/{case_id}/stream")
    assert s.status_code == 501, s.text


# ---------------------------------------------------------------- F7


def test_f7_published_record_cannot_be_edited_or_reextracted():
    db = SessionLocal()
    uploader = _user(db, f"u7_{os.urandom(3).hex()}@t.in", "senior_staff")
    approver = _user(db, f"a7_{os.urandom(3).hex()}@t.in", "senior_staff")
    case_id = _publish(db, uploader, approver, body=b"%PDF frozen doc " * 40)
    db.close()
    _as(approver)
    p = client.patch(f"/api/v1/cases/{case_id}", json={"judge": "Changed"})
    assert p.status_code == 409, p.text
    x = client.post(f"/api/v1/cases/{case_id}/re-extract")
    assert x.status_code == 409, x.text


def test_f7_uploader_cannot_publish_own_submission():
    db = SessionLocal()
    uploader = _user(db, f"self_{os.urandom(3).hex()}@t.in", "senior_staff")
    c = _case_with_file(db, uploader, b"%PDF self doc " * 40, status="pending_review")
    _as(uploader)
    r = client.post(f"/api/v1/admin/approve/{c.id}", json={"status": "published"})
    assert r.status_code == 403, r.text
    db.close()


# ---------------------------------------------------------------- F8


def test_f8_report_is_read_only_and_reports_structure(tmp_path):
    db_copy = tmp_path / "copy.db"
    db_copy.write_bytes(open(engine.url.database, "rb").read())
    before = hashlib.sha256(db_copy.read_bytes()).hexdigest()
    env = dict(os.environ)
    out = subprocess.run(
        [sys.executable, os.path.join(BACKEND_DIR, "integrity_report.py"), "--db", str(db_copy), "--json"],
        capture_output=True, text=True, env=env, cwd=BACKEND_DIR, timeout=300,
    )
    assert out.returncode in (0, 1), out.stderr
    import json
    lines = out.stdout.splitlines()
    start = lines.index("{")  # JSON block starts at column 0
    report = json.loads("\n".join(lines[start:]))
    for key in ("chain", "seals", "maker_checker", "documents", "hygiene", "failed_checks", "ok"):
        assert key in report
    assert hashlib.sha256(db_copy.read_bytes()).hexdigest() == before, "report modified the database"


# ---------------------------------------------------------------- Round 2: G1-G7


def _run_python(code: str, env_extra: dict):
    env = dict(os.environ)
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-c", code], cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=300
    )


def test_g1_csrf_secret_removed_and_demo_seeding_off_by_default():
    from app.core.config import Settings
    assert "CSRF_SECRET" not in Settings.model_fields
    assert Settings.model_fields["SEED_DEMO_ACCOUNTS"].default is False


def test_g2_demo_accounts_seeded_only_when_opted_in_and_default_key_warned():
    db_off = os.path.join(_TMP, "g2_off.db")
    db_on = os.path.join(_TMP, "g2_on.db")
    code = (
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        "with TestClient(app):\n"
        "    pass\n"
        "from app.core.database import SessionLocal\n"
        "from app.models.user import User\n"
        "db = SessionLocal()\n"
        "print('USERS', db.query(User).count())\n"
    )
    off = _run_python(code, {"DATABASE_URL": f"sqlite:///{db_off}", "ENVIRONMENT": "development",
                             "SEED_DEMO_ACCOUNTS": "false"})
    assert "USERS 0" in off.stdout, off.stdout + off.stderr
    assert "DEFAULT development SECRET_KEY" in off.stderr

    on = _run_python(code, {"DATABASE_URL": f"sqlite:///{db_on}", "ENVIRONMENT": "development",
                            "SEED_DEMO_ACCOUNTS": "true"})
    users = [l for l in on.stdout.splitlines() if l.startswith("USERS")]
    assert users and int(users[0].split()[1]) > 0, on.stdout + on.stderr


def test_g3_api_csp_has_no_inline_scripts():
    r = client.get("/api/v1/does-not-exist")
    csp = r.headers.get("content-security-policy", "")
    assert "script-src 'self'" in csp
    script_part = csp.split("style-src")[0]
    assert "'unsafe-inline'" not in script_part


def test_g4_rate_limiter_memory_is_bounded_and_limit_still_applies():
    import types
    from fastapi import HTTPException
    from app.core import rate_limit as rl

    rl._request_history.clear()
    stale = time.time() - 10_000
    for i in range(6000):
        rl._request_history[f"10.0.{i // 256}.{i % 256}:/stale"] = [stale]

    dep = rl.rate_limit(max_requests=5, window_seconds=60)
    req = types.SimpleNamespace(client=types.SimpleNamespace(host="1.2.3.4"),
                                url=types.SimpleNamespace(path="/limited"))
    for _ in range(5):
        dep(req)
    with pytest.raises(HTTPException) as exc:
        dep(req)
    assert exc.value.status_code == 429
    assert len(rl._request_history) < 100  # stale keys were pruned
    rl._request_history.clear()


def test_g5_upload_auto_rename_failure_keeps_file_and_row_consistent(monkeypatch):
    import app.api.v1.endpoints.cases as cases_mod
    from app.core.config import resolve_case_pdf_path
    from app.models.user import User as _U

    db = SessionLocal()
    staff = _user(db, f"g5_{os.urandom(3).hex()}@t.in", "senior_staff")
    db.close()
    _as(staff)

    # Use a unique copy: the seeded DB already holds this PDF, and duplicates are rejected (409).
    src = os.path.join(BACKEND_DIR, "seed_corpus", "pdfs", "01_crl-a-md-1150-2026.pdf")
    pdf = os.path.join(_TMP, f"g5_{os.urandom(4).hex()}.pdf")
    with open(src, "rb") as fh_src, open(pdf, "wb") as fh_dst:
        fh_dst.write(fh_src.read() + b"\n% g5 nonce " + os.urandom(12).hex().encode() + b"\n")

    def failing_replace(src, dst):
        raise OSError("simulated rename failure")

    monkeypatch.setattr(cases_mod.os, "replace", failing_replace)
    with open(pdf, "rb") as fh:
        r = client.post("/api/v1/cases/upload-auto", files={"file": ("judgment.pdf", fh, "application/pdf")})
    assert r.status_code == 201, r.text
    body = r.json()
    case_id = body.get("id") or body.get("case_id")
    assert case_id

    db = SessionLocal()
    row = db.query(Case).filter(Case.id == case_id).one()
    assert os.path.exists(str(resolve_case_pdf_path(row.file_path))), "DB row points at a missing file"
    db.close()


def test_g6_static_verified_claims_removed_from_viewer_and_schema():
    from app.schemas.case import CaseDetailResponse
    assert CaseDetailResponse.model_fields["integrity_status"].default == "not_checked"
    html = open(os.path.join(BACKEND_DIR, "..", "frontend", "case-viewer.html"), encoding="utf-8").read()
    assert "VERIFIED UNALTERED RECORD" not in html.split("<script")[0]
    assert "Verified Copy" not in html
    assert 'id="cert-integrity-badge"' in html


def test_g7_readme_has_no_unmeasured_merkle_or_case_count_claims():
    readme = open(os.path.join(BACKEND_DIR, "..", "README.md"), encoding="utf-8").read()
    # "Merkle" may appear only in a negated statement ("not a Merkle tree").
    assert all("Merkle" not in line or "not a Merkle" in line for line in readme.splitlines())
    assert "208" not in readme
    assert "989" not in readme


# ---------------------------------------------------------------- Round 3: Agent 2 hardening


def test_h1_read_verified_bytes_is_single_read_and_constant_time(tmp_path):
    """The bytes that are verified are the bytes that get served (no re-read window)."""
    from app.services.crypto_service import read_verified_bytes, compute_sha256

    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.4 authentic")
    good = compute_sha256(b"%PDF-1.4 authentic")

    content, computed, ok = read_verified_bytes(str(p), good)
    assert ok and computed == good
    assert content == b"%PDF-1.4 authentic", "caller must receive the verified bytes"

    # Upper-case digest in the DB still matches; comparison is normalised.
    assert read_verified_bytes(str(p), good.upper())[2] is True
    # Empty/absent expected digest is never a pass.
    assert read_verified_bytes(str(p), "")[2] is False
    # Misspelled digest fails.
    assert read_verified_bytes(str(p), "0" * 64)[2] is False

    with pytest.raises(FileNotFoundError):
        read_verified_bytes(str(tmp_path / "missing.pdf"), good)


def test_h2_download_serves_exactly_the_verified_bytes(monkeypatch):
    """
    A file swapped AFTER the integrity read must not reach the client.

    Regression for a verify-then-reopen window: the old implementation verified the
    path and then handed the same path to FileResponse, so a swap between the two
    reads streamed unverified bytes with X-Lexguard-Verified: true.
    """
    import app.services.crypto_service as crypto

    db = SessionLocal()
    staff = _user(db, f"h2_{os.urandom(3).hex()}@t.in", "senior_staff")
    reader = _user(db, f"h2r_{os.urandom(3).hex()}@t.in", "advocate")
    case = _case_with_file(db, staff, b"%PDF authentic payload " * 30, status="published")
    case_id, path = case.id, case.file_path
    db.close()

    real = crypto.read_verified_bytes

    def read_then_swap(file_path, expected_hash):
        result = real(file_path, expected_hash)
        with open(path, "wb") as fh:          # swap the file after verification
            fh.write(b"%PDF swapped payload " * 30)
        return result

    monkeypatch.setattr(crypto, "read_verified_bytes", read_then_swap)

    _as(reader)
    r = client.get(f"/api/v1/cases/{case_id}/download")
    assert r.status_code == 200, r.text
    assert r.headers.get("x-lexguard-verified") == "true"
    assert b"authentic payload" in r.content
    assert b"swapped payload" not in r.content, "download served bytes it did not verify"
    # The response digest must describe the served bytes, not just the DB value.
    assert r.headers.get("x-lexguard-sha256") == hashlib.sha256(r.content).hexdigest()


def test_h3_download_missing_file_is_404_and_logs_no_verified_header():
    db = SessionLocal()
    staff = _user(db, f"h3_{os.urandom(3).hex()}@t.in", "senior_staff")
    reader = _user(db, f"h3r_{os.urandom(3).hex()}@t.in", "advocate")
    case = _case_with_file(db, staff, b"%PDF gone " * 30, status="published")
    case_id, path = case.id, case.file_path
    os.remove(path)
    db.close()

    _as(reader)
    r = client.get(f"/api/v1/cases/{case_id}/download")
    assert r.status_code == 404, r.text
    assert "x-lexguard-verified" not in r.headers


def test_h4_verify_integrity_returns_seal_and_audit_link_status():
    """GET /cases/{id}/verify-integrity must report Phi_case and the audit link state."""
    db = SessionLocal()
    uploader = _user(db, f"h4_{os.urandom(3).hex()}@t.in", "senior_staff")
    approver = _user(db, f"h4a_{os.urandom(3).hex()}@t.in", "senior_staff")
    case_id = _publish(db, uploader, approver, body=b"%PDF sealed doc " * 40)
    db.close()

    _as(approver)
    r = client.get(f"/api/v1/cases/{case_id}/verify-integrity")
    assert r.status_code == 200, r.text
    data = r.json()

    # File level (original contract kept)
    assert data["is_valid"] is True
    assert data["status_badge"] == "VERIFIED_UNTAMPERED"
    assert data["file_present"] is True and data["bytes_verified"] is True

    # Digital seal Phi_case
    assert data["seal_present"] is True
    assert data["composite_seal"] and len(data["composite_seal"]) == 64
    assert data["seal_reproducible"] is True
    assert data["recomputed_seal"] == data["composite_seal"]
    assert data["approve_log_found"] is True
    assert data["integrity_status"] == "SEAL_VERIFIED"
    assert set(data["sealed_components"]) == {"H_doc", "H_meta", "H_text", "T_approved"}

    # Audit link status for this record
    assert data["audit_entries_checked"] >= 1
    assert data["audit_link_ok"] is True
    assert data["audit_hashes_ok"] is True
    assert all(e["recomputed_ok"] and e["link_ok"] for e in data["audit_trail"])


def test_h5_verify_integrity_detects_seal_drift_and_file_mismatch():
    db = SessionLocal()
    uploader = _user(db, f"h5_{os.urandom(3).hex()}@t.in", "senior_staff")
    approver = _user(db, f"h5a_{os.urandom(3).hex()}@t.in", "senior_staff")
    case_id = _publish(db, uploader, approver, body=b"%PDF drift doc " * 40)
    case = db.query(Case).filter(Case.id == case_id).one()
    path = case.file_path
    case.judge = "Someone Else"                      # breaks H_meta -> seal drift
    db.commit()
    db.close()

    _as(approver)
    data = client.get(f"/api/v1/cases/{case_id}/verify-integrity").json()
    assert data["is_valid"] is True                  # bytes still fine
    assert data["seal_reproducible"] is False        # seal does not
    assert data["integrity_status"] == "SEAL_MISMATCH"
    assert data["recomputed_seal"] != data["composite_seal"]

    with open(path, "r+b") as fh:                    # now tamper the bytes too
        fh.write(b"X")
    data2 = client.get(f"/api/v1/cases/{case_id}/verify-integrity").json()
    assert data2["is_valid"] is False
    assert data2["status_badge"] == "INTEGRITY_VIOLATION"
    assert data2["integrity_status"] == "FILE_HASH_MISMATCH"

    db = SessionLocal()
    assert db.query(AuditLog).filter(
        AuditLog.case_id == case_id, AuditLog.action == "INTEGRITY_VIOLATION"
    ).count() >= 1, "a failed file check must be recorded as a tamper event"
    db.close()


def test_h6_queue_submitter_cannot_approve_their_own_submission():
    """Maker-checker covers the reviewer who queued the record, not just the uploader."""
    from app.models.approval_queue import ApprovalQueue

    db = SessionLocal()
    uploader = _user(db, f"h6_{os.urandom(3).hex()}@t.in", "senior_staff")
    queue_maker = _user(db, f"h6q_{os.urandom(3).hex()}@t.in", "senior_staff")
    case = _case_with_file(db, uploader, b"%PDF queued doc " * 40, status="pending_review")
    case_id = case.id
    db.add(ApprovalQueue(case_id=case_id, submitted_by_id=queue_maker.id, status="pending"))
    db.commit()
    db.close()

    _as(queue_maker)
    r = client.post(f"/api/v1/admin/approve/{case_id}", json={"status": "published"})
    assert r.status_code == 403, r.text
    assert "Maker-checker" in r.text


def test_h7_quarantined_record_cannot_be_published_while_bytes_still_fail():
    db = SessionLocal()
    uploader = _user(db, f"h7_{os.urandom(3).hex()}@t.in", "senior_staff")
    approver = _user(db, f"h7a_{os.urandom(3).hex()}@t.in", "senior_staff")
    case = _case_with_file(db, uploader, b"%PDF quarantined doc " * 40, status="quarantined")
    case_id, path = case.id, case.file_path
    db.close()

    with open(path, "r+b") as fh:              # still corrupt
        fh.write(b"X")

    _as(approver)
    r = client.post(f"/api/v1/admin/approve/{case_id}", json={"status": "published"})
    assert r.status_code == 409, r.text
    assert "Quarantined" in r.text


def test_h8_ledger_head_and_verification_use_the_same_order():
    """
    Head selection and chain verification must walk the ledger in one order.

    AuditLog.id is a UUID string (no insertion order), so an id-ordered head would
    fork the chain whenever timestamps and UUIDs disagree.
    """
    from app.services.audit_service import get_chain_head_hash, ledger_entries, verify_ledger

    db = _isolated_session()
    for i in range(4):
        log_audit_event(db, action=f"H8_EVENT_{i}", details=f"e{i}")

    entries = ledger_entries(db)
    assert len(entries) == 4
    assert get_chain_head_hash(db) == entries[-1].current_hash

    result = verify_ledger(db)
    assert result["is_valid"], result
    db.close()


def test_h9_link_check_rejects_a_forward_or_self_link():
    from app.services.audit_service import build_audit_entry, check_audit_entry

    db = _isolated_session()
    first = AuditLog(**build_audit_entry(None, action="H9_FIRST", details="a"))
    db.add(first)
    db.commit()

    # A row claiming the genesis parent is fine.
    assert check_audit_entry(db, first) == {"recomputed_ok": True, "link_ok": True}

    # A row pointing at itself must not verify as a link.
    selflink = AuditLog(**build_audit_entry("0" * 64, action="H9_SELF", details="b"))
    db.add(selflink)
    db.commit()
    selflink.previous_log_hash = selflink.current_hash
    db.commit()
    assert check_audit_entry(db, selflink)["link_ok"] is False

    # A row whose parent is in the future (later timestamp) must not verify either.
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    future = AuditLog(**build_audit_entry("0" * 64, action="H9_FUTURE",
                                          timestamp=_dt.now(_tz.utc) + _td(days=1), details="c"))
    db.add(future)
    db.commit()
    child = AuditLog(**build_audit_entry(future.current_hash, action="H9_CHILD", details="d"))
    db.add(child)
    db.commit()
    assert check_audit_entry(db, child)["link_ok"] is False
    db.close()


def test_h10_published_is_frozen_until_explicitly_quarantined():
    """
    Spec 2, second clause: a published record cannot be mutated *without explicit
    quarantine status*.

    The positive half matters as much as the 409: without a quarantine step that
    reopens editing, "reject and resubmit" is the only recovery path, and a record
    found to be bad after publication could never be corrected in place.
    """
    db = SessionLocal()
    uploader = _user(db, f"h10_{os.urandom(3).hex()}@t.in", "senior_staff")
    reviewer = _user(db, f"h10r_{os.urandom(3).hex()}@t.in", "senior_staff")
    case_id = _publish(db, uploader, reviewer, body=b"%PDF quarantine flow " * 40)
    db.close()

    _as(reviewer)

    # 1. Published -> frozen.
    blocked = client.patch(f"/api/v1/cases/{case_id}", json={"judge": "Edited While Published"})
    assert blocked.status_code == 409, blocked.text
    assert "sealed" in blocked.text.lower()

    # 2. Explicit quarantine (the only sanctioned unlock).
    q = client.post(f"/api/v1/admin/approve/{case_id}", json={"status": "quarantined",
                                                             "review_note": "integrity review"})
    assert q.status_code == 200, q.text
    assert q.json()["status"] == "quarantined"

    # 3. Quarantined -> mutable again, and the edit is recorded.
    allowed = client.patch(f"/api/v1/cases/{case_id}", json={"judge": "Corrected After Quarantine"})
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["judge"] == "Corrected After Quarantine"

    db = SessionLocal()
    assert db.query(AuditLog).filter(
        AuditLog.case_id == case_id, AuditLog.action == "UPDATE_METADATA"
    ).count() == 1, "the post-quarantine edit must be in the audit trail"
    db.close()
