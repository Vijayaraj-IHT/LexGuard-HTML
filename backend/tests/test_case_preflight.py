"""Tests for the case-file preflight service, endpoints, migration and CLI.

Everything runs against a temporary SQLite file that is created by this module. The
database engine used by the endpoints/CLI is monkeypatched to that file, so the
repository's ``backend/lexguard.db`` is never opened for writing, no matter which
test module pytest imported first.

Run from backend/:
    python -m pytest tests/test_case_preflight.py -q
"""
import hashlib
import json
import os
import sys
import tempfile

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

_TMP_DIR = tempfile.mkdtemp(prefix="lg_preflight_test_")
_TEST_DB = os.path.join(_TMP_DIR, "preflight.db")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main_module  # noqa: E402
import app.services.case_preflight_service as svc  # noqa: E402
import preflight_cases  # noqa: E402
from app.api.v1.endpoints import system as system_module  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.security import get_current_user  # noqa: E402
from app.models.case import Case  # noqa: E402
from app.models.preflight import CasePreflightRun  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.crypto_service import compute_sha256  # noqa: E402
import importlib.util  # noqa: E402

engine = create_engine(f"sqlite:///{_TEST_DB}", connect_args={"check_same_thread": False})
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)

STATUS_POSTGRES_REQUIRED = "POSTGRES_REQUIRED"
STATUS_BUSY = "BUSY"
STATUS_COMPLETED = "COMPLETED"
STATUS_ISSUES = "COMPLETED_WITH_ISSUES"
STATUS_REPAIRED = "REPAIRED"


