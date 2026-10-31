# LexGuard — Directory-by-Directory Optimisation Plan

**Baseline:** 1,117 tracked files · 299 MB working tree (99 MB `.git`) · 22.1 k Python lines · 5.8 k JS · 5.1 k HTML · 756 PDFs (596 unique) · 607 case rows · 45 API routes · no CI, no build step.

The plan is ordered by **impact ÷ effort**. Every item names the directory it touches and how you will know it worked.

---

## 0. Target layout

```
LexGuard/
├── backend/
│   ├── app/                      # unchanged shape: api · core · models · schemas · services
│   │   ├── api/v1/endpoints/
│   │   ├── core/                 # config, database, security, logging, cache
│   │   └── services/             # + search/ (ranking), llm/ (providers)
│   ├── migrations/               # single Alembic chain (replaces 5 ad-hoc scripts)
│   ├── tests/
│   │   ├── unit/  integration/  fixtures/   # no DB writes to a tracked .db
│   ├── requirements/             # base.txt · dev.txt · ml.txt (heavy models split out)
│   └── scripts/                  # ONLY operations used today (ingest, enrich, verify)
├── frontend/
│   ├── pages/                    # 20 html files
│   ├── assets/
│   │   ├── css/  js/core  js/components  js/pages
│   │   ├── img/ (optimised)      # no screenshots in shipping bundle
│   │   └── vendor/               # self-hosted pinned JS (optional)
│   └── index.html
├── data/
│   ├── manifest/cases.jsonl      # one row per case: path, sha256, source_url, retrieved_at
│   ├── fixtures/                 # 5-case dev subset (checked in)
│   └── README.md                 # how to fetch the full corpus
├── docs/                         # audit, redesign, diagrams, report sources
├── tools/                        # one-off/dev utilities, clearly non-production
├── scripts/                      # dev.sh · serve.py · fetch_corpus.py · check_assets.py
├── .github/workflows/ci.yml
└── README.md · LICENSE · PROVENANCE.md · THIRD_PARTY_NOTICES.md
```

Corpus PDFs (`storage/cases`, 124 MB) move **out of Git** to object storage / Git LFS / a release asset, with `data/manifest/cases.jsonl` as the reproducible index.

---

## 1. Repository & storage (`/`, `storage/`, `database/`, `backend/storage/`)

| Problem | Number | Technique |
|---|---|---|
| PDFs tracked in Git | 756 files / 124 MB | `git rm -r --cached storage/cases`; publish a `fetch_corpus.py` that downloads a versioned archive; keep 5 fixture PDFs in-repo |
| Duplicate PDFs | 160 extra copies / 25 MB | Deduplicate by SHA-256 at ingest (`file_hash` already exists); keep one canonical name per hash; add `UNIQUE(file_hash)` |
| Duplicate/generated artefacts | 3.2 MB Mermaid + 5.1 MB screenshots.zip + 20 MB docx archive + 11 MB staging PDFs | Delete (§ dead-code report); add `.gitignore` entries **before** adding files |
| Two dumps, one stale | `lexguard_dump.sql` has 145 cases, `database_dump.sql` 607 | Delete the stale one, generate dumps from a single script, name with date + row count |
| `.gitignore` does not protect anything already tracked | `backend/*.db`, `storage/` tracked | `git rm --cached` then rely on ignore; add a CI check `git ls-files | grep -E '\.(db|sqlite|pdf)$'` |
| `report_builder/` mixes source and output | 25 MB | Keep `build_report.py` + `diagrams/` under `docs/report/`; outputs to `dist/` (ignored) |

**Target:** working tree ≤ 60 MB, `.git` ≤ 20 MB, zero binary diffs in normal commits.

---

## 2. Backend runtime (`backend/app`)

### 2.1 Search path — biggest performance problem

Current flow (`api/v1/endpoints/search.py`):

```python
query_obj = db.query(Case).options(defer(Case.full_text)).filter(Case.status == "published")
candidates: List[Case] = query_obj.all()          # every published row → RAM
for c in candidates:
    ... c.full_text[:15000] ...                   # defeats defer(): 1 query per row
```

- **N+1 queries:** `defer(Case.full_text)` is undone by `c.full_text` in the scoring loop → ~606 extra SELECTs per search.
- **No DB-side ranking:** vector, lexical and statute scores are computed in Python.
- **No LIMIT before scoring**, so memory grows linearly with the corpus.

