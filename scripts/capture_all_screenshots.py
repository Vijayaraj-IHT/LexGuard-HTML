import os
import subprocess
import requests

ARTIFACT_DIR = r"C:\Users\Vijay Raj\.gemini\antigravity\brain\bf49bd7f-191f-466f-8220-3857aab9ae1c\screenshots"
os.makedirs(ARTIFACT_DIR, exist_ok=True)

EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

# Pre-fetch a real case id from PostgreSQL
case_id = "a460d112-b2ba-4095-8a37-4427303392d4"
case_id_2 = "6598d00f-ad95-4529-a60e-299ac778c25b"

try:
    r = requests.post("http://127.0.0.1:8000/api/v1/search/", json={"query": "", "limit": 2, "offset": 0}, timeout=5)
    if r.status_code == 200:
        results = r.json().get("results", [])
        if len(results) >= 1:
            case_id = results[0]["id"]
        if len(results) >= 2:
            case_id_2 = results[1]["id"]
except Exception as e:
    print(f"Warning: could not fetch dynamic case id: {e}")

# Also get a live staff auth token from backend
staff_token = ""
try:
    r = requests.post("http://127.0.0.1:8000/api/v1/auth/login", json={"email": "staff@court.gov.in", "password": "staff123"}, timeout=5)
    if r.status_code == 200:
        staff_token = r.json().get("access_token", "")
except Exception as e:
    print(f"Warning: could not fetch staff token: {e}")

auth_params = f"auth_token={staff_token}&auth_role=staff" if staff_token else "auth_role=staff"