def _load_migration_module():
    path = os.path.join(BACKEND_DIR, "migrations", "002_add_case_preflight_runs.py")
    spec = importlib.util.spec_from_file_location("migration_002", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration_002 = _load_migration_module()


# --------------------------------------------------------------------------- setup
@pytest.fixture(scope="module", autouse=True)
def _schema():
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_tables():
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM case_preflight_runs"))
        conn.execute(text("DELETE FROM cases"))
    yield


@pytest.fixture()
def session():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


def _make_pdf(name="judgment.pdf", content=b"%PDF-1.4 test judgment body"):
    path = os.path.join(_TMP_DIR, name)
    with open(path, "wb") as fh:
        fh.write(content)
    return path, hashlib.sha256(content).hexdigest()


def _add_case(db, *, case_id="case-1", file_path=None, file_hash=None, status="published", **overrides):
    values = dict(
        id=case_id,
        case_no="WP No. 1 of 2024",
        title="State v. Example",
        court="Madras High Court",
        year=2024,
        file_path=file_path or os.path.join(_TMP_DIR, "does-not-exist.pdf"),
        file_hash=file_hash or ("a" * 64),
        status=status,
        uploaded_by_id="user-1",
        act_tags=[],
        section_tags=[],
        keyword_tags=[],
    )
    values.update(overrides)
    case = Case(**values)
    db.add(case)
    db.commit()
    return case


# --------------------------------------------------------------------------- service
def test_refuses_non_postgres_by_default(session):
    run = svc.run_case_preflight(session, mode="verify", trigger="test")

    assert run.status == STATUS_POSTGRES_REQUIRED
    assert run.finished_at is not None
    assert run.report_json["dialect"] == "sqlite"
    assert "PostgreSQL" in run.report_json["message"]
    assert run.report_json["advisory_lock"]["held"] is False
    assert session.query(CasePreflightRun).count() == 1


def test_verify_classifies_each_failure_mode(session):
    good_path, good_hash = _make_pdf("good.pdf")
    bad_path, _ = _make_pdf("tampered.pdf")
    other_path, other_hash = _make_pdf("other.pdf", b"%PDF-1.4 different body")

    _add_case(session, case_id="case-good", file_path=good_path, file_hash=good_hash)
    _add_case(session, case_id="case-missing", file_path=os.path.join(_TMP_DIR, "nope.pdf"))
    _add_case(session, case_id="case-mismatch", file_path=bad_path, file_hash="b" * 64)
    _add_case(
        session,
        case_id="case-invalid",
        file_path=other_path,
        file_hash=other_hash,
        case_no="Civil Appeal No. 3843 of 2020",
        year=1961,
    )

    run = svc.run_case_preflight(session, mode="verify", trigger="test", allow_non_postgres=True)

    assert run.total_cases == 4
    assert run.verified_count == 1
    assert run.missing_count == 1
    assert run.mismatch_count == 1
    assert run.invalid_metadata_count == 1
    assert run.duplicate_hash_count == 0
    assert run.status == STATUS_ISSUES

    report = run.report_json
    assert report["metadata_reasons"]["year_conflicts_with_case_no"] == 1
    assert "case-missing" in report["samples"]["missing"]
    assert "case-mismatch" in report["samples"]["mismatch"]
    assert "case-invalid" in report["samples"]["invalid_metadata"]


def test_clean_corpus_reports_completed(session):
    path, digest = _make_pdf("clean.pdf")
    _add_case(session, case_id="case-clean", file_path=path, file_hash=digest)

    run = svc.run_case_preflight(session, mode="verify", allow_non_postgres=True)

    assert run.status == STATUS_COMPLETED
    assert (run.verified_count, run.missing_count, run.mismatch_count) == (1, 0, 0)


def test_duplicate_hashes_are_counted(session):
    path, digest = _make_pdf("dup.pdf")
    _add_case(session, case_id="dup-a", file_path=path, file_hash=digest)
    _add_case(session, case_id="dup-b", file_path=path, file_hash=digest)

    run = svc.run_case_preflight(session, mode="verify", allow_non_postgres=True)

    assert run.duplicate_hash_count == 2
    assert run.report_json["duplicates"] == {"hashes": 1, "cases": 2}
    assert run.verified_count == 2  # duplicates are informational, not a failure


def test_invalid_metadata_reasons_unit():
    def case(**kw):
        base = dict(case_no="WP No. 1 of 2024", title="T", court="C", year=2024)
        base.update(kw)
        c = Case()
        for key, value in base.items():
            setattr(c, key, value)
        return c

    assert svc.invalid_metadata_reasons(case()) == []
    assert "missing_title" in svc.invalid_metadata_reasons(case(title="  "))
    assert "missing_year" in svc.invalid_metadata_reasons(case(year=None))
    assert "impossible_year" in svc.invalid_metadata_reasons(case(year=1800))
    assert "year_conflicts_with_case_no" in svc.invalid_metadata_reasons(
        case(case_no="Civil Appeal No. 3843 of 2020", year=1961)
    )
    # One-year tolerance: a 2023 case number and a 2024 decision date are fine.
    assert svc.invalid_metadata_reasons(case(case_no="SLP (C) No. 9 of 2023", year=2024)) == []


def test_repair_quarantines_mismatches(session):
    path, _ = _make_pdf("repair.pdf")
    _add_case(session, case_id="case-bad", file_path=path, file_hash="c" * 64)

    run = svc.run_case_preflight(
        session,
        mode="repair",
        trigger="cli",
        allow_non_postgres=True,
        quarantine_mismatch=True,
    )

    assert run.status == STATUS_REPAIRED
    assert run.report_json["repair"]["quarantined_count"] == 1
    assert session.get(Case, "case-bad").status == "quarantined"


def test_verify_mode_never_mutates_status(session):
    path, _ = _make_pdf("nomutate.pdf")
    _add_case(session, case_id="case-keep", file_path=path, file_hash="d" * 64, status="published")

    svc.run_case_preflight(session, mode="verify", allow_non_postgres=True)

    assert session.get(Case, "case-keep").status == "published"


def test_busy_when_advisory_lock_unavailable(session, monkeypatch):
    monkeypatch.setattr(svc, "is_postgres", lambda db: True)
    monkeypatch.setattr(svc, "_try_advisory_lock", lambda db, key: False)

    path, digest = _make_pdf("busy.pdf")
    _add_case(session, case_id="case-busy", file_path=path, file_hash=digest)

    run = svc.run_case_preflight(session, mode="verify", trigger="web_manual")

    assert run.status == STATUS_BUSY
    assert run.report_json["advisory_lock"] == {"id": svc.lock_id(), "held": False}
    assert run.total_cases == 0


def test_lock_is_released_after_run(session, monkeypatch):
    released = []
    monkeypatch.setattr(svc, "is_postgres", lambda db: True)
    monkeypatch.setattr(svc, "_try_advisory_lock", lambda db, key: True)
    monkeypatch.setattr(svc, "_release_advisory_lock", lambda db, key: released.append(key))

    path, digest = _make_pdf("locked.pdf")
    _add_case(session, case_id="case-lock", file_path=path, file_hash=digest)

    run = svc.run_case_preflight(session, mode="verify")

    assert run.report_json["advisory_lock"]["held"] is True
    assert released == [svc.lock_id()]


def test_report_never_leaks_filesystem_paths(session):
    _add_case(session, case_id="case-path", file_path=os.path.join(_TMP_DIR, "secret.pdf"))

    run = svc.run_case_preflight(session, mode="verify", allow_non_postgres=True, verify_hashes=False)
    payload = json.dumps(run.report_json)

    assert _TMP_DIR not in payload
    assert "file_path" not in payload
    assert ".pdf" not in payload


# --------------------------------------------------------------------------- endpoints
@pytest.fixture()
def client(monkeypatch):
    def _db_override():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    staff = User(id="staff-1", email="staff@court.gov.in", role="court_staff", name="Staff")
    public = User(id="public-1", email="citizen@example.com", role="public", name="Citizen")
    state = {"user": staff}

    main_module.app.dependency_overrides[get_db] = _db_override
    main_module.app.dependency_overrides[get_current_user] = lambda: state["user"]
    monkeypatch.setattr(system_module, "SessionLocal", TestSession)
    monkeypatch.setattr(system_module.settings, "PREFLIGHT_THROTTLE_SECONDS", 60, raising=False)
    monkeypatch.setattr(system_module.settings, "PREFLIGHT_ALLOW_NON_POSTGRES", True, raising=False)

    test_client = TestClient(main_module.app)
    test_client.public_user = public  # type: ignore[attr-defined]
    test_client.state = state  # type: ignore[attr-defined]
    try:
        yield test_client
    finally:
        main_module.app.dependency_overrides.clear()


def test_latest_returns_404_before_any_run(client):
    response = client.get("/api/v1/system/case-preflight/latest")
    assert response.status_code == 404


def test_run_endpoint_is_throttled_and_reports_latest(client):
    path, digest = _make_pdf("endpoint.pdf")
    db = TestSession()
    try:
        _add_case(db, case_id="case-endpoint", file_path=path, file_hash=digest)
    finally:
        db.close()

    first = client.post("/api/v1/system/case-preflight/run")
    assert first.status_code == 202
    body = first.json()
    assert body["status"] == "QUEUED"
    run_id = body["id"]

    # TestClient runs background tasks before returning, so the run is already done.
    latest = client.get("/api/v1/system/case-preflight/latest")
    assert latest.status_code == 200
    summary = latest.json()
    assert summary["id"] == run_id
    assert summary["status"] in (STATUS_COMPLETED, STATUS_ISSUES)
    assert summary["total_cases"] == 1
    assert "report" in summary and "dialect" in summary["report"]

    single = client.get(f"/api/v1/system/case-preflight/{run_id}")
    assert single.status_code == 200
    assert single.json()["id"] == run_id

    second = client.post("/api/v1/system/case-preflight/run")
    assert second.status_code == 429
    assert "Retry-After" in second.headers


def test_run_endpoint_requires_staff_role(client):
    client.state["user"] = client.public_user
    response = client.post("/api/v1/system/case-preflight/run")
    assert response.status_code == 403


def test_missing_ledger_table_self_heals(client):
    """A database created before this feature must not 500 on the first read."""
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE case_preflight_runs"))
    assert inspect(engine).has_table("case_preflight_runs") is False

    assert client.get("/api/v1/system/case-preflight/latest").status_code == 404
    assert inspect(engine).has_table("case_preflight_runs") is True


def test_unknown_run_id_returns_404(client):
    assert client.get("/api/v1/system/case-preflight/does-not-exist").status_code == 404


def test_latest_never_exposes_paths(client):
    db = TestSession()
    try:
        _add_case(db, case_id="case-secret", file_path=os.path.join(_TMP_DIR, "hidden.pdf"))
    finally:
        db.close()

    client.post("/api/v1/system/case-preflight/run")
    payload = client.get("/api/v1/system/case-preflight/latest").text

    assert _TMP_DIR not in payload
    assert "hidden.pdf" not in payload


def test_ledger_ddl_is_jsonb_on_postgres_and_text_on_sqlite():
    """Same model, dialect-specific column type: JSONB in production, TEXT locally."""
    from sqlalchemy.dialects import postgresql, sqlite
    from sqlalchemy.schema import CreateTable

    pg_ddl = str(CreateTable(CasePreflightRun.__table__).compile(dialect=postgresql.dialect()))
    lite_ddl = str(CreateTable(CasePreflightRun.__table__).compile(dialect=sqlite.dialect()))

    assert "JSONB" in pg_ddl
    assert "JSONB" not in lite_ddl
    assert "report_json TEXT" in lite_ddl


# --------------------------------------------------------------------------- migration / CLI
def test_migration_creates_table_and_indexes(monkeypatch):
    monkeypatch.setattr(migration_002, "engine", engine)

    first = migration_002.run()
    assert first["table_created"] is False  # table exists from the fixture's create_all
    inspector = inspect(engine)
    assert inspector.has_table("case_preflight_runs")
    index_names = {ix["name"] for ix in inspector.get_indexes("cases")}
    assert {"ix_cases_file_hash", "ix_cases_cnr_number", "ix_cases_decision_date", "ix_cases_status"} <= index_names

    second = migration_002.run()  # idempotent
    assert second["indexes_created"] == []
    assert set(second["indexes_present"]) == {
        "ix_cases_file_hash",
        "ix_cases_cnr_number",
        "ix_cases_decision_date",
        "ix_cases_status",
    }


def test_cli_refuses_sqlite_without_flag(monkeypatch, capsys):
    monkeypatch.setattr(preflight_cases, "engine", engine)
    monkeypatch.setattr(preflight_cases, "SessionLocal", TestSession)

    code = preflight_cases.main(["--json"])

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == STATUS_POSTGRES_REQUIRED


def test_cli_runs_on_sqlite_with_flag(monkeypatch, capsys):
    monkeypatch.setattr(preflight_cases, "engine", engine)
    monkeypatch.setattr(preflight_cases, "SessionLocal", TestSession)

    path, digest = _make_pdf("cli.pdf")
    db = TestSession()
    try:
        _add_case(db, case_id="case-cli", file_path=path, file_hash=digest)
    finally:
        db.close()

    code = preflight_cases.main(["--allow-sqlite", "--json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == STATUS_COMPLETED
    assert payload["verified_count"] == 1
