# LexGuard-HTML — Independent Project Audit & Code-Plagiarism Assessment

**Repository:** `Vijayaraj-IHT/LexGuard-HTML` · branch `arena/64b06a8b-lexguard-html` · commit `8d240fc` (2026-10-31)
**Audit date:** 31 October 2026 · **Auditor:** Arena agent (automated + manual source review)
**Scope:** whole repository — backend, frontend, database, corpus, scripts, reports, third-party assets
**Deliverable:** project overview + originality/plagiarism findings + defects + remediation plan

---

**Contents:** [Summary](#0-executive-summary) · [Method](#1-how-this-audit-was-performed) · [Project overview](#2-what-the-project-actually-is) · [Corpus](#3-corpus-and-data-provenance) · [Plagiarism audit](#4-plagiarism-and-originality-audit) · [Defects](#5-defects-found-during-the-analysis) · [Remediation](#6-prioritised-remediation-plan) · [Assessment](#7-overall-assessment) · [Reproduce](#9-reproducing-this-audit)

## 0. Executive summary

**What this is.** A full-stack, zero-build "judicial case repository and document-verification platform" for Indian High Courts (Madras HC branding), built as a Semester-5 mini project by two students at Mepco Schlenk Engineering College. It combines a FastAPI/SQLAlchemy backend, a pure HTML5/Bootstrap 5/jQuery front end (20 pages), a 607-case judgment corpus, a SHA-256 hash-chained audit ledger, RBAC, semantic + lexical search, and a precedent comparator.

**Is the code plagiarised?** *Not from third parties, as far as can be established.* Thirteen targeted GitHub code searches for distinctive strings, comments and identifiers returned no verbatim hits from other authors. One phrase overlap was found in an unrelated public repo with a **different implementation** — consistent with shared LLM phrasing, not copying.

**The real originality problem is self-duplication.** 158 files in this repo also exist in the author's earlier repo `Vijayaraj-IHT/Sem-5-Project`. **121 are byte-identical and 31 are ≥82 % similar — 97.1 % of the 42,799 overlapping lines.** The HTML application was first committed inside `Sem-5-Project` on 22 Oct 2026 and this repo was created on 23 Oct 2026 as a spin-off. That is fine for a private continuation, but it is a **duplicate-submission risk** if both repositories are presented as separate work, and it means most of the "new" repository is not new code.

**Also found (none of it is plagiarism, all of it matters):**
- The backend **cannot even import on Python 3.10/3.11** (an f-string backslash at `bookmarks.py:247` requires Python 3.12), contradicting the README's "Python 3.10+".
- **6 malformed JSON cells in the shipped database** make the search endpoint throw 500s (3 test failures reproduce this).
- The front end **hard-codes `http://127.0.0.1:8000`**, so it only works on the developer's own machine.
- **475 of 607 cases (78 %) have no embedding** and **299 (49 %) have no extracted full text**, so "semantic hybrid search" mostly degrades to keyword matching in the shipped data.
- A **4.2 MB SQLite database plus two SQL dumps are committed** with 26 bcrypt hashes and real personal Gmail addresses.
- Documentation is **stale by 3×**: README and the project report say 208 cases / 989 ledger blocks / 31 screenshots; reality is 607 / 1,626 / 40.

**Bottom line:** technically ambitious and demonstrably working, but the submission needs (a) an explicit statement of reuse from `Sem-5-Project`, (b) an AI-assistance disclosure, (c) third-party licence notices, and (d) the P0 bug fixes below before it can be called reproducible.

---

## 1. How this audit was performed

| Check | Method / tool | What it can prove | What it cannot prove |
|---|---|---|---|
| Duplicate code inside the repo | `jscpd` 4.3.0 (token-based clone detection, ≥50 tokens / ≥5 lines), plus a custom Python AST structural-normalisation pass | Copy-paste between files | Whether the copied code was originally written by someone else |
| Duplication against the author's other repos | Shallow clone of `Sem-5-Project` and `LEX-GUARD`, SHA-256 file comparison + `difflib` similarity per shared path | Reuse between the author's own projects | Intent |
| Similarity to public code | GitHub Code Search API (`search/code`), 13 quoted distinctive queries + control queries | Verbatim matches in indexed public repos | Non-indexed repos, private repos, books, papers, paid corpora, pre-2020 web pages. **This repo is not indexed by GitHub code search** (a search for its own secret string returns 0), so negative results are weak evidence. |
| Third-party / licence compliance | Manual review of vendored files, CDN references, `requirements.txt`, licence terms | Licence conflicts and missing notices | Legal advice |
| Runtime behaviour | `python -m compileall`, `pytest` on a copy with a minimal dependency set | Concrete, reproducible defects | Production-scale behaviour |
| Data integrity | SQLite queries against the committed DB (JSON validation, hash de-duplication, file presence) | Shipped-data defects | Intent behind the data |

**Not available in this environment:** Turnitin/iThenticate/Codequiry/MOSS, the institutional corpus, and access to non-GitHub web sources. Treat "no external match found" as *absence of evidence*, not proof of originality.

Reproduction commands are in [§9](#9-reproducing-this-audit). Raw evidence: [`docs/audit_evidence/`](docs/audit_evidence/).

---

## 2. What the project actually is

### 2.1 Purpose and intended users

A judicial research and verification portal. Four personas are seeded in the database and advertised on the login screen:

| Role | Demo account | Intended capability |
|---|---|---|
| Court staff / Chief Registrar | `staff@court.gov.in` / `staff123` | Ingestion, approval queue, analytics, audit ledger |
| Senior Advocate | `advocate@bar.in` / `advocate123` | Search, bookmarks/binders, memo export, precedent comparison |
| Legal Scholar | `scholar@law.edu` / `scholar123` | Statutory concordance, landmark summaries, ratio analysis |
| Citizen / Litigant | `public@citizen.in` / `public123` | Public case status, cause list, SHA-256 verification |

A fifth account (`staff@lexguard.gov.in` / `Admin@Lexguard2026`, role `senior_staff`) is created by the test suite.

### 2.2 Feature inventory — claimed vs implemented

| # | Feature (README claim) | Reality in code | Status |
|---|---|---|---|
| 1 | Case status / CNR lookup | `POST /search` with field prefixes (`cnr:`, `court:`, `year:`, `judge:`); CNR stored on cases | ✅ Real (but see search defect) |
| 2 | Precedent "hybrid" search (RRF of dense vectors + full-text) | 3 score components combined by RRF, but all candidates are loaded into Python and scored in a loop; 78 % of cases have no vector | ⚠️ Real algorithm, weak data, not scalable |
| 3 | Statutory acts & IPC→BNS concordance | 12 acts, but only **20 statute sections** in total; concordance maps a curated subset | ⚠️ Demo dataset, not a bare-act library |
| 4 | SHA-256 tamper verification | Client-side Web Crypto digest + `POST /verification/lookup` against published hashes | ✅ Real |
| 5 | Multi-precedent comparator | 3-layer heuristic comparator (statutory tests, ratio alignment, boilerplate suggestions) — keyword overlap, no LLM | ✅ Real (heuristic) |
| 6 | Staff CIS review workstation | Split-screen PDF + editable docket, approval queue endpoints | ✅ Real |
| 7 | AI judgment draft studio | Embedding-ranked precedent suggestions + gap flags; Claude optional; mock heuristics when no key | ⚠️ Works offline as heuristics |
| 8 | Daily cause list tracker | **Simulated** — halls/stages/statuses are generated in `cause-list.js` | ❌ Mock data |
| 9 | Cryptographic audit register | SHA-256 hash chain with `previous_log_hash`, thread mutex, chain verifier | ✅ Real (single-node) |
| 10 | Case ingestion desk | Upload (PDF/DOCX), hash, dedupe, 3-pass extraction, approval queue | ⚠️ DOCX accepted but extraction is PDF-only |

**Also present but under-advertised:** bookmarks/binders with Markdown memo export, citation network endpoint, keyword-in-document search, official-content pagination, re-extraction, analytics endpoints.

### 2.3 Tech stack (as built)

- **Backend:** Python 3.12-required (see P0-1), FastAPI 0.115+, SQLAlchemy 2.x, Pydantic v2, PyJWT (HS256), bcrypt (cost 12), pdfplumber, optional `sentence-transformers` / `transformers` / `torch`, optional Anthropic SDK, `slowapi` declared but unused (custom limiter used instead).
- **Frontend:** pure HTML5 + Bootstrap 5.3.3 + jQuery 3.7.1 + Bootstrap Icons + Chart.js 4.4 + PDF.js 3.11, all from CDNs; Web Crypto API; no build step.
- **Database:** PostgreSQL + pgvector intended (384-dim `Vector` column when the extension is importable), **automatic silent fallback to SQLite** (`backend/lexguard.db`) when PostgreSQL is unreachable — which is how the repo is actually shipped.
- **AI/NLP:** `sentence-transformers/all-MiniLM-L6-v2` embeddings, `law-ai/InLegalBERT` NER, optional `Qwen/Qwen2.5-3B-Instruct` local LLM, optional Claude 3.5 Sonnet. All have deterministic/mock fallbacks.

### 2.4 Architecture

```
Browser (20 static HTML pages, no build)
  │  jQuery + fetch → http://127.0.0.1:8000/api/v1   ← hard-coded
  ▼
FastAPI app (uvicorn :8000)
  ├── SecurityHeadersMiddleware · CSRFValidationMiddleware · CORS
  ├── /auth (+ /users alias)  /cases  /search  /draft  /statutes
  │   /verification  /comparison  /admin  /bookmarks
  ├── Services: crypto · audit · extraction · embedding · NER
  │             text_sanitizer · comparator · comparison · claude · local_llm · ai_api
  └── SQLAlchemy ORM ──► PostgreSQL + pgvector
                     └─(connection failure)─► SQLite lexguard.db
Corpus: storage/cases/*.pdf (124 MB) + audit chain (1,626 rows)
```

### 2.5 Repository anatomy

| Path | Contents | Size | Notes |
|---|---|---|---|
| `backend/app` | 9 routers, 12 services, 8 models, 9 schemas, core | ~6.5k lines | Real application code |
| `backend/tests` | 13 test modules, 49 test functions | ~1.9k lines | Partly DB-fixture driven |
| `backend/*.py` (root) | ingest/seed/migrate one-offs | ~4k lines | Includes 1000-case batch ingester |
| `frontend/` | 20 HTML pages, 20 JS modules, 2 CSS files | 12 MB | 40 screenshots incl. 16 stale `react_*` |
| `database/` | `lexguard_dump.sql` (2.1 MB), `database_dump.sql` (3.7 MB), duplicate seeder | 5.8 MB | Committed bcrypt hashes + PII |
| `storage/cases/` | 756 PDFs | 124 MB | Only 596 unique |
| `scripts/` | 39 one-off patch/seed/scrub scripts | 1.4 MB | 11 hard-code `e:/SEM 5 PROJECT/...` paths |
| `report_builder/` | Python-docx report generator, 11 archived `.docx`, UML/PPT assets | 25 MB | Academic report generator |
| root | `index.html` (byte-identical to `frontend/index.html`), 3.2 MB `mermaid.min.js` (unused), launchers | 3.3 MB | README calls the root file a "redirect" — it is not |

**Volume:** 1,117 tracked files · 299 MB working tree (99 MB `.git`) · Python 22,136 lines · JS 5,801 · HTML 5,124 · CSS 1,325 · SQL 5,034.

### 2.6 Data model (8 tables)

| Table | Purpose | Key columns |
|---|---|---|
| `users` | Identity + RBAC | `email`, `password_hash` (bcrypt-12), `role`, `status`, `credential_id` |
| `cases` | Judgment registry | 47 columns: `cnr_number`, `case_no`, court/bench/judge, `summary`, `ratio_decidendi`, `statutory_tests`, `full_text`, `file_hash`, `embedding` (vector 384), `status` |
| `document_versions` | Immutable file versions | `case_id`, version number, hash |
| `audit_logs` | Hash-chained ledger | `previous_log_hash`, `current_hash`, action, ip, user-agent |
| `bookmarks` | Research binders | `case_id`, `binder_name`, notes |
| `draft_sessions` | Draft studio persistence | petition text, analysis JSON |
| `approval_queue` | Two-tier review workflow | submitted_by, status |
| `statute_sections` | Acts & sections | `act_code`, `section_no`, text |

### 2.7 API surface

**45 unique routes** in 9 routers (`/auth` is also mounted as `/users`, so 49 mounted operations):

- **auth (4):** login, register, logout, me
- **cases (12):** upload, upload-auto, list, stats, landmarks, get, patch, re-extract, view, verify-integrity, download/pdf, official-content, search-keywords, citations, external-references
- **search (1):** hybrid search
- **draft (4):** analyze, sessions (GET/POST), compare-with-precedent
- **statutes (3):** acts, index, section lookup
- **verification (3):** lookup (POST/GET path), document stream
- **comparison (3):** precedents, compare, compare-multi
- **admin (5):** queue, approve, audit-logs, verify-audit-chain, analytics
- **bookmarks (5):** list, create, update, delete, binders, export-memo

### 2.8 Front end (20 pages)

Portal (`index`), search, acts explorer, verify, case-viewer (PDF.js with text layer + keyword stepper), case-review, case-compare, draft-assistant, admin, cause-list, audit-ledger, case-upload, bookmarks, login/register/forgot/reset, 404, unauthorized, screenshots gallery.

Shared shell in `lexguard-nav.js` (2 `innerHTML` injections), API layer in `lexguard-api.js` (455 lines), 125 `escapeHtml` call sites — XSS discipline is better than average for hand-written jQuery.

---

## 3. Corpus and data provenance

| Metric | Value | Comment |
|---|---|---|
| Cases in DB | **607** (606 published, 1 pending_review) | README and report say 208 |
| Distinct `file_hash` in DB | 598 | **9 duplicate case records** |
| PDFs on disk | 756 | **160 redundant copies** (596 unique hashes) |
| Case hashes missing on disk | 2 | Broken document links |
| Cases with `full_text` | 308 (49 % empty) | Limits keyword snippets and extraction quality |
| Cases with embeddings | 132 (**78 % null**) | "Semantic" search largely lexical in shipped data |
| `source_url` populated | 410 | Only 4 distinct portal-level URLs (327 `services.ecourts.gov.in`, 78 `mhc.tn.gov.in/judis`, 4 `judgments.ecourts.gov.in`, 1 `www.mhc.tn.gov.in/judis`) — no per-document links |
| `source_verification_state` | 410 verified, 30 verified_authentic, 167 unverified | "Verified" here means a flag, not a citation check |
| Audit ledger rows | 1,626 | Report says 989 |
| Statute sections | 20 | 12 acts, demo subset |

**Provenance note.** `backend/seed_corpus/manifest.json` records that the seed PDFs came from a Google Drive folder and `mhc.tn.gov.in/judis`; six files still carry the browser-default name *"Home | Judgements and Orders…pdf"*. Indian court judgments themselves are generally not copyrightable government works, but **third-party headnotes/citations (SCC, AIR) are**, and bulk-downloading from a portal may breach its terms of use. Attribute each PDF to its source URL and keep the manifest.

---

## 4. Plagiarism and originality audit

### 4.1 Evidence 1 — similarity to public code (external)

Thirteen quoted-phrase queries were run against GitHub Code Search. Control tests confirmed the API was working (a query against `fastapi/full-stack-fastapi-template` returned a hit).

| # | Distinctive query (verbatim) | Hits | Result |
|---|---|---|---|
| 1 | `"lexguard-super-secret-jwt-key-2026-production-ready-32-chars-min"` | 0 | Unique |
| 2 | `"3-Layer Precision Precedent Comparator"` | 0 | Unique |
| 3 | `"Global mutex to prevent in-process thread-level race conditions"` | 0 | Unique |
| 4 | `"Transforms statutory section references into interactive clickable links"` | 0 | Unique |
| 5 | `"Statutory Cross-Reference Mapping between Pre-2024 Acts"` | 0 | Unique |
| 6 | `"Public accounts are active immediately; advocates and scholars start pending verification"` | 0 | Unique |
| 7 | `"Semantically related legal queries (bail/IPC) should have higher similarity"` | 0 | Unique |
| 8 | `"BAR-DL-2024-9912"` (seed credential ID) | 0 | Unique |
| 9 | `"class PrecedentComparatorService"` | 0 | Unique |
| 10 | `"compute_audit_log_hash" "verify_audit_chain"` | 1 (unrelated SQL migration) | Coincidental identifier overlap |
| 11 | `"previous_log_hash" "current_hash" "GENESIS_HASH"` | 4 (different projects, different code) | Generic hash-chain vocabulary |
| 12 | `"Deterministic normalized 384-dim pseudo-vector"` | **1 — `rimaypatil/ObserveAI::backend/embeddings/generator.py`** | **Phrase overlap, implementation differs** |
| 13 | `"InLegalBERT" "STATUTORY" "BNSS"` | 66 (READMEs of unrelated legal-AI projects) | Domain vocabulary, not code |

**The one hit, examined:** ObserveAI's `EmbeddingGenerator` uses NumPy `RandomState(seed).normal(...)` for its fallback vector; LexGuard's `EmbeddingService` uses MD5/SHA-256 feature hashing over tokens. The shared fragment is the comment `# Deterministic normalized 384-dim pseudo-vector`, plus the generic structure "lazy-load SentenceTransformer → catch exception → deterministic fallback". This is a **common LLM-generated idiom**, not a copy: no shared identifier, no shared line of logic, and the surrounding code differs throughout.

**Verdict on external copying:** no evidence of verbatim reuse from other public repositories. Confidence: **moderate**, because GitHub's index does not cover this repo, code in books/papers/private repos, or the pre-2020 web.

**What *is* recognisably non-original, and legitimately so:** the JWT/bcrypt/`HTTPBearer` pattern in `core/security.py`, the double-submit CSRF pattern, the sliding-window rate limiter, and the SHA-256 hash-chain construction are all canonical tutorial-grade patterns. They are not attributed because they are ideas/idioms, not copied expression — but the report should cite FastAPI, OWASP and NIST (it already cites the latter two).

### 4.2 Evidence 2 — duplication with the author's earlier repositories (the headline finding)

| Comparison | Result |
|---|---|
| `LexGuard-HTML` ↔ `Vijayaraj-IHT/Sem-5-Project` | **158 files overlap; 121 byte-identical (28,912 lines); 31 ≥82 % similar (12,633 lines) → 97.1 % of 42,799 overlapping lines** |
| Same-path subset only | 119 files / 31,455 lines → 94 identical (22,040 lines, 70.1 %) + 19 near-identical (25.9 %) = **96.0 %** |
| Python specifically | 15,562 lines byte-identical (≈58 % of all Python in the repo) |
| Front end ↔ `Sem-5-Project/lexguard-html/` | 41 shared files; **29 byte-identical** (7,291 lines); 12 more at 0.87–1.00 similarity |
| `LexGuard-HTML` ↔ `Vijayaraj-IHT/LEX-GUARD` (Aug 2026 prototype) | 0 identical files — genuinely different architecture |

**Timeline (from GitHub commit metadata):**

| Date (UTC) | Event |
|---|---|
| 2026-10-11 | `Sem-5-Project` created |
| 2026-10-22 20:02 | *"implement full LexGuard HTML5 multi-page application (11 pages…)"* committed **inside `Sem-5-Project`** |
| 2026-10-23 17:56 | judicial red/white redesign in `Sem-5-Project` |
| 2026-10-23 18:00 | `LexGuard-HTML` repository created |
| 2026-10-24 → 10-31 | Both repos continue in lock-step (e.g. identical commit messages on 24 Oct) |
| 2026-10-31 | This repo reaches 607 cases |

**Interpretation.** Both repos belong to the same author/team and describe the same project; the HTML app was developed first inside `Sem-5-Project` and then split out. This is **self-reuse, not plagiarism of a third party**. It is nevertheless the single biggest academic-integrity exposure:
1. If both repos are submitted (or one is submitted and the other is discoverable), this looks like **duplicate submission / self-plagiarism** unless declared.
2. 96 % overlap means claims of "new work" in this repository are not supportable; the genuinely new material is the corpus expansion (278 → 607 cases), renames, diagrams and report builder.
3. The repo carries a **single squashed commit locally** (`8d240fc`), which erases in-repo provenance; the GitHub history is the only evidence trail. Keep it public or export the log.

**Recommendation:** add a `PROVENANCE.md` stating that the backend and HTML client originate in `Sem-5-Project` (commit links), list what is new here, and get supervisor sign-off.

### 4.3 Evidence 3 — duplication inside this repository

`jscpd` over 217 files / 38,554 lines:

| Format | Files | Lines | Clones | Duplicated lines |
|---|---|---|---|---|
| Python | 105 | 21,061 | 35 | 911 (4.33 %) |
| JavaScript | 41 | 6,339 | 12 | 179 (2.82 %) |
| CSS | 23 | 4,062 | 3 | 278 (6.84 %) |
| HTML | 22 | 5,423 | 68 | **1,209 (22.29 %)** |
| Bash | 19 | 987 | 5 | 97 (9.83 %) |
| **Total** | **217** | **38,554** | **123** | **2,674 (6.94 %)** |

**Hot spots**

| Lines | Tokens | Location A | Location B | Diagnosis |
|---|---|---|---|---|
| 386 | 4,525 | `index.html` (root) 1-386 | `frontend/verify.html` 1-78 | Shared HTML `<head>`/CSS/JS shell. jscpd reports a long span because inline CSS/JS tokens align, although the two pages are otherwise unrelated (difflib ratio 0.09) |
| 179 | 1,059 | `backend/seed_105_cases.py` | `database/seed_105_cases.py` | Byte-identical duplicate file |
| 161 | 1,886 | `index.html` 20-180 | `frontend/index.html` 20-180 | **Byte-identical files** — the root `index.html` is a full copy of the portal, not the redirect the README describes |
| 141 + 107 | 2,500 | `scripts/seed_35_more_cases_to_reach_200.py` | `scripts/seed_final_20_cases_to_reach_200.py` | Two 500-line seeders sharing `generate_case_pdf()` and `main()` |
| 87 | 1,190 | `frontend/login.html` | `frontend/register.html` | Shared auth card markup |
| 60 | 539 | `scripts/seed_55_landmark_and_hc_cases.py` | `scripts/seed_final_20_cases…` | Third copy of the same seeder |
| 52 | 399 | `frontend/404.html` | `frontend/verify.html` | Shared shell |
| 48 | 399 | `frontend/index.html` | `frontend/unauthorized.html` | Shared footer/shell |
| 43 | 436 | `scripts/batch_ingest_judgments.py` | `scripts/rename_case_pdfs.py` | Duplicated `get_court_code()` |
| 35 | 459 | `search.py` 250-284 | `search.py` 142-176 | **Copy-paste inside one function's filter block** |

An independent AST pass (structural normalisation, names/constants removed) found **5 groups of functions with identical statement structure**, the largest being `generate_case_pdf()` (130 statements) duplicated across two seed scripts and `get_court_code()` (23 statements) across two ingest scripts.

**Assessment:** ~7 % internal duplication is normal for a student project, but the HTML shell duplication (22 %) and the three near-identical seeders are avoidable and make maintenance error-prone. Fix by extracting `layout.js`/`seed_common.py`.

### 4.4 Evidence 4 — third-party assets and licence compliance

| Asset | Licence | Handling in repo | Verdict |
|---|---|---|---|
| `mermaid.min.js` (3.2 MB, unversioned minified build) | MIT | **Vendored at root, no copyright/permission notice, and never referenced by any page** | ⚠️ Fails MIT's "include the notice" condition *and* is dead weight |
| Bootstrap 5.3.3 (CSS/JS), Bootstrap Icons, jQuery 3.7.1, Chart.js 4.4.1, PDF.js 3.11.174 | MIT / MIT / MIT / MIT / Apache-2.0 | CDN `<script src>` with **no `integrity` (SRI) attribute** | ⚠️ Not plagiarism; supply-chain risk. Also mixed versions (5.3.0 and 5.3.3) across pages |
| Google Fonts (Inter, Playfair Display, JetBrains Mono) | OFL-1.1 | CDN | ✅ OK, but the backend CSP `font-src 'self' data:` would block them on API-served pages |
| PyMuPDF (`pymupdf`) | **AGPL-3.0** (or commercial) | Declared in `requirements.txt` but **never imported**; extraction uses `pdfplumber` (MIT) | ⚠️ Declaring AGPL in an MIT project is a needless licence conflict; remove it |
| python-docx, numpy, torch, transformers, sentence-transformers, anthropic, psycopg2-binary | MIT / BSD / BSD / Apache-2.0 / Apache-2.0 / MIT / LGPL-with-exception | Normal dependency use | ✅ OK |

There is **no `NOTICE`, `THIRD_PARTY_NOTICES.md`, or licence header in any first-party file**. For an MIT-licensed repository that is acceptable for your own code, but the vendored bundle and AGPL entry need action.

### 4.5 Evidence 5 — AI-generated code indicators

This is an inference section, not a finding of misconduct. Signals:

| Signal | Observation |
|---|---|
| Uniform documentation | Near-every function carries a multi-line Google-style docstring with the same cadence, in 22k lines written within ~3 weeks |
| Branded commentary | Comments such as *"OWASP A02:2025 Defense"*, *"Double-Submit Cookie CSRF Defense"*, *"Global mutex to prevent in-process thread-level race conditions"* |
| Section-numbered inline comments | `# 1. Pass 1 …`, `# 2. Pass 2 …` repeated across services |
| Marketing register in code/docs | "enterprise-grade", "zero-build", "zero-trust", "anti-hallucination" throughout README and the academic report |
| Hard-coded personal environment | 6 scripts contain 11 hard-coded `e:/SEM 5 PROJECT/...` paths; 39 one-off `update_*.py`/`scrub_*.py` scripts that string-replace HTML |
| Emoji-rich artefacts | Emojis and badge walls in README; uniform report prose with US-spelling and em dashes |
| Over-claiming | "100 % zero hallucination rate", "average 1.14 seconds" with no benchmark harness in the repo |

**Implication:** the code is very likely LLM-assisted to a substantial degree. That is *not plagiarism*, but most institutions require an **AI-use declaration** and many require that AI-assisted code be understood and defensible in a viva. Add a short statement ("AI assistants were used for scaffolding, docstrings and refactoring; all code was reviewed and is understood by the authors") and be ready to explain `crypto_service.py`, `audit_service.py` and `search.py` line by line.

### 4.6 Originality risk matrix

| Dimension | Finding | Risk | Action |
|---|---|---|---|
| Third-party code copying | No verbatim matches found; one generic phrase overlap with an unrelated repo | 🟢 Low | Keep the audit note; optional: replace the shared phrase |
| Reuse of own earlier repo | 121 identical + 31 near-identical files (97 % of overlapping lines) | 🔴 High (duplicate submission) | `PROVENANCE.md` + supervisor disclosure |
| Internal copy-paste | 6.94 % duplicated lines; 22 % of HTML | 🟡 Moderate | Extract shared layout/seed helpers |
| Licence / attribution | Unused Mermaid bundle without notice; AGPL dependency declared; no SRI | 🟡 Moderate | Add notices, drop PyMuPDF, add SRI or self-host |
| AI-generated content | Strong indicators | 🟡 Moderate (policy, not plagiarism) | AI-use disclosure; viva preparation |
| Data/corpus provenance | 410 generic source URLs, 167 unverified, 160 duplicate PDFs | 🟡 Moderate | Per-document source URLs, dedupe, manifest |
| Report text | Has 7 references; no plagiarism/AI statement | 🟡 Moderate | Run institutional similarity check on the .docx |

---

## 5. Defects found during the analysis

### 5.1 P0 — blocks execution or correctness

1. **The backend does not import on Python 3.10/3.11.**
   `backend/app/api/v1/endpoints/bookmarks.py:247`
   ```python
   f"- **Bench:** {c.judge or 'Hon\'ble Bench'}"
   ```
   A backslash inside an f-string expression is only legal from Python 3.12 (PEP 701). `python -m compileall` fails; all six test modules that import `app.main` error at collection. Fix: `bench = c.judge or "Hon'ble Bench"` then `f"- **Bench:** {bench}"`.
   The README claims Python 3.10+, and the report describes the stack as Python 3.11+.

2. **Six malformed JSON cells in the shipped `backend/lexguard.db`** break search with an unhandled 500:
   - `comparison_profile` — cases `0b8c4db5`, `759908c8`, `45674d77`, `52dd984d`, `5c2b7bf1`
   - `issues_framed` — case `326f70b2`
   Cause: literal `\` escapes written into JSON text. `query_obj.all()` hydrates these rows and SQLAlchemy's JSON deserialiser raises `JSONDecodeError`. Reproduced as 3 test failures. Fix: sanitise with `json.dumps` at write time, validate with a DB check, migrate the 6 rows.

3. **Front end cannot talk to any backend but the developer's laptop.**
   `frontend/js/lexguard-core.js:13` → `API_BASE: 'http://127.0.0.1:8000/api/v1'`, duplicated as a literal fallback in `acts-explorer.js:43,178`. Any deployment (or sandboxed preview) fails. Fix: resolve from `window.location` / a `<meta>` config, and proxy `/api` in dev.

### 5.2 P1 — functional and security weaknesses

| Area | Finding |
|---|---|
| Search performance | `defer(Case.full_text)` is immediately defeated by `c.full_text` inside the scoring loop → one lazy query per case (~606 N+1 queries); all published cases are pulled into RAM per search |
| AI/search honesty | 475/607 cases have no embedding; the fallback "deterministic vector" is MD5 feature hashing, not semantics — results will be lexical even when "semantic" is claimed |
| DOCX support | `.docx` is accepted by upload but extraction/streaming path is pdfplumber-only; DOCX uploads will fail downstream |
| Secret defaults | `SECRET_KEY` and `CSRF_SECRET` ship with usable defaults in `core/config.py` and `.env.example`; production guard only covers the JWT key and only when `ENVIRONMENT != development` |
| CORS | `allow_origins=["*"]` fallback combined with `allow_credentials=True` is invalid per the CORS spec (browsers reject it); the list path is fine but the fallback is a trap |
| Rate limiting | In-memory per-process dict with no eviction; applied only to register (10/min), login (15/min) and verification lookups (60/min); ineffective behind multiple workers |
| Health check | `/health` always reports `"database_connected": True` without touching the DB |
| Silent DB fallback | PostgreSQL failure silently switches to SQLite; in production this means writes go to a local file and disappear |
| Data leakage | Committed `backend/lexguard.db` + two SQL dumps contain 26 bcrypt hashes (crackable demo passwords) and real Gmail addresses; demo credentials are printed on the login page |
| Headers/CSP | Security headers are applied only to API responses, not to the static front end; CSP allows `'unsafe-inline'` and would block the Google Fonts/CDN assets it ships with |
| CSRF coverage | Middleware and dependency duplicate the same check; cookie-only auth means Bearer-token API clients bypass CSRF entirely (acceptable, but document it) |

**Strengths worth crediting:** bcrypt cost 12; JWT with `iat`/`exp`; HttpOnly + SameSite cookies; constant-time hash comparison (`hmac.compare_digest`); upload size/extension validation; canonical filename generation defeating path traversal; duplicate detection by SHA-256; published-only visibility on verification and search; 125 `escapeHtml` call sites in the front end; audit logging on privileged actions; RBAC with staff-role expansion.

### 5.3 Test suite reality check

Run on a copy of `backend/` with only the light dependencies installed (FastAPI, SQLAlchemy, PyJWT, bcrypt, httpx, pytest, pgvector), after applying the P0-1 one-line fix:

```
37 passed, 5 failed, 7 skipped in ~5 s
```

- 2 failures — `pdfplumber` not installed in this sandbox (environment, not a code bug)
- 3 failures — the malformed-JSON DB cells (real bug, P0-2)

Without the one-line fix, **6 of 13 test modules fail at collection** (25 of 49 tests never run) on Python 3.11.

### 5.4 Documentation drift

| Claim (README / report) | Reality |
|---|---|
| 208 cases / 989 ledger blocks | 607 cases / 1,626 audit rows |
| 31 screenshots | 40 files (16 stale `react_*` images from the abandoned React client) |
| Python 3.10 / 3.11 / 3.12 | Requires 3.12 (f-string syntax) |
| "Root Portal Redirect" (`index.html`) | Byte-identical 386-line copy of `frontend/index.html` |
| PostgreSQL 17 persistence tier | Ships as SQLite; silently falls back |
| "PyMuPDF extraction" (report) | Code uses `pdfplumber` |
| "Live cause list" | Randomly generated demo board |
| "208 cases" / "130" / "607" | Three different numbers appear across README, UI badges and DB |
| "100 % zero hallucination", "1.14 s average" | No benchmark or harness in the repo |

### 5.5 Repository hygiene

- 299 MB working tree; 124 MB of PDFs and a 4.2 MB DB tracked in Git; GitHub reports 100 MB.
- `backend/storage/` and `*.db` are in `.gitignore` **but still tracked** (added before the rule).
- 11 archived copies of the same report `.docx` (20 MB) in `report_builder/archive/`.
- 160 duplicate PDFs; 9 duplicate case records; 2 dangling file references.
- 39 one-off scripts (6 of them with hard-coded `e:/SEM 5 PROJECT/...` paths); no `Makefile`, no CI, no `Dockerfile`, no linter config.
- Single squashed local commit; useful history exists only on GitHub.

---

## 6. Prioritised remediation plan

**Before submission (same day)**

1. Fix `bookmarks.py:247` and add a Python-version marker (`requires-python = ">=3.12"` or make it 3.11-compatible).
2. Repair the 6 malformed JSON rows; add a `json.dumps` guard in extraction/seed paths.
3. Add `PROVENANCE.md` (reuse from `Sem-5-Project` + commit links + what is new) and an AI-use statement.
4. Add `THIRD_PARTY_NOTICES.md` (Mermaid MIT text, Bootstrap/jQuery/Chart.js/PDF.js/Google Fonts), delete the unused `mermaid.min.js`, remove `pymupdf` from `requirements.txt`.
5. Stop shipping the DB/dumps with real emails and hashes: scrub users, keep only demo accounts, rotate anything reused.

**Within a week**

6. Make `API_BASE` environment-resolved; add a tiny `serve.py` that serves `frontend/` and proxies `/api`.
7. Update all stale numbers (README, UI badges, report) from a single stats endpoint.
8. Fix the search N+1 (`selectinload` or vector search in SQL), and either compute the 475 missing embeddings or label the feature "lexical fallback".
9. Deduplicate the 160 PDFs and 9 case rows; rebuild the corpus manifest with per-document source URLs.
10. Extract `layout`/`seed_common` helpers to kill the 22 % HTML duplication and the triple seeder.

**Before any public/real deployment**

11. Redis-backed rate limiting, forced secret provisioning, Postgres-only mode (no silent fallback), `/health` that actually pings the DB.
12. Per-page CSP without `unsafe-inline`; SRI on every CDN asset or self-host them.
13. Add CI: `ruff` + `pytest` on 3.12, `jscpd --threshold 5`, link check, secret scan.
14. Delete `react_*` screenshots, `screenshots.zip`, `report_builder/archive/`, and move large corpora to external storage or Git LFS.

---

## 7. Overall assessment

| Dimension | Verdict |
|---|---|
| Ambition / scope | Strong: 45 endpoints, 8 tables, 20 pages, 607-case corpus, real cryptography and RBAC |
| Engineering quality | Mixed: clean service separation and good XSS/session hygiene, undermined by copy-paste, N+1 queries, dead code and one-off patch scripts |
| Reproducibility | **Weak today** — Python 3.12 dependency undocumented, hard-coded localhost, corrupt DB rows, silent SQLite fallback; fixable in a day |
| Security posture | Reasonable for a prototype; secrets and PII in Git are the main problems |
| Documentation accuracy | Weak — numbers stale by 3× and several architectural claims do not match the code |
| **Originality (external)** | **No third-party plagiarism detected** (moderate confidence) |
| **Originality (internal)** | **Poor** — 97 % overlap with the author's earlier repo; needs disclosure, not concealment |
| Academic readiness | Conditionally ready: fix P0s, declare reuse + AI assistance, add licence notices, rerun similarity check in Turnitin/Codequiry |

**One-sentence verdict:** LexGuard is a genuine, working, unusually broad student project whose code shows no sign of having been copied from strangers — but it is largely the same code as the author's previous repository, was probably written with heavy AI assistance, and currently does not run on the Python version it advertises.

---

## 8. Files produced by this audit

| File | Contents |
|---|---|
| `PROJECT_AUDIT.md` | This report |
| `docs/audit_evidence/cross_repo_duplication.csv` | 158 rows: LexGuard file ↔ Sem-5-Project file, line count, identical/near/divergent, similarity ratio |
| `docs/audit_evidence/internal_clones.csv` | 123 `jscpd` clone pairs with file ranges, lines and tokens |

## 9. Reproducing this audit

```bash
# 1. Syntax check (expect failure on Python 3.11)
python3 -m compileall -q backend

# 2. Clone detector
npm install --prefix /tmp/plagcheck jscpd@4
/tmp/plagcheck/node_modules/.bin/jscpd . --min-tokens 50 --min-lines 5 \
  --ignore "**/*.min.js,**/*.pdf,**/storage/**,**/incoming_cases/**,**/seed_corpus/pdfs/**,**/report_builder/**,**/*.json,**/*.sql" \
  --reporters console,json --output /tmp/jscpd-out

# 3. Cross-repository comparison
git clone --depth 1 https://github.com/Vijayaraj-IHT/Sem-5-Project.git /tmp/sem5
# then run the SHA-256 + difflib comparison (see docs/audit_evidence/*.csv)

# 4. Test suite (on a copy, light deps only)
python3 -m venv /tmp/venv-lg && /tmp/venv-lg/bin/pip install fastapi sqlalchemy pydantic \
  pydantic-settings pyjwt bcrypt httpx pytest python-multipart email-validator pgvector
cp -r backend /tmp/testrun && cd /tmp/testrun
# apply the P0-1 one-line fix first, otherwise collection fails on Python < 3.12
/tmp/venv-lg/bin/python -m pytest tests -q

# 5. Database integrity
sqlite3 backend/lexguard.db "select status,count(*) from cases group by 1;"

# 6. GitHub similarity probes
gh api -X GET search/code -f q='"<distinctive phrase>"' --jq '.total_count'
```

---

*Prepared on 2026-10-31 against commit `8d240fc`. Automated similarity tools are advisory; for an official submission use your institution's licensed plagiarism service (Turnitin/iThenticate/Codequiry) as well.*