targets = [
    # --- PHASE 1: REACT 18 / VITE SPA (Port 5173) ---
    {
        "name": "react_01_landing.png",
        "url": "http://127.0.0.1:5173/",
        "title": "Phase 1 (React) - Official Portal Landing Page"
    },
    {
        "name": "react_02_login.png",
        "url": "http://127.0.0.1:5173/login",
        "title": "Phase 1 (React) - Judicial Staff & Advocate Login"
    },
    {
        "name": "react_03_register.png",
        "url": "http://127.0.0.1:5173/register",
        "title": "Phase 1 (React) - User & Bar Registration"
    },
    {
        "name": "react_04_search_public.png",
        "url": "http://127.0.0.1:5173/search/public",
        "title": "Phase 1 (React) - Precedent Hybrid Search"
    },
    {
        "name": "react_05_acts_explorer.png",
        "url": "http://127.0.0.1:5173/acts",
        "title": "Phase 1 (React) - Statutory Acts & BNS Concordance"
    },
    {
        "name": "react_06_verify_public.png",
        "url": "http://127.0.0.1:5173/verify/public",
        "title": "Phase 1 (React) - SHA-256 Tamper Verification"
    },
    {
        "name": "react_07_dashboard_staff.png",
        "url": f"http://127.0.0.1:5173/dashboard?{auth_params}",
        "title": "Phase 1 (React) - Staff Admin Executive Dashboard"
    },
    {
        "name": "react_08_search_auth.png",
        "url": f"http://127.0.0.1:5173/search?{auth_params}",
        "title": "Phase 1 (React) - Authenticated Workspace Search"
    },
    {
        "name": "react_09_case_viewer.png",
        "url": f"http://127.0.0.1:5173/cases/{case_id}?{auth_params}",
        "title": "Phase 1 (React) - Judicial Case Detail & Reader"
    },
    {
        "name": "react_10_case_review.png",
        "url": f"http://127.0.0.1:5173/review/{case_id}?{auth_params}",
        "title": "Phase 1 (React) - Human-in-the-Loop CIS Review"
    },
    {
        "name": "react_11_case_compare.png",
        "url": f"http://127.0.0.1:5173/compare?case1={case_id}&case2={case_id_2}&{auth_params}",
        "title": "Phase 1 (React) - Multi-Case Comparative Matrix"
    },
    {
        "name": "react_12_audit_ledger.png",
        "url": f"http://127.0.0.1:5173/admin/audit?{auth_params}",
        "title": "Phase 1 (React) - Merkle Cryptographic Audit Ledger"
    },
    {
        "name": "react_13_case_upload.png",
        "url": f"http://127.0.0.1:5173/upload?{auth_params}",
        "title": "Phase 1 (React) - Case Ingestion & CIS Extraction"
    },

    # --- PHASE 2: HTML5 / BOOTSTRAP 5 / JQUERY (Port 8888) ---
    {
        "name": "html_01_login.png",
        "url": "http://127.0.0.1:8888/login.html",
        "title": "Phase 2 (HTML5) - Multi-Role Quick Access Login"
    },
    {
        "name": "html_02_register.png",
        "url": "http://127.0.0.1:8888/register.html",
        "title": "Phase 2 (HTML5) - User Registration Form"
    },
    {
        "name": "html_03_search_results.png",
        "url": "http://127.0.0.1:8888/search.html",
        "title": "Phase 2 (HTML5) - Precedent Hybrid Search"
    },
    {
        "name": "html_04_dashboard_admin.png",
        "url": f"http://127.0.0.1:8888/admin.html?{auth_params}",
        "title": "Phase 2 (HTML5) - Staff Analytics & Ingest Queue"
    },
    {
        "name": "html_05_case_viewer_pdf.png",
        "url": f"http://127.0.0.1:8888/case-viewer.html?id={case_id}&{auth_params}",
        "title": "Phase 2 (HTML5) - Advanced PDF.js Viewer & Dossier"
    },
    {
        "name": "html_06_case_review_split.png",
        "url": f"http://127.0.0.1:8888/case-review.html?id={case_id}&{auth_params}",
        "title": "Phase 2 (HTML5) - Split-Screen Staff CIS Review"
    },
    {
        "name": "html_07_case_compare_tray.png",
        "url": f"http://127.0.0.1:8888/case-compare.html?case1={case_id}&case2={case_id_2}",
        "title": "Phase 2 (HTML5) - 3-Precedent Tray & BNSS Matrix"
    },
    {
        "name": "html_08_draft_assistant.png",
        "url": f"http://127.0.0.1:8888/draft-assistant.html?case_id={case_id}",
        "title": "Phase 2 (HTML5) - AI Judgment Draft Assistant Studio"
    },
    {
        "name": "html_09_acts_explorer.png",
        "url": "http://127.0.0.1:8888/acts-explorer.html",
        "title": "Phase 2 (HTML5) - Major Indian Statutory Acts Catalog"
    },
    {
        "name": "html_10_verify_tamper.png",
        "url": "http://127.0.0.1:8888/verify.html",
        "title": "Phase 2 (HTML5) - SHA-256 Tamper Verification Engine"
    },
    {
        "name": "html_11_cause_list.png",
        "url": "http://127.0.0.1:8888/cause-list.html",
        "title": "Phase 2 (HTML5) - Madras High Court Daily Cause List"
    }
]

print(f"=== Starting LexGuard Visual Capture Suite ({len(targets)} targets) ===")
captured = []

for idx, t in enumerate(targets, 1):
    out_file = os.path.join(ARTIFACT_DIR, t["name"])
    print(f"[{idx}/{len(targets)}] Capturing: {t['title']} -> {t['name']}...")
    cmd = [
        EDGE_EXE,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-software-rasterizer",
        "--virtual-time-budget=3500",
        "--window-size=1440,900",
        f"--screenshot={out_file}",
        t["url"]
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=14)
        if os.path.exists(out_file) and os.path.getsize(out_file) > 1000:
            size_kb = os.path.getsize(out_file) / 1024
            print(f"   [SUCCESS] Saved ({size_kb:.1f} KB)")
            captured.append({"title": t["title"], "filename": t["name"], "size_kb": size_kb, "path": out_file})
        else:
            print(f"   [FAILED] File missing or empty (returncode {proc.returncode})")
    except subprocess.TimeoutExpired:
        print(f"   [TIMEOUT] Execution exceeded 14s")
    except Exception as e:
        print(f"   [ERROR] {e}")

print(f"\nCompleted {len(captured)} of {len(targets)} captures successfully.")