**Techniques**
1. Move retrieval to SQL:
   ```python
   # PostgreSQL + pgvector
   q = (db.query(Case, Case.embedding.cosine_distance(qvec).label("d"))
          .filter(Case.status == "published")
          .order_by("d").limit(100))
   ```
   Add `CREATE INDEX ON cases USING hnsw (embedding vector_cosine_ops);`
2. Full-text: `to_tsvector('english', title || ' ' || summary || ' ' || full_text)` with a GIN index; statute matching via `section_tags` GIN index.
3. RRF combine in SQL (`ROW_NUMBER()` over each rank list) or in a small service over top-100 candidates.
4. Only select the columns the card needs (`load_only`) and return top-N.
5. Cache: query-embedding LRU already exists; add a 60 s cache for `/cases/stats`, `/cases/landmarks`, `/statutes/acts`.

**Exit criteria:** p95 search < 300 ms at 5 k cases; ≤ 3 SQL round-trips per search.

### 2.2 Database

| Technique | Detail |
|---|---|
| Indexes | `(status, created_at DESC)`, `court`, `year`, `file_hash UNIQUE`, GIN on `act_tags`, `section_tags`, `keyword_tags` |
| Data sanity | fix 6 malformed JSON cells; 9 duplicate hashes; 2 dangling file paths; 475 missing embeddings |
| pgvector optionality | `models/case.py` falls back to JSON when pgvector is absent — good; document that SQLite mode = lexical-only |
| Sessions | `pool_size=10/max_overflow=20` is fine for a demo; add `pool_pre_ping` (present) and a `/health` that runs `SELECT 1` |
| Migrations | replace 5 `migrate_*.py` scripts with one Alembic baseline + versions |
| Seed | one idempotent `seed_corpus.py` (delete the 6 incremental seeders that share 130 duplicated statements) |

### 2.3 API layer

- Remove the duplicate `/users` mount of the auth router (halves auth operations in OpenAPI).
- Collapse duplicated case-filter blocks in `search.py` (35-line copy at 142–176 ↔ 250–284) into `apply_filters(query, filters)`.
- `response_model` everywhere + `exclude_unset` to cut payload size.
- Add `GZipMiddleware(minimum_size=1000)` — JSON responses and PDF metadata are text-heavy.
- Add `Cache-Control: no-store` on authenticated endpoints, `public, max-age=300` on `/statutes/acts`, `/cases/stats`.
- Rate limiting: keep the in-memory limiter for dev, use Redis (`slowapi` is already declared) for multi-worker runs; add global limits to search (search is currently unlimited).
- Health: return DB latency + model status; never hard-code `database_connected: True`.
- Long-running work (batch re-extract, ingestion of 1000 PDFs) → background task/queue instead of blocking the request.

### 2.4 Configuration & security

- Fail closed: no default `SECRET_KEY`, no default DB password; require them in all environments except explicit `ENVIRONMENT=test`.
- Remove silent SQLite fallback in production (`ALLOW_SQLITE_FALLBACK=false`).
- CORS: never combine `allow_origins=["*"]` with `allow_credentials=True`; drop the wildcard branch.
- Split `requirements.txt` into `base` / `ml` / `dev` so the API can start in ~2 s without torch (currently the install is >2 GB and unnecessary for search-only deployments).

---

## 3. Frontend (`frontend/`)

### 3.1 Delivery (no build step required)

| Technique | Current → Target |
|---|---|
| Self-host or SRI | 6 CDN references, 0 `integrity` attributes → add SRI hashes or vendor files under `assets/vendor/` (adds 2 files, removes a supply-chain dependency) |
| Defer/async | scripts are parser-blocking at the end of `<body>` → add `defer` and move to `<head>` (parallel download) |
| CSS splitting | 2 files × 20 pages, 33 KB raw / 7 KB gzip → keep global + per-page blocks; remove 188 `!important` |
| Fonts | 3 families × up to 6 weights from Google → subset to `wght@400;600;700`, `display=swap`, preconnect (already) and `font-display` fallback |
| Images | 40 PNG screenshots 5.7 MB (not shipped on app pages, but in repo) → WebP/AVIF for docs, lazy `loading="lazy"` in gallery |
| Caching | `python -m http.server` sends no cache headers → use the planned `serve.py` with `Cache-Control: public, max-age=31536000, immutable` for hashed assets and `no-cache` for HTML |
| Compression | none → gzip/brotli in `serve.py` or nginx (search page 47 KB → ~13 KB) |
| Page weight | `search.html` = 14 KB HTML + 33 KB CSS + 47 KB JS + Bootstrap/jQuery CDN (~90 KB gz) → target < 150 KB gz first load |

