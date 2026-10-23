# 🏛️ LexGuard — High Court Judicial Case Repository & Verification Platform

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-v0.110+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-336791?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![HTML5](https://img.shields.io/badge/Frontend-Pure%20HTML5%20%2F%20Bootstrap%205-E34F26?logo=html5&logoColor=white)](https://getbootstrap.com/)
[![Design System](https://img.shields.io/badge/Theme-High%20Court%20Red%20%26%20White-991b1b)](https://github.com/Vijayaraj-IHT/LexGuard-HTML)
[![Cryptography](https://img.shields.io/badge/Security-SHA--256%20%7C%20Merkle%20Ledger-059669)](https://developer.mozilla.org/en-US/docs/Web/API/Web_Crypto_API)
[![License: MIT](https://img.shields.io/badge/License-MIT-amber.svg)](LICENSE)

> **High Court of Judicature at Madras · Chennai Principal Seat & Madurai Bench**  
> An enterprise-grade, zero-build judicial case repository and cryptographic document verification system designed for Court Staff, Judicial Registrars, Advocates, and Legal Researchers.

---

## 📸 Visual Execution Showcase

| High Court Portal Landing (10-Service Grid) | Precedent Hybrid Search (208 Live Cases) |
| :---: | :---: |
| ![Landing](frontend/screenshots/html_00_landing.png) | ![Search](frontend/screenshots/html_03_search_results.png) |

| Staff CIS Workstation & Chart.js Analytics | Advanced PDF.js Viewer & Dossier |
| :---: | :---: |
| ![Admin](frontend/screenshots/html_04_dashboard_admin.png) | ![Viewer](frontend/screenshots/html_05_case_viewer_pdf.png) |

*(Explore all 31 full-resolution output states inside the interactive [`frontend/screenshots-gallery.html`](frontend/screenshots-gallery.html))*

---

## ⚖️ Key Architectural Highlights

* **Pure HTML5 / Bootstrap 5 / jQuery Client (Zero-Build Frontend)**:
  * No `npm`, `node_modules`, `webpack`, or `vite` required.
  * Instant execution directly from any web browser or lightweight HTTP server.
  * Native Web Crypto API integration for client-side zero-byte SHA-256 calculation.
* **High Court Red & White Design System**:
  * Authentic judicial palette: Deep Crimson (`#991b1b`), Maroon (`#7f1d1d`), and Pristine White (`#ffffff` / `#f8fafc`).
  * Dark charcoal slate typography (`#0f172a`) providing high contrast and compliance with court readability standards.
  * Replaced dark background cards with clean elevated judicial panels and subtle crimson borders (`rgba(185, 28, 28, 0.15)`).
* **Robust FastAPI & PostgreSQL 17 Backend**:
  * 208 precedent judgments indexed with InLegalBERT statutory embeddings and full-text vectors.
  * Merkle tree audit ledger with 989 immutable SHA-256 hash-chained records.
  * OWASP A02/A07 defense: SecurityHeadersMiddleware, Double-Submit Cookie CSRF protection, and HttpOnly JWT cookies.

---

## 🏛️ 10 High Court Authorized Services & Portals

1. **Case Status / CNR Lookup** (`search.html`): Search by 16-digit CNR, Filing Number, FIR, or Judge Name.
2. **Precedent Hybrid Search** (`search.html`): Reciprocal Rank Fusion (RRF) combining dense semantic vectors and statutory full-text search.
3. **Statutory Acts & Concordance** (`acts-explorer.html`): Directory covering IPC, Cr.P.C., Evidence Act, and automatic concordance mapping to Bharatiya Nyaya Sanhita (BNS) 2023.
4. **SHA-256 Tamper Verification Engine** (`verify.html`): Drag-and-drop client-side file digest computation validated against the PostgreSQL audit ledger.
5. **Multi-Precedent Comparator** (`case-compare.html`): Side-by-side legal ratio decidendi divergence and Cr.P.C. 1973 ↔ BNSS 2023 concordance matrix.
6. **Staff CIS Review Workstation** (`case-review.html`): Split-screen human-in-the-loop review with PDF on the left and editable CIS docket fields on the right.
7. **AI Judgment Draft Studio** (`draft-assistant.html`): Structured judicial drafting environment with session persistence and statutory audit stepper.
8. **Madras HC Daily Cause List Tracker** (`cause-list.html`): Court board tracker displaying courtroom serials, benches, and live hearing status.
9. **Cryptographic Merkle Audit Ledger** (`audit-ledger.html`): Real-time blockchain-style hash chain inspector verifying data integrity and tamper seals.
10. **Case Ingestion Desk** (`case-upload.html`): PDF ingest pipeline with InLegalBERT entity extraction and automated SHA-256 sealing.

---

## ⚡ 1-Minute Quick Start

### Prerequisites
* **Python 3.10+**
* **PostgreSQL 17** (or 14+) with database `lexguard` created

### 🚀 Windows (1-Click Launcher)
Simply double-click:
```cmd
start_windows.bat
```
*This script will create the virtualenv, install dependencies, start the backend on port 8000, start the HTML frontend on port 8888, and automatically open your default browser!*

### 🐧 Linux / macOS
```bash
chmod +x start_linux.sh
./start_linux.sh
```

---

## 🛠️ Manual Step-by-Step Setup

### 1. Clone the Repository
```bash
git clone https://github.com/Vijayaraj-IHT/LexGuard-HTML.git
cd LexGuard-HTML
```

### 2. Backend Setup
```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

### 3. Database Restoration (208 Cases & Merkle Audit Logs)
Ensure PostgreSQL is running, then restore the included database dump:
```bash
# Windows / Linux / macOS
psql -U lexguard -d lexguard -f ../database/lexguard_dump.sql
```
*(Default credentials in `.env.example`: User: `lexguard`, Password: `lexguard123`, DB: `lexguard`)*

### 4. Launch Services
**Terminal 1 (FastAPI Backend on port 8000):**
```bash
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2 (HTML5 Frontend on port 8888):**
```bash
cd frontend
python -m http.server 8888
```

Open your browser to: **`http://127.0.0.1:8888/index.html`**

---

## 🔑 Demo Access Personas

The database comes pre-seeded with authorized credentials for all four judicial roles:

| Role | Email | Password | Access Privileges |
| :--- | :--- | :--- | :--- |
| **Chief Registrar (Staff)** | `staff@court.gov.in` | `staff123` | CIS Moderation, Merkle Audit Ledger, Ingestion Desk, Analytics |
| **Senior Advocate** | `advocate@bar.in` | `advocate123` | Case Search, Citation Bookmarks, Judgment Export, Precedent Compare |
| **Legal Scholar** | `scholar@law.edu` | `scholar123` | Statutory Concordance, Landmark Summaries, Ratio Decidendi Analysis |
| **Citizen / Litigant** | `public@citizen.in` | `public123` | Public Case Status Lookup, Cause List Tracker, SHA-256 Verifier |

---

## 📂 Repository Structure

```
LexGuard-HTML/
├── frontend/                     # Pure HTML5 / Bootstrap 5 / jQuery Client
│   ├── index.html                # Madras High Court Portal & 10-Service Grid
│   ├── search.html               # Hybrid Precedent Search & Query Pills
│   ├── admin.html                # Staff Workstation & Chart.js Visualizations
│   ├── case-viewer.html          # PDF.js Reader, Text Layer, Keyword Stepper
│   ├── case-review.html          # Split-Screen CIS Human-in-the-Loop Review
│   ├── case-compare.html         # 3-Precedent Tray & BNSS Concordance
│   ├── draft-assistant.html      # AI Judgment Draft Assistant Studio
│   ├── acts-explorer.html        # Indian Statutory Directory & Concordance
│   ├── verify.html               # Web Crypto SHA-256 Tamper Verification
│   ├── cause-list.html           # Daily Cause List Court Board Tracker
│   ├── audit-ledger.html         # Merkle Tree Cryptographic Audit Ledger
│   ├── case-upload.html          # PDF Ingestion Desk
│   ├── bookmarks.html            # Saved Precedents
│   ├── 404.html                  # Judicial 404 Not Found Screen
│   ├── screenshots-gallery.html  # 31-Task Visual Execution Showcase
│   ├── css/                      # High Court Red & White CSS Engine
│   ├── js/                       # API Services, Nav Loader, Page Logic
│   ├── screenshots/              # 31 Visual Audit Execution Screenshots
│   └── favicon.svg               # High Court Crimson Shield
├── backend/                      # FastAPI Python Backend
│   ├── app/                      # Models, Endpoints, Services, Security
│   ├── storage/cases/            # Judgment PDF Corpus (208 Cases)
│   ├── requirements.txt          # Minimal Python Dependencies
│   └── .env.example              # Environment Configuration
├── database/                     # Database Assets
│   ├── lexguard_dump.sql         # Full PostgreSQL 17 Dump (208 cases, 989 logs)
│   └── seed_105_cases.py         # Python Seeder Script
├── scripts/                      # Utility Scripts
│   ├── capture_html_red_white.py # Headless Edge Visual Audit Script
│   └── find_404_errors.py        # Route Integrity Validator
├── start_windows.bat             # 1-Click Windows Launcher
├── start_linux.sh                # 1-Click Linux Launcher
├── index.html                    # Root Portal Redirect
├── LICENSE                       # MIT License
└── README.md                     # Documentation
```

---

## 🔒 Security & Cryptographic Integrity

* **Zero-Byte Client Hashing**: File digests are computed directly in the client browser using the W3C Web Cryptography API (`crypto.subtle.digest('SHA-256', buffer)`). Sensitive case documents are never sent over the network merely to compute checksums.
* **Merkle Chained Audit Ledger**: Every case modification, approval, and verification event calculates a SHA-256 leaf hash that links cryptographically to the prior block hash, rendering unauthorized database manipulation mathematically detectable.
* **OWASP Hardened Headers**: Every API response enforces `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, and strict Content Security Policies.

---

## 📜 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for full details.  
Maintained by **Vijayaraj** ([@Vijayaraj-IHT](https://github.com/Vijayaraj-IHT)).
