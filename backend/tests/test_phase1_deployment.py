"""Phase-1 deployment/admin-surface regression tests.

Phase 1 makes LexGuard deployable as one free Render web service backed by
Neon PostgreSQL and completes the senior-admin browser surface for the
Phase-0 governance endpoints.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"


def test_settings_normalize_provider_database_urls_and_environment():
    neon = Settings(
        ENVIRONMENT=" Production ",
        SECRET_KEY="x" * 40,
        COOKIE_SECURE=True,
        COOKIE_SAMESITE="LAX",
        DATABASE_URL="postgres://user:pass@ep-example.aws.neon.tech/neondb?sslmode=require",
        CORS_ORIGINS=["https://lexguard.onrender.com"],
    )
    assert neon.ENVIRONMENT == "production"
    assert neon.COOKIE_SAMESITE == "lax"
    assert neon.DATABASE_URL.startswith("postgresql+psycopg2://user:pass@ep-example")

    plain = Settings(DATABASE_URL="postgresql://user:pass@localhost:5432/lexguard")
    assert plain.DATABASE_URL.startswith("postgresql+psycopg2://")
    # Canonical dumps use JSON embeddings; native pgvector is explicit opt-in.
    assert plain.USE_PGVECTOR is False


def test_production_settings_reject_wildcard_cors_with_cookie_auth():
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="y" * 40,
            COOKIE_SECURE=True,
            CORS_ORIGINS=["*"],
        )


def test_health_is_liveness_only_and_readiness_checks_dependencies(client):
    health = client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "healthy"
    assert body["version"]
    # Phase 1 removed the old unconditional (and potentially false) claim.
    assert "database_connected" not in body
    assert "content-security-policy" in health.headers

    ready = client.get("/ready")
    assert ready.status_code == 200, ready.text
    ready_body = ready.json()
    assert ready_body["status"] == "ready"
    assert ready_body["ready"] is True
    assert ready_body["checks"] == {
        "database": True,
        "schema": True,
        "storage": True,
        "frontend": True,
    }

    root = client.get("/")
    api_root = client.get("/api")
    assert root.status_code == 200
    assert api_root.status_code == 200
    assert root.json()["status"] == "online"
    assert app.title


def test_single_service_mode_serves_frontend_same_origin():
    """Boot a fresh interpreter with SERVE_FRONTEND=true (Render topology)."""
    code = textwrap.dedent(
        """
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)

        root = client.get("/")
        assert root.status_code == 200, root.text[:200]
        assert "LexGuard" in root.text
        assert "text/html" in root.headers.get("content-type", "")
        csp = root.headers.get("content-security-policy", "")
        assert "https://cdnjs.cloudflare.com" in csp
        assert "frame-ancestors 'none'" in csp

        login = client.get("/login.html")
        assert login.status_code == 200
        assert "LexGuard" in login.text

        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["frontend_served"] is True

        missing = client.get("/no-such-page.html", headers={"Accept": "text/html"})
        assert missing.status_code == 404
        assert "LexGuard" in missing.text

        api_missing = client.get("/api/v1/no-such-endpoint")
        assert api_missing.status_code == 404
        assert api_missing.json()["error"] == "Not Found"
        print("single-service frontend OK")
        """
    )

    env = os.environ.copy()
    env.update(
        {
            "SERVE_FRONTEND": "true",
            "FRONTEND_DIR": str(REPO_ROOT / "frontend"),
            "ENVIRONMENT": "development",
            "COOKIE_SECURE": "False",
            "USE_LOCAL_LLM": "False",
            "USE_MOCK_LLM": "True",
            "PYTHONPATH": str(BACKEND_DIR),
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "single-service frontend OK" in result.stdout


def test_frontend_api_base_is_same_origin_outside_local_static_ports():
    core = (REPO_ROOT / "frontend/js/lexguard-core.js").read_text()
    acts = (REPO_ROOT / "frontend/js/pages/acts-explorer.js").read_text()
    api = (REPO_ROOT / "frontend/js/lexguard-api.js").read_text()

    assert "window.location.origin + '/api/v1'" in core
    assert "LEXGUARD_API_BASE_URL" in core
    assert core.count("http://127.0.0.1:8000/api/v1") == 1  # local fallback only
    assert "LG.api.statutes.getActs()" in acts
    assert "LG.api.statutes.getSection(actCode, secNo)" in acts
    assert "127.0.0.1:8000" not in acts
    assert "statutes:" in api
    assert "system:" in api


def test_render_blueprint_and_production_requirements_are_free_tier_safe():
    yaml = pytest.importorskip("yaml")
    blueprint = yaml.safe_load((REPO_ROOT / "render.yaml").read_text())
    [service] = blueprint["services"]

    assert service["type"] == "web"
    assert service["runtime"] == "python"
    assert service["plan"] == "free"
    assert service["healthCheckPath"] == "/health"
    assert "requirements-prod.txt" in service["buildCommand"]
    assert "backend/start.sh" in service["startCommand"]

    env = {item["key"]: item for item in service["envVars"]}
    assert env["SERVE_FRONTEND"]["value"] is True
    assert env["RUN_MIGRATIONS"]["value"] is True
    assert env["USE_LOCAL_LLM"]["value"] is False
    assert env["DATABASE_URL"]["sync"] is False
    assert env["SECRET_KEY"]["generateValue"] is True

    prod_packages = [
        line.strip().lower()
        for line in (BACKEND_DIR / "requirements-prod.txt").read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert not any(package.startswith("torch") for package in prod_packages)
    assert not any(package.startswith("transformers") for package in prod_packages)
    assert not any(package.startswith("sentence-transformers") for package in prod_packages)

    start_script = (BACKEND_DIR / "start.sh").read_text()
    assert "RUN_MIGRATIONS" in start_script
    assert "migrate_phase0.py" in start_script
    assert "--host 0.0.0.0" in start_script
    assert "${PORT:-8000}" in start_script


def test_admin_workstation_exposes_senior_users_and_reseal_ui():
    html = (REPO_ROOT / "frontend/admin.html").read_text()
    js = (REPO_ROOT / "frontend/js/pages/admin.js").read_text()

    for marker in [
        'id="users-tab-item"',
        'id="tab-admin-users"',
        'id="createUserModal"',
        'id="editUserModal"',
        'id="resealModal"',
        'id="chain-segments-body"',
        'id="posture-readiness"',
    ]:
        assert marker in html

    for marker in [
        "LG.api.admin.getUsers",
        "LG.api.admin.createUser",
        "LG.api.admin.updateUser",
        "LG.api.admin.resealAuditChain",
        "LG.api.system.readiness",
        "renderChainSegments",
        "isSeniorAdmin",
    ]:
        assert marker in js