Measured local assets for the search page:

| File | Raw | Gzip |
|---|---:|---:|
| `search.html` | 14,127 | 3,630 |
| `lexguard.css` + `components.css` | 32,778 | 7,109 |
| core + auth + toast + api + nav + search JS | 50,953 | 14,404 |

### 3.2 Code structure

- Extract `assets/js/components/case-card.js` (see `SEARCH_CARD_REDESIGN.md`) and reuse it in search, bookmarks, compare tray.
- Replace the 5 identical `<script>` blocks per page with one `bootstrap.js` include list (or ES modules with `type="module"`).
- Remove the 14 dead `LG.*` members and 6 undefined classes; fix `badge-gold`/`fs-7`/`btn-xs`.
- Replace per-render `.on()` binding in `search.js` with delegated handlers (prevents handler churn on every keystroke).
- Escape server snippets client-side; never inject HTML from the API.
- Add `aria-live="polite"` on `#results-container`, `scope` on table headers, `aria-label` on icon buttons.
- Add a skeleton state (3 placeholder cards) instead of emptying the container.
- Keep the zero-build promise: optional `esbuild --minify` script for release only (`scripts/build_frontend.sh`), not a dev dependency.

### 3.3 Frontend config

- `API_BASE` hard-coded to `http://127.0.0.1:8000` (3 places) → resolve at runtime:
  ```js
  API_BASE: (document.querySelector('meta[name="lg-api-base"]')?.content)
            || (location.hostname === 'localhost' ? 'http://127.0.0.1:8000/api/v1' : '/api/v1')
  ```
  plus a `serve.py` proxy so the browser only talks to one origin (also fixes CORS in previews).
- Version asset URLs (`?v=20261101`) or content hashes — `case-viewer.html` already needed a cache-busting fix in history.

---

## 4. Data & corpus (`data/`, `storage/`)

| Problem | Number | Technique |
|---|---|---|
| Duplicate PDFs | 160 / 25 MB | SHA-256 dedupe on ingest; keep the first canonical path |
| Duplicate case rows | 9 | group by `file_hash`, merge, add unique index |
| Missing files | 2 case rows point nowhere | validate on startup or in CI |
| Missing text | 299 / 607 empty `full_text` | re-run extraction with `pdfplumber`, store per-page text |
| Missing embeddings | 475 / 607 | batch backfill using `batch_generate_embeddings()` (currently dead code — reuse it) |
| Provenance | `source_url` only 4 portal roots | store per-document URL + `retrieved_at` + licence/ToS note in `data/manifest/cases.jsonl` |
| Internal IDs shown as citations | 535 rows contain `LexGuard…` | split into `repository_id` (internal) and `official_citation` (only when verified) |
| Wrong years | 178 of 434 parseable rows | derive from `decision_date` or `case_no`, add constraint |
| Three numbers in UI | 130 / 208 / 607 | single `/cases/stats` call feeding every badge |

**Pipeline:** `fetch → hash → dedupe → extract (pdfplumber) → embed → validate → insert` as one idempotent command (`python -m app.cli ingest --dir ...`), replacing 20+ seed scripts.

---

## 5. Security & configuration (`backend/app/core`, deployment)

| Item | Change |
|---|---|
| Secrets | rotate and remove defaults; `.env.example` contains a real-looking JWT key and DB password — replace with placeholders |
| PII in Git | 29 users, 26 bcrypt hashes + 2 personal Gmail addresses in `lexguard.db` and the dumps → scrub, regenerate demo data, add secret-scan CI (`gitleaks`) |
| Headers/CSP | serve the frontend through the same app (or nginx) so CSP/HSTS apply to pages, not just API responses |
| CSRF | one implementation (middleware), remove the duplicate dependency |
| Cookies | `SameSite=Lax` is fine; set `Secure` in all non-dev environments (already enforced) |
| Rate limit | add to `/search` (expensive) and `/register` (already), store counters in Redis |
| Upload | validate magic bytes (not just extension), cap decompressed DOCX size, virus-scan hook for a real deployment |
| Logging | structured JSON logs + request IDs; never log tokens or query strings with PII |

