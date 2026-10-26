# Lexguard — Backend API Service

FastAPI-powered backend for **Lexguard: Legal Case Research & Document Verification System**.

## Features Implemented in Milestone 1:

1. **Role-Based Access Control (RBAC):**
   - 4 Scoped Roles: Court Staff / Senior Staff, Advocate, Legal Scholar, Public.
   - bcrypt password hashing with cost factor 12.
   - Stateless JWT authentication in **HttpOnly, Secure cookies** paired with a CSRF double-submit token pattern (defending against OWASP A07 and XSS token theft).

2. **Cryptographic Integrity & Chain of Custody:**
   - **Document SHA-256 Fingerprinting:** Real-time computation on upload and verification on view/download.
   - **Automatic Tamper Detection:** Immediate status quarantine and admin alerting if document bytes change on disk.
   - **Segmented Tamper-Evident Audit Log:** Every application event is appended only through `audit_service`, links `previous_log_hash` to `current_hash` via SHA-256, and receives a monotonic `seq`. `/api/v1/admin/verify-audit-chain` reports the active segment and archived segments separately. Senior staff may explicitly reseal with `/api/v1/admin/reseal-audit-chain`; historical rows are never rewritten.

3. **Hybrid Precedent Search & AI Draft Assistant:**
   - Query understanding and petition gap analysis using Anthropic Claude API with deterministic local mock fallback for 100% offline testing.
   - Strict citation grounding to prevent legal hallucination.

4. **Security Hardening (OWASP Top 10):**
   - HTTP security headers middleware (CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy).
   - UUID file renaming on upload (Path Traversal defense).
   - Parameterized SQLAlchemy queries.

---

## Directory Structure

```
backend/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── endpoints/
│   │       │   ├── auth.py
│   │       │   ├── cases.py
│   │       │   ├── search.py
│   │       │   ├── draft.py
│   │       │   └── admin.py
│   │       └── api.py
│   ├── core/
│   │   ├── config.py
│   │   ├── database.py
│   │   └── security.py
│   ├── models/
│   │   ├── user.py
│   │   ├── case.py
│   │   ├── document_version.py
│   │   ├── audit_log.py
│   │   ├── bookmark.py
│   │   ├── draft_session.py
│   │   └── approval_queue.py
│   ├── schemas/
│   │   ├── user.py
│   │   ├── case.py
│   │   ├── search.py
│   │   ├── draft.py
│   │   ├── audit.py
│   │   └── token.py
│   ├── services/
│   │   ├── crypto_service.py
│   │   ├── audit_service.py
│   │   └── claude_service.py
│   └── main.py
├── tests/
│   └── test_milestone1.py
├── requirements.txt
├── .env.example
└── README.md
```

---

## Running the Application

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

### 3. Run Development Server
```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
- Interactive Swagger UI: [http://127.0.0.1:8000/api/v1/docs](http://127.0.0.1:8000/api/v1/docs)
- Health Check: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

### 4. Phase-0 Migration for a Restored Legacy Dump
After restoring `database/database_dump.sql`, apply the idempotent schema/backfill migration, then have an active senior-staff operator perform the disclosed reseal:
```bash
python migrate_phase0.py
python ../scripts/reseal_audit_chain.py \
  --email staff@lexguard.gov.in \
  --reason "Phase-0 disclosed remediation of legacy audit segment" \
  --confirm
```
The restored 1,393-row legacy segment is known invalid (first broken link at replay index 31). The migration labels it segment 0, backfills `seq`, and converts audit user/case foreign keys to `ON DELETE RESTRICT`; it does not rewrite hashes. The reseal appends a genesis `CHAIN_RESEALED` event in a new segment.

### 5. Running the Test Suite
The suite is isolated by `tests/conftest.py`: it forces a fresh temporary SQLite database and storage directory, then resets and reseeds deterministic demo users/cases before each test.
```bash
pytest -q
```
