#!/usr/bin/env python3
"""
Lexguard seed-corpus loader.

Reads backend/seed_corpus/manifest.json and uploads every PDF in
backend/seed_corpus/pdfs/ to a running Lexguard backend through the
normal staff upload endpoint (POST /api/v1/cases/upload), preserving
the curated metadata (case_no, title, court, year, judge, parties,
act/section/keyword tags, summary).

Features:
  * Verifies each file's SHA-256 against the manifest before upload.
  * Logs in with HttpOnly cookie + double-submit CSRF token (same flow
    as the React frontend).
  * Treats HTTP 409 (duplicate hash) as an expected, non-fatal outcome.
  * Optional --approve flag publishes uploaded cases via
    POST /api/v1/admin/approve/{case_id} (court_staff/senior_staff).

Usage:
  export LEXGUARD_EMAIL="staff@lexguard.example"   # court_staff or senior_staff
  export LEXGUARD_PASSWORD="..."
  python backend/seed_corpus/seed_corpus.py --verify-only     # hashes only, no server
  python backend/seed_corpus/seed_corpus.py                   # upload all (pending approval)
  python backend/seed_corpus/seed_corpus.py --approve         # upload + publish
  python backend/seed_corpus/seed_corpus.py --limit 3         # smoke test

Environment:
  LEXGUARD_BASE_URL   default http://localhost:8000
  LEXGUARD_EMAIL      staff account email (required for upload)
  LEXGUARD_PASSWORD   staff account password (required for upload)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:  # only needed for upload; --verify-only works without it
    requests = None  # type: ignore[assignment]

HERE = Path(__file__).resolve().parent
MANIFEST_PATH = HERE / "manifest.json"
PDF_DIR = HERE / "pdfs"
DEFAULT_BASE_URL = os.environ.get("LEXGUARD_BASE_URL", "http://localhost:8000")
CSRF_COOKIE = "lexguard_csrf_token"
CSRF_HEADER = "X-CSRF-Token"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest() -> dict:
    with MANIFEST_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def verify_hashes(documents: list[dict]) -> tuple[list[dict], list[str]]:
    """Return (verified_docs, problems). Missing/corrupt files are reported."""
    verified: list[dict] = []
    problems: list[str] = []
    for doc in documents:
        path = PDF_DIR / doc["file"]
        if not path.exists():
            problems.append(f"MISSING  {doc['file']}")
            continue
        actual = sha256_file(path)
        if actual != doc["sha256"]:
            problems.append(
                f"MODIFIED {doc['file']}\n"
                f"         expected {doc['sha256']}\n"
                f"         actual   {actual}"
            )
            continue
        size = path.stat().st_size
        if size != doc["size_bytes"]:
            problems.append(f"SIZE-MISMATCH {doc['file']} ({size} != {doc['size_bytes']})")
            continue
        verified.append(doc)
    return verified, problems


def login(session: requests.Session, base_url: str, email: str, password: str) -> None:
    resp = session.post(
        f"{base_url}/api/v1/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    if resp.status_code != 200:
        raise SystemExit(
            f"Login failed ({resp.status_code}): {resp.text[:400]}\n"
            "Use a court_staff or senior_staff account and check "
            "LEXGUARD_EMAIL / LEXGUARD_PASSWORD / LEXGUARD_BASE_URL."
        )
    if CSRF_COOKIE not in session.cookies:
        raise SystemExit("Login succeeded but no CSRF cookie was set — check backend config.")


def upload_case(session: requests.Session, base_url: str, doc: dict) -> dict:
    """Upload one manifest entry. Returns {'status': 'uploaded'|'duplicate'|..., ...}."""
    path = PDF_DIR / doc["file"]
    data = {
        "case_no": doc["case_no"],
        "title": doc["title"],
        "court": doc["court"],
        "year": str(doc["year"]),
        "judge": doc.get("judge") or "",
        "parties": doc.get("parties") or "",
        "act_tags": json.dumps(doc.get("act_tags") or []),
        "section_tags": json.dumps(doc.get("section_tags") or []),
        "keyword_tags": json.dumps(doc.get("keyword_tags") or []),
        "summary": doc.get("summary") or "",
        "outcome": doc.get("outcome") or "",
    }
    headers = {CSRF_HEADER: session.cookies.get(CSRF_COOKIE, "")}
    with path.open("rb") as fh:
        resp = session.post(
            f"{base_url}/api/v1/cases/upload",
            data=data,
            files={"file": (doc["file"], fh, "application/pdf")},
            headers=headers,
            timeout=120,
        )

    if resp.status_code == 201:
        return {"status": "uploaded", "case": resp.json()}
    if resp.status_code == 409:
        return {"status": "duplicate", "detail": resp.text[:200]}
    if resp.status_code == 401:
        raise SystemExit(f"Session expired/unauthorised during upload: {resp.text[:300]}")
    if resp.status_code == 403:
        return {"status": "forbidden", "detail": resp.text[:300]}
    return {"status": "error", "detail": f"HTTP {resp.status_code}: {resp.text[:300]}"}


def approve_case(session: requests.Session, base_url: str, case_id: str, note: str) -> bool:
    headers = {CSRF_HEADER: session.cookies.get(CSRF_COOKIE, "")}
    resp = session.post(
        f"{base_url}/api/v1/admin/approve/{case_id}",
        json={"status": "published", "review_note": note},
        headers=headers,
        timeout=30,
    )
    return resp.status_code == 200


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Lexguard with the Drive judgment corpus.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Backend base URL")
    parser.add_argument("--limit", type=int, default=0, help="Upload only the first N documents")
    parser.add_argument("--approve", action="store_true", help="Publish each case after upload")
    parser.add_argument("--verify-only", action="store_true", help="Only verify manifest hashes; needs no server")
    parser.add_argument("--delay", type=float, default=0.2, help="Pause between uploads (seconds)")
    args = parser.parse_args()

    manifest = load_manifest()
    documents = manifest["documents"]
    print(f"Manifest: {MANIFEST_PATH}")
    print(f"Documents: {len(documents)} | expected total bytes: {manifest.get('total_bytes')}")

    verified, problems = verify_hashes(documents)
    if problems:
        print("\nIntegrity problems detected:")
        for p in problems:
            print(f"  - {p}")
    print(f"Hash verification: {len(verified)}/{len(documents)} OK")

    if args.verify_only:
        return 1 if problems else 0

    if problems:
        print("Refusing to upload while integrity problems exist (re-download those files).")
        return 1

    if requests is None:
        print("The 'requests' package is required for uploading (pip install requests).")
        return 2

    email = os.environ.get("LEXGUARD_EMAIL")
    password = os.environ.get("LEXGUARD_PASSWORD")
    if not email or not password:
        print("Set LEXGUARD_EMAIL and LEXGUARD_PASSWORD (court_staff / senior_staff).")
        return 2

    session = requests.Session()
    login(session, args.base_url, email, password)
    print(f"Logged in as {email} → {args.base_url}")

    targets = verified[: args.limit] if args.limit else verified
    counts = {"uploaded": 0, "duplicate": 0, "published": 0, "skipped": 0}
    failures: list[str] = []

    for idx, doc in enumerate(targets, 1):
        result = upload_case(session, args.base_url, doc)
        label = f"[{idx}/{len(targets)}] {doc['file']} → {doc['case_no']}"
        if result["status"] == "uploaded":
            counts["uploaded"] += 1
            case = result["case"]
            line = f"{label}  OK (id={case.get('id', '?')[:8]}…)"
            if args.approve:
                ok = approve_case(session, args.base_url, case["id"], "Seeded from Drive corpus (auto-approved)")
                if ok:
                    counts["published"] += 1
                    line += " [published]"
                else:
                    line += " [approve FAILED]"
                    failures.append(doc["file"])
            print(line)
        elif result["status"] == "duplicate":
            counts["duplicate"] += 1
            print(f"{label}  DUPLICATE (already in repository)")
        elif result["status"] == "forbidden":
            counts["skipped"] += 1
            print(f"{label}  FORBIDDEN — account lacks court_staff/senior_staff role")
            failures.append(doc["file"])
        else:
            failures.append(doc["file"])
            print(f"{label}  ERROR — {result.get('detail', '')}")
        time.sleep(args.delay)

    print("\n=== Seed summary ===")
    print(f"uploaded: {counts['uploaded']} | duplicates: {counts['duplicate']} | "
          f"published: {counts['published']} | failures: {len(failures)}")
    if failures:
        print("Failures:")
        for f in failures:
            print(f"  - {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