---

## 6. Developer workflow (root, `.github/`)

| Gap | Add |
|---|---|
| No linting | `ruff` (lint+format), `mypy` on `app/core` + `app/services` |
| No CI | `.github/workflows/ci.yml`: Python 3.12 → `ruff`, `pyflakes`, `pytest`, `jscpd --threshold 8`, `compileall`, asset-reference check |
| No env reproducibility | `requirements/*.txt` with hashes (`pip-compile`), `node` not required except for optional tooling |
| No task runner | `Makefile`/`justfile`: `make dev`, `make test`, `make lint`, `make corpus`, `make dump` |
| No migrations discipline | Alembic baseline; one command `alembic upgrade head` |
| Docs drift | generate README metrics from `/cases/stats` at build time |
| No provenance | `PROVENANCE.md` (reuse from `Sem-5-Project`) + `THIRD_PARTY_NOTICES.md` |
| Local env portability | replace `e:/SEM 5 PROJECT/...` paths in 6 scripts with CLI args / `pathlib` |

---

## 7. Measurable targets

| Metric | Now | Target | How to verify |
|---|---:|---:|---|
| Working tree | 299 MB | ≤ 60 MB | `du -sh .` |
| Tracked binaries | 756 PDFs + 2 DB + zip | 5 fixtures | `git ls-files` filter |
| Search p95 | not measured (~600 N+1 queries) | < 300 ms | `pytest-benchmark` / `ab` |
| Duplicate code | 6.9 % (HTML 22 %) | < 3 % | `jscpd --threshold 3` |
| Dead Python symbols | 8 | 0 | `vulture --min-confidence 80` |
| Dead imports | 13 | 0 | `pyflakes` |
| Undefined CSS classes used | 20 | 0 | `check_assets.py` |
| First-load page weight | ~47 KB local + CDN | < 150 KB gz total | DevTools / Lighthouse |
| Tests on 3.11 | fail to collect | green on 3.11 + 3.12 | CI matrix |
| Corpus with embeddings | 22 % | 100 % | SQL count |
| Corpus duplicates | 160 files / 9 rows | 0 | SQL + hash scan |
| Secrets/PII in Git | 26 hashes + 2 emails | 0 | `gitleaks` |

---

## 8. Sequencing

**Day 1 — stop the bleeding**
1. Fix `bookmarks.py:247` (Python 3.12 syntax) → makes tests runnable.
2. Repair 6 malformed JSON rows.
3. `git rm` the zero-reference artefacts (Mermaid, screenshots.zip, archive, duplicate index/seed/dump).
4. Make `API_BASE` configurable + add `serve.py` (static + `/api` proxy + gzip + cache headers).

**Week 1 — structure**
5. Move PDFs out of Git; add `data/manifest/cases.jsonl` and `scripts/fetch_corpus.py`.
6. Deduplicate PDFs and case rows; add `UNIQUE(file_hash)`; backfill 475 embeddings.
7. Extract `case-card.js`; delete 14 dead JS members; add SRI or self-host CDN assets.
8. Add `ruff` + `pyflakes` + `pytest` + `jscpd` CI gate on Python 3.12.

**Week 2 — performance & correctness**
9. SQL-side search (pgvector + FTS + RRF), remove N+1, add indexes; benchmark.
10. Split requirements into base/ml; gzip middleware; caching headers; Redis rate limit.
11. Alembic baseline; one idempotent ingestion CLI; archive `tools/`.
12. Update README/report numbers from live stats; add `PROVENANCE.md`, `THIRD_PARTY_NOTICES.md`.

**Week 3 — product polish**
13. Search card redesign phases 2–4 (visual tokens, a11y, sort, "why matched").
14. Logo system roll-out (see `LOGO_DESIGN_BRIEF.md`).
15. Lighthouse/axe audit, load test at 5 k cases, final report regeneration.
