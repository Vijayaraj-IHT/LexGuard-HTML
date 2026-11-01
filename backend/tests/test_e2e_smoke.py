"""
End-to-end smoke tests for the LexGuard stack (Agent 5: Performance, Test & QA).

Validates, against a hermetic temporary SQLite database:
  1. API health            — GET /health and GET /
  2. Search                — POST /api/v1/search/ with an empty (browse) query and
                             with real hybrid queries (empty + no-hit included)
  3. Integrity lookup      — POST /api/v1/verification/lookup and
                             GET  /api/v1/verification/lookup/{hash}
  4. Bare acts catalog     — GET /api/v1/statutes/acts and GET /api/v1/statutes/
  5. Static serving proxy  — scripts/serve.py serving frontend/ and reverse-proxying
                             /api/* to a live uvicorn backend (real subprocesses)

The tests never touch the repository database: a dedicated temp SQLite file is
created and injected via a `get_db` dependency override, and the proxy test boots
uvicorn with DATABASE_URL pointing at the same temp file.

Run from the repository root:
    python -m pytest backend/tests/test_e2e_smoke.py -v
or from backend/:
    python -m pytest tests/test_e2e_smoke.py -v
"""

import hashlib
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
SERVE_PY = REPO_ROOT / "scripts" / "serve.py"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Hermetic environment — must be set before the app package is imported.
_TMP_DIR = tempfile.mkdtemp(prefix="lexguard_e2e_smoke_")
TEST_DB_PATH = os.path.join(_TMP_DIR, "e2e_smoke.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["ENVIRONMENT"] = "development"
os.environ.setdefault("SEED_DEMO_ACCOUNTS", "false")

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.database import Base, get_db  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.main import app  # noqa: E402
from app.models.case import Case  # noqa: E402
from app.models.statute import StatuteSection  # noqa: E402
from app.models.user import User  # noqa: E402

# ---------------------------------------------------------------------------
# Hermetic database: own engine + dependency override, independent of cwd
# ---------------------------------------------------------------------------

test_engine = create_engine(
    f"sqlite:///{TEST_DB_PATH}",
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

KNOWN_SHA256 = hashlib.sha256(b"lexguard-e2e-known-document").hexdigest()
UNKNOWN_SHA256 = hashlib.sha256(b"lexguard-e2e-unregistered-document").hexdigest()

PUBLISHED_CASES = 5


def _seed_database():
    Base.metadata.create_all(bind=test_engine)
    db = TestingSessionLocal()
    try:
        user = User(
            id=str(uuid.uuid4()),
            name="E2E Tester",
            email="e2e@test.local",
            password_hash=get_password_hash("e2e-test-password"),
            role="staff",
            status="active",
        )
        db.add(user)
        db.flush()

        cases = [
            Case(
                id=str(uuid.uuid4()),
                case_no=f"E2E-TEST-{i + 1}/2026",
                title=title,
                court="Madras High Court (Principal Seat)",
                year=2026,
                judge="Hon'ble Justice E2E",
                summary=summary,
                facts=f"Facts of e2e test case {i + 1}.",
                ratio_decidendi=ratio,
                full_text=full_text,
                outcome="Allowed" if i % 2 == 0 else "Dismissed",
                disposition="Allowed" if i % 2 == 0 else "Dismissed",
                act_tags=acts,
                section_tags=sections,
                keyword_tags=keywords,
                file_path=f"storage/cases/e2e_{i + 1}.pdf",
                file_hash=KNOWN_SHA256 if i == 0 else hashlib.sha256(f"e2e-doc-{i}".encode()).hexdigest(),
                status="published",
                uploaded_by_id=user.id,
            )
            for i, (title, summary, ratio, full_text, acts, sections, keywords) in enumerate([
                (
                    "Anticipatory Bail in NDPS Offence",
                    "Petition for anticipatory bail under Section 438 CrPC in an NDPS Act case.",
                    "Anticipatory bail may be granted where custodial interrogation is not required.",
                    "--- PAGE 1 ---\nThe petitioner seeks anticipatory bail under Section 438 CrPC. "
                    "The offence is under the NDPS Act. The court considers parity and mens rea.\n"
                    "--- PAGE 2 ---\nBail is allowed with conditions.",
                    ["NDPS Act", "CrPC"],
                    ["Section 438 CrPC", "Section 37 NDPS Act"],
                    ["anticipatory bail", "bail", "NDPS"],
                ),
                (
                    "Murder Conviction under Section 302 IPC",
                    "Appeal against conviction for murder under Section 302 IPC.",
                    "Conviction under Section 302 IPC upheld on proof of mens rea beyond reasonable doubt.",
                    "--- PAGE 1 ---\nThe accused is charged with murder under Section 302 IPC. "
                    "Culpable homicide amounts to murder.\n--- PAGE 2 ---\nAppeal dismissed.",
                    ["IPC"],
                    ["Section 302 IPC"],
                    ["murder", "conviction", "mens rea"],
                ),
                (
                    "Quashing of FIR under Section 482 CrPC",
                    "Petition to quash FIR alleging abuse of process of court.",
                    "FIR quashed where allegations do not disclose a prima facie offence.",
                    "--- PAGE 1 ---\nThe petitioner seeks quashing of the FIR under Section 482 CrPC. "
                    "Settlement reached between parties.\n--- PAGE 2 ---\nFIR quashed.",
                    ["CrPC"],
                    ["Section 482 CrPC"],
                    ["quashing", "FIR", "prima facie"],
                ),
                (
                    "Dishonour of Cheque under NI Act Section 138",
                    "Complaint under Section 138 of the Negotiable Instruments Act for cheque bounce.",
                    "Presumption under Section 139 NI Act applies; accused must rebut it.",
                    "--- PAGE 1 ---\nCheque dishonoured. Notice issued under Section 138 NI Act. "
                    "Complaint filed before the magistrate.\n--- PAGE 2 ---\nConviction recorded.",
                    ["NI Act"],
                    ["Section 138 NI Act"],
                    ["cheque", "dishonour", "negotiable instruments"],
                ),
                (
                    "Habeas Corpus Petition for Missing Person",
                    "Habeas corpus petition seeking production of a missing person.",
                    "State directed to produce the detenue; habeas corpus made absolute.",
                    "--- PAGE 1 ---\nHabeas corpus petition filed. The person is missing in custody. "
                    "The court issues notice.\n--- PAGE 2 ---\nRule made absolute.",
                    ["Constitution of India"],
                    ["Article 226 Constitution"],
                    ["habeas corpus", "custody", "missing person"],
                ),
            ])
        ]
        # One non-published case must never leak into public search results
        draft = Case(
            id=str(uuid.uuid4()),
            case_no="E2E-DRAFT-9/2026",
            title="Draft Judgment Not For Public Search",
            court="Supreme Court of India",
            year=2026,
            file_path="storage/cases/e2e_draft.pdf",
            file_hash=hashlib.sha256(b"e2e-draft").hexdigest(),
            status="pending_approval",
            uploaded_by_id=user.id,
        )
        db.add(draft)

        db.add_all(cases)
        db.add_all([
            StatuteSection(
                id=str(uuid.uuid4()),
                act_code="CRPC",
                act_title="Code of Criminal Procedure, 1973",
                section_no="438",
                section_title="Anticipatory bail",
                bare_text="When any person has reason to believe that he may be arrested...",
                explanation="Direction for anticipatory bail to the High Court or Court of Session.",
                case_count=1,
            ),
            StatuteSection(
                id=str(uuid.uuid4()),
                act_code="IPC",
                act_title="Indian Penal Code, 1860",
                section_no="302",
                section_title="Punishment for murder",
                bare_text="Whoever commits murder shall be punished with death...",
                explanation="Punishment for the offence of murder.",
                case_count=1,
            ),
        ])
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="module")
def client():
    _seed_database()
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# 1. API health
# ---------------------------------------------------------------------------

def test_health_endpoint(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert body["database_connected"] is True
    assert "Lexguard" in body["system"]


def test_root_metadata_endpoint(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "online"
    assert body["api_docs"] == "/api/v1/docs"


# ---------------------------------------------------------------------------
# 2. Search: empty (browse) and query-based hybrid search
# ---------------------------------------------------------------------------

def test_search_empty_query_browses_published_cases(client):
    r = client.post("/api/v1/search/", json={"query": "", "limit": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == PUBLISHED_CASES  # draft case must be excluded
    assert len(body["results"]) == PUBLISHED_CASES
    for item in body["results"]:
        assert item["match_type"] == "browse"
        assert item["id"] and item["case_no"] and item["title"]
        assert len(item["file_hash"]) == 64


def test_search_hybrid_query_returns_ranked_results(client):
    r = client.post("/api/v1/search/", json={"query": "anticipatory bail under section 438 CrPC", "limit": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    top = body["results"][0]
    assert "bail" in top["title"].lower()
    assert top["match_type"] in {"keyword", "statute", "related", "hybrid"}
    assert top["relevance_score"] is not None
    assert top["repository_id"].startswith("LG-")
    assert "query_understanding" in body


def test_search_query_with_advanced_syntax(client):
    r = client.post(
        "/api/v1/search/",
        json={"query": '"mens rea" AND murder NOT acquittal', "limit": 10},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["query_understanding"]["is_advanced_syntax"] is True
    assert body["query_understanding"]["required_phrases"] == ["mens rea"]
    assert body["total"] >= 1
    # the murder case carries both the quoted phrase and the AND term -> rank #1
    assert "murder" in body["results"][0]["title"].lower()


def test_search_boolean_not_excludes_matching_cases(client):
    r = client.post("/api/v1/search/", json={"query": "bail NOT ndps", "limit": 10})
    assert r.status_code == 200
    body = r.json()
    # the only seeded case mentioning NDPS (the anticipatory-bail one) is excluded
    assert body["total"] == PUBLISHED_CASES - 1
    for item in body["results"]:
        haystack = (item["title"] + " " + (item["summary"] or "") + " " + " ".join(item["keyword_tags"])).lower()
        assert "ndps" not in haystack


def test_search_nonsense_query_still_returns_ranked_browse_results(client):
    # The RRF engine ranks all published candidates even when no token hits;
    # it must still answer 200 with a well-formed ranked payload.
    r = client.post("/api/v1/search/", json={"query": "zzqqxxy nonexistent gibberish", "limit": 10})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == PUBLISHED_CASES
    assert len(body["results"]) == PUBLISHED_CASES
    assert all(item["relevance_score"] is not None for item in body["results"])


def test_search_respects_pagination(client):
    page1 = client.post("/api/v1/search/", json={"query": "", "limit": 2, "offset": 0})
    page2 = client.post("/api/v1/search/", json={"query": "", "limit": 2, "offset": 2})
    assert page1.status_code == 200 and page2.status_code == 200
    ids1 = {i["id"] for i in page1.json()["results"]}
    ids2 = {i["id"] for i in page2.json()["results"]}
    assert len(ids1) == 2 and len(ids2) == 2
    assert ids1.isdisjoint(ids2)


# ---------------------------------------------------------------------------
# 3. Document integrity lookup
# ---------------------------------------------------------------------------

def test_verification_lookup_registered_hash_matches(client):
    r = client.post("/api/v1/verification/lookup", json={"sha256_hash": KNOWN_SHA256})
    assert r.status_code == 200
    body = r.json()
    assert body["matched"] is True
    assert body["integrity_status"] in {"VERIFIED", "REGISTERED", "MATCHED"} or body["matched"]
    assert body["case"]["case_no"] == "E2E-TEST-1/2026"
    assert body["case"]["file_hash"] == KNOWN_SHA256
    assert body["case"]["h_meta"] and len(body["case"]["h_meta"]) == 64


def test_verification_lookup_get_variant_matches(client):
    r = client.get(f"/api/v1/verification/lookup/{KNOWN_SHA256}")
    assert r.status_code == 200
    assert r.json()["matched"] is True


def test_verification_lookup_unregistered_hash(client):
    r = client.post("/api/v1/verification/lookup", json={"sha256_hash": UNKNOWN_SHA256})
    assert r.status_code == 200
    body = r.json()
    assert body["matched"] is False
    assert body["integrity_status"] == "UNREGISTERED"
    assert body["case"] is None


def test_verification_lookup_rejects_malformed_hash(client):
    r = client.post("/api/v1/verification/lookup", json={"sha256_hash": "not-a-hash"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# 4. Bare acts catalog
# ---------------------------------------------------------------------------

def test_statutes_acts_catalog(client):
    r = client.get("/api/v1/statutes/acts")
    assert r.status_code == 200
    acts = r.json()
    assert isinstance(acts, list) and len(acts) == 2
    codes = {a["act_code"] for a in acts}
    assert codes == {"CRPC", "IPC"}
    for a in acts:
        assert a["section_count"] == 1
        assert a["total_cases"] == 1
        assert a["act_title"]


def test_statutes_sections_listing_and_detail(client):
    r = client.get("/api/v1/statutes/")
    assert r.status_code == 200
    sections = r.json()
    assert len(sections) == 2

    r = client.get("/api/v1/statutes/CRPC/438")
    assert r.status_code == 200
    assert r.json()["section_no"] == "438"

    r = client.get("/api/v1/statutes/CRPC/999")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 5. Static serving proxy (scripts/serve.py) against a live uvicorn backend
# ---------------------------------------------------------------------------

def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for_http(url: str, timeout: float = 40.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=2.0).status_code < 500:
                return True
        except Exception:
            time.sleep(0.25)
    return False


@pytest.fixture(scope="module")
def live_stack():
    """Boot uvicorn (API) + scripts/serve.py (static + proxy) on ephemeral ports."""
    backend_port = _free_port()
    proxy_port = _free_port()
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
    env["ENVIRONMENT"] = "development"

    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(backend_port)],
        cwd=str(BACKEND_DIR), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    proxy_proc = subprocess.Popen(
        [sys.executable, str(SERVE_PY),
         "--bind", "127.0.0.1", "--port", str(proxy_port),
         "--backend", f"http://127.0.0.1:{backend_port}"],
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        assert _wait_for_http(f"http://127.0.0.1:{backend_port}/health"), "uvicorn backend did not start"
        assert _wait_for_http(f"http://127.0.0.1:{proxy_port}/index.html"), "serve.py proxy did not start"
        yield {
            "backend": f"http://127.0.0.1:{backend_port}",
            "proxy": f"http://127.0.0.1:{proxy_port}",
        }
    finally:
        for proc in (proxy_proc, backend_proc):
            proc.terminate()
        for proc in (proxy_proc, backend_proc):
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def test_serve_py_serves_frontend_pages(live_stack):
    proxy = live_stack["proxy"]
    for page in ["/", "/index.html", "/search.html", "/login.html", "/verify.html", "/404.html"]:
        r = httpx.get(proxy + page, timeout=10)
        assert r.status_code == 200, f"{page} -> {r.status_code}"
        assert "text/html" in r.headers.get("content-type", "")


def test_serve_py_serves_static_assets(live_stack):
    proxy = live_stack["proxy"]
    assets = [
        "/css/lexguard.css",
        "/css/components.css",
        "/js/lexguard-core.js",
        "/js/lexguard-api.js",
        "/js/pages/search.js",
        "/favicon.svg",
        "/favicon.ico",
    ]
    for asset in assets:
        r = httpx.get(proxy + asset, timeout=10)
        assert r.status_code == 200, f"{asset} -> {r.status_code}"
        assert len(r.content) > 0


def test_serve_py_proxies_api_to_backend(live_stack):
    proxy = live_stack["proxy"]
    backend = live_stack["backend"]

    # health on the backend itself
    r = httpx.get(backend + "/health", timeout=10)
    assert r.status_code == 200 and r.json()["status"] == "healthy"

    # API calls through the one-origin proxy
    r = httpx.get(proxy + "/api/v1/statutes/acts", timeout=10)
    assert r.status_code == 200
    assert {a["act_code"] for a in r.json()} == {"CRPC", "IPC"}

    r = httpx.post(proxy + "/api/v1/search/", json={"query": "anticipatory bail", "limit": 5}, timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert "bail" in body["results"][0]["title"].lower()

    r = httpx.post(proxy + "/api/v1/verification/lookup", json={"sha256_hash": KNOWN_SHA256}, timeout=10)
    assert r.status_code == 200 and r.json()["matched"] is True


def test_serve_py_returns_404_for_missing_assets(live_stack):
    proxy = live_stack["proxy"]
    r = httpx.get(proxy + "/js/definitely-missing-file.js", timeout=10)
    assert r.status_code == 404
    # the custom 404 page itself must be reachable with 200
    r = httpx.get(proxy + "/404.html", timeout=10)
    assert r.status_code == 200
