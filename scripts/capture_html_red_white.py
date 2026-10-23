import os
import shutil
import subprocess
import time
import requests

ARTIFACT_SCREENSHOTS = r"C:\Users\Vijay Raj\.gemini\antigravity\brain\bf49bd7f-191f-466f-8220-3857aab9ae1c\screenshots"
HTML_SCREENSHOTS = r"E:\SEM 5 PROJECT\Lexguard\lexguard-html\screenshots"
os.makedirs(ARTIFACT_SCREENSHOTS, exist_ok=True)
os.makedirs(HTML_SCREENSHOTS, exist_ok=True)

EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.exists(EDGE_EXE):
    EDGE_EXE = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"

# 1. Fetch dynamic cases from live backend
case_id = "a460d112-b2ba-4095-8a37-4427303392d4"
case_id_2 = "6598d00f-ad95-4529-a60e-299ac778c25b"

try:
    r = requests.post("http://127.0.0.1:8000/api/v1/search/", json={"query": "", "limit": 4, "offset": 0}, timeout=5)
    if r.status_code == 200:
        results = r.json().get("results", [])
        if len(results) >= 1:
            case_id = results[0]["id"]
        if len(results) >= 2:
            case_id_2 = results[1]["id"]
        print(f"Fetched live cases: case_1={case_id}, case_2={case_id_2}")
except Exception as e:
    print(f"Warning: could not fetch dynamic case id: {e}")

# 2. Staff token
staff_token = ""
try:
    r = requests.post("http://127.0.0.1:8000/api/v1/auth/login", json={"email": "staff@court.gov.in", "password": "staff123"}, timeout=5)
    if r.status_code == 200:
        staff_token = r.json().get("access_token", "")
        print(f"Acquired staff authentication token.")
except Exception as e:
    print(f"Warning: could not fetch staff token: {e}")

auth_params = f"auth_token={staff_token}&auth_role=staff" if staff_token else "auth_role=staff"

targets = [
    {
        "name": "html_00_landing.png",
        "url": "http://127.0.0.1:8888/index.html",
        "title": "High Court Portal & 10-Service Grid (Court Red & White)",
        "wait_ms": 2500
    },
    {
        "name": "html_01_login.png",
        "url": "http://127.0.0.1:8888/login.html",
        "title": "Multi-Role Quick Access Login",
        "wait_ms": 2000
    },
    {
        "name": "html_02_register.png",
        "url": "http://127.0.0.1:8888/register.html",
        "title": "Citizen & Bar Registration Form",
        "wait_ms": 2000
    },
    {
        "name": "html_03_search_results.png",
        "url": "http://127.0.0.1:8888/search.html",
        "title": "Hybrid Precedent Search & Live DB",
        "wait_ms": 3500
    },
    {
        "name": "html_04_dashboard_admin.png",
        "url": f"http://127.0.0.1:8888/admin.html?{auth_params}",
        "title": "Staff Analytics & Approval Queue (Chart.js Crimson)",
        "wait_ms": 4000
    },
    {
        "name": "html_05_case_viewer_pdf.png",
        "url": f"http://127.0.0.1:8888/case-viewer.html?id={case_id}&{auth_params}",
        "title": "Advanced PDF.js Viewer & Dossier",
        "wait_ms": 4000
    },
    {
        "name": "html_06_case_review_split.png",
        "url": f"http://127.0.0.1:8888/case-review.html?id={case_id}&{auth_params}",
        "title": "Split-Screen Staff CIS Review",
        "wait_ms": 3500
    },
    {
        "name": "html_07_case_compare_tray.png",
        "url": f"http://127.0.0.1:8888/case-compare.html?case1={case_id}&case2={case_id_2}",
        "title": "3-Precedent Tray & Concordance Matrix",
        "wait_ms": 3000
    },
    {
        "name": "html_08_draft_assistant.png",
        "url": f"http://127.0.0.1:8888/draft-assistant.html?case_id={case_id}",
        "title": "AI Judgment Draft Assistant Studio",
        "wait_ms": 3000
    },
    {
        "name": "html_09_acts_explorer.png",
        "url": "http://127.0.0.1:8888/acts-explorer.html",
        "title": "Major Indian Acts Catalog",
        "wait_ms": 2500
    },
    {
        "name": "html_10_verify_tamper.png",
        "url": "http://127.0.0.1:8888/verify.html",
        "title": "SHA-256 Tamper Verification Engine",
        "wait_ms": 2500
    },
    {
        "name": "html_11_cause_list.png",
        "url": "http://127.0.0.1:8888/cause-list.html",
        "title": "Madras HC Daily Cause List Tracker",
        "wait_ms": 3500
    },
    {
        "name": "html_12_audit_ledger.png",
        "url": "http://127.0.0.1:8888/audit-ledger.html",
        "title": "Cryptographic Merkle Audit Ledger",
        "wait_ms": 3500
    },
    {
        "name": "html_13_case_viewer_upgraded.png",
        "url": f"http://127.0.0.1:8888/case-viewer.html?id={case_id}",
        "title": "Upgraded Case Reader & Keyword Finder",
        "wait_ms": 3500
    },
    {
        "name": "html_14_404_page.png",
        "url": "http://127.0.0.1:8888/404.html",
        "title": "Judicial 404 Not Found Portal (Light Theme)",
        "wait_ms": 2000
    },
    {
        "name": "html_15_cause_list_live.png",
        "url": "http://127.0.0.1:8888/cause-list.html",
        "title": "Live Daily Cause List & Court Board",
        "wait_ms": 3500
    },
    {
        "name": "html_16_case_viewer_404.png",
        "url": "http://127.0.0.1:8888/case-viewer.html?id=999999",
        "title": "Graceful 404 Docket Handler in Viewer",
        "wait_ms": 2500
    },
    {
        "name": "html_17_gallery.png",
        "url": "http://127.0.0.1:8888/screenshots-gallery.html",
        "title": "Visual Audit Showcase Gallery",
        "wait_ms": 3000
    }
]

print(f"=== Starting Court Red & White Visual Capture Suite ({len(targets)} targets) ===")
captured = []

for idx, t in enumerate(targets, 1):
    artifact_path = os.path.join(ARTIFACT_SCREENSHOTS, t["name"])
    html_path = os.path.join(HTML_SCREENSHOTS, t["name"])
    print(f"[{idx}/{len(targets)}] Capturing: {t['title']} -> {t['name']}...")
    
    cmd = [
        EDGE_EXE,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-software-rasterizer",
        f"--virtual-time-budget={t['wait_ms']}",
        "--window-size=1440,920",
        f"--screenshot={artifact_path}",
        t["url"]
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=16)
        if os.path.exists(artifact_path) and os.path.getsize(artifact_path) > 1000:
            # Sync to HTML screenshots directory
            shutil.copy2(artifact_path, html_path)
            size_kb = os.path.getsize(artifact_path) / 1024
            print(f"   [SUCCESS] Saved ({size_kb:.1f} KB) to Artifacts and HTML folders")
            captured.append({"title": t["title"], "filename": t["name"], "size_kb": size_kb})
        else:
            print(f"   [FAILED] File missing or empty (returncode {proc.returncode})")
    except subprocess.TimeoutExpired:
        print(f"   [TIMEOUT] Execution exceeded timeout")
    except Exception as e:
        print(f"   [ERROR] {e}")

print(f"\nSuccessfully captured {len(captured)} of {len(targets)} screens in Court Red & White.")
