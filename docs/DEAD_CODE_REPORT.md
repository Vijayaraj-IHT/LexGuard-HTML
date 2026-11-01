# LexGuard — Dead Code & Unused Asset Report

**Generated:** 31 Oct 2026 · commit `8d240fc` · branch `arena/64b06a8b-lexguard-html`
**Question answered:** *what is unnecessary, what was it probably there for, and what should happen to it?*

---

## 1. Method

| Check | Tool | Threshold |
|---|---|---|
| Unused Python functions/classes/vars | `vulture` on a syntax-fixed copy (the repo does not parse on 3.11) + custom AST pass that excludes FastAPI route handlers | name referenced ≤ 1 time repo-wide |
| Unused imports | `pyflakes` | default |
| Unused settings | parse `core/config.py` × `settings.*` usages | zero reads outside config |
| Unused frontend API wrappers / utils | Acorn AST scan of `LG.*` members × usage in all JS + HTML | zero call sites |
| Unused CSS | selector extraction vs `class="…"` in HTML + JS literals | custom-prefix selectors only |
| Unused files & assets | reference scan (HTML/JS/CSS/Python) + SHA-256 duplicate detection | unreferenced or byte-identical copy |
| Unused DB columns/tables | model AST × ORM usage | no reads/writes outside `models/` |
| Dead routes / broken flows | route table × client call map | no caller |
| Stale data artefacts | SQLite queries + dump parsing | — |

**Caveat:** route handlers, Pydantic models and SQLAlchemy columns are *framework-referenced* and are deliberately excluded from "dead function" counts; only things with genuinely no runtime path are listed.

---

## 2. Summary

| Category | Items | Volume | Verdict |
|---|---:|---:|---|
| Duplicate files | 5 groups | ~7 MB + 565 lines | Delete one copy each |
| Unused vendored asset | 1 | 3.2 MB | Delete |
| Stale / duplicate exports | 4 groups | ~37 MB | Delete or move out of Git |
| Unreferenced images | 9 | 1.3 MB | **Deleted** |
| React-era screenshots | 16 (14 still referenced by the gallery) | 1.5 MB | Keep — only 9 truly unreferenced images deleted |
| Duplicate PDFs in corpus | 160 files | 27.2 MB | **Deduplicated** (kept the copies the DB points at) |
| Dead frontend pages / flows | 3 | 3 files | Fix or delete |
| Dead API client wrappers | 10 | 110 lines | Keep 3, delete 7 |
| Dead backend routes | 3 | — | Delete aliases, document rest |
| Unused Python functions | 8 (6 real + 2 framework validators) | ~250 lines | Delete 6, keep validators |
| Unused imports / variables | 17 imports + 3 variables | ~25 lines | Clean |
| Unused settings | 4 | — | Remove or implement |
| Unused frontend JS members | 14 | ~120 lines | Delete 11 |
| Unused CSS selectors / variables | 14 | ~40 lines | Delete |
| Undefined CSS classes in use | 4 | — | Define or replace |
| Dead DB column | 1 | — | Drop in migration |
| One-off / superseded scripts | 39 | 1.4 MB | Archive 30 |
| Stale dump shipped as canonical | 1 | 2.1 MB | Delete or relabel |

**Reclaimable on disk: ≈ 75 MB of 299 MB (25 %).** **Reclaimable in code: ≈ 600 lines** of first-party code plus ~110 lines of API wrappers.

---

## 3. Duplicate files (byte-identical)

| Duplicate | Identical to | Size | Why it is probably there | Action |
|---|---|---|---|---|
| `index.html` (root) | byte-identical to `frontend/index.html` | 18 KB / 386 lines | A "portal redirect" was documented, but the full portal was copied to the repo root during a deploy/export step | **Deleted** — the README serves `frontend/` on :8888, so the root copy was never the entry point |
| `database/seed_105_cases.py` | `backend/seed_105_cases.py` | 179 lines | Seeder copied into `database/` so the "database assets" folder looked self-contained | Delete one; keep `backend/` |
| `backend/storage/favicon.ico` | `frontend/favicon.ico` | 1 KB | Served by `GET /favicon.ico` on the API | **Keep** (not dead) |
| `database/lexguard_dump.sql` | *not identical* — older snapshot (145 cases, 1,179 logs) | 2.1 MB | Earlier export kept alongside the newer `database_dump.sql` (607 cases, 1,593 logs) | **Deleted**; README restore command now points at `database_dump.sql` |
| `report_diagrams_png/*`, `report_diagrams_svg/*` | **Correction:** only **4 of 13** PNGs are byte-identical to `report_builder/diagrams/*`. The 19 files in `report_diagrams_svg/` (9 `.svg` + 9 `.mmd` + 1 `.html`) are **unique** — they are the only Mermaid sources for the report figures | 6.3 MB | Output folders from two diagram pipelines (`generate_ppt_diagrams.py`, `render_svg_chrome.py`). `render_svg_chrome.py:6` reads them via a hard-coded `E:\SEM 5 PROJECT\...` path, so the dependency only works on the author's machine | **Keep** — deleting them loses the only editable source of the figures |

Also duplicated: `frontend/screenshots.zip` (**5.1 MB**) is an archive of `frontend/screenshots/` — pure redundancy unless it is a deliverable upload bundle.

---

## 4. Unused / stale assets and data

| Item | Evidence | Size | Purpose it probably served | Action |
|---|---|---:|---|---|
| `mermaid.min.js` | 0 references in any HTML/JS/Python | 3.2 MB | Diagrams were authored with Mermaid; the bundle was left in case the browser rendered `.mmd` files. Rendering actually happens offline via `render_svg_chrome.py` | **Delete** |
| `frontend/screenshots/react_*.png` (16) | **Correction: 14 of 16 ARE referenced** by `frontend/screenshots-gallery.html` (its `galleryItems` array builds `src="screenshots/${filename}"`) | 1.3 MB | Screenshots of the earlier React frontend (`Sem-5-Project/frontend`), kept as a "task completed" showcase for the report/viva | **14 kept** (restored after `main` deleted them and left 14 broken images); `react_landing`/`react_search` deleted |
| 9 unreferenced PNGs (`html_17_gallery`, `html_18_bookmarks`, `html_19_case_upload`, `html_search`, `html_search_budget`, `login`, `login_preview`, `react_landing`, `react_search`) | No `screenshots/<name>` reference in any HTML/JS/Python | 1.3 MB | Iteration leftovers from the screenshot-capture script | **Deleted** |
| `frontend/screenshots-gallery.html` | 0 inbound links; removed from nav by `scrub_all_prohibited_terms.py` | 20 KB | Internal "visual showcase" page for the report/viva | Keep out of production nav or delete |
| `backend/incoming_cases/` (50 PDFs) | All 50 are byte-identical to a PDF already in `storage/cases` or `backend/seed_corpus`; no code references the folder | 12 MB | Landing zone for `batch_ingest_*` downloads | **Deleted** (content preserved elsewhere); add to `.gitignore` |
| `backend/landmark_cases_manifest_template.csv/.json` | 0 references | 8 KB | Templates for bulk landmark import; superseded by `landmark_cases_data.json` | Delete |
| `backend/storage/extracted_metadata/manifest_1000.json` | Referenced only by a one-off script | 40 KB | Manifest for the "1000 case" ingestion experiment that never completed (607 cases exist) | Archive |
| `cases_lacking_original_pdfs.json` | 1 script reference | 115 KB | Audit list for purging cases without source PDFs — historical record | Move to `docs/audit/` |
| `new_51_cases_analysis.json` | 3 references | 107 KB | Analysis output for a 51-case batch | Archive |
| `report_builder/archive/*.docx` (11 files) | Not referenced; same report | 20 MB | Versioned snapshots before `build_report.py` overwrote them | **Delete** — regenerate from source |

---

## 5. Dead frontend flows

| Item | Evidence | Purpose | Action |
|---|---|---|---|
| `frontend/forgot-password.html` | Form POSTs to `/auth/forgot-password` — **backend has no such route** (only register/login/logout/me) | Password recovery was planned/UI-first | Implement endpoint or remove page + login link |
| `frontend/reset-password.html` | Calls `/auth/reset-password` — **no route**; no inbound link | Same | Same |
| `frontend/js/pages/*` for the above | Inline scripts inside the pages | — | — |
| `frontend/404.html` | 0 inbound links | Static 404 for the plain HTTP server (which has no error handler) | Keep only if the server uses it; otherwise delete |

Note: `login.html` shows a "Forgot password?" link to a page whose API does not exist — a user-visible dead end.

---

## 6. Dead API surface

### 6.1 Client wrappers never called (10)

| Wrapper (`lexguard-api.js`) | Endpoint | Endpoint reachable from UI? | Recommendation |
|---|---|---|---|
| `cases.getView` | `GET /cases/{id}/view` | No | Delete wrapper; keep route (used by external clients/demo) |
| `cases.verifyIntegrity` | `GET /cases/{id}/verify-integrity` | No — verify page uses the SHA-256 lookup instead | Delete wrapper |
| `cases.getOfficialContentUrl` | `GET /cases/{id}/official-content` | No — viewer uses `getDownloadUrl` | Delete wrapper |
| `cases.getLandmarks` | `GET /cases/landmarks` | No page uses it | Delete wrapper |
| `cases.getCitations` | `GET /cases/{id}/citations` | No | Delete wrapper (citation graph not surfaced) |
| `verification.lookupHash` | `GET /verification/lookup/{hash}` | No — UI uses POST `lookup` | Delete wrapper |
| `verification.getStreamUrl` | `GET /verification/documents/{id}/stream` | No | Delete wrapper |
| `comparison.compareMulti` | `POST /comparison/compare-multi` | **Yes** — `case-compare.js:113` calls the URL directly, bypassing the wrapper | Keep wrapper, refactor page to use it |
| `draft.getSessions` | `GET /draft/sessions` | **Yes** — `draft-assistant.js:157` calls the URL directly | Keep wrapper, refactor page |
| `draft.compareWithPrecedent` | `POST /draft/compare-with-precedent` | **Yes** — `draft-assistant.js:384` | Keep wrapper, refactor page |

**Pattern:** three pages bypass the API layer with hand-built URLs, which is why wrappers look dead. Normalising pages onto `LG.api.*` removes ~60 lines and restores a single CSRF/error-handling path.

### 6.2 Backend routes with no product use

| Route | Status | Recommendation |
|---|---|---|
| `GET /cases/{id}/pdf` | Alias of `/download` (two decorators on one function) | Keep as compatibility alias or delete decorator |
| `GET /auth/...` mounted twice (`/auth` and `/users`) | Duplicates all four auth operations in OpenAPI | Drop the `/users` alias |
| `POST /auth/forgot-password`, `POST /auth/reset-password` | **Do not exist**, but UI calls them | Implement (rate-limited, token table) or remove UI |

---

## 7. Dead Python symbols

### 7.1 Functions / classes never referenced (8)

| Symbol | File:line | Size | Probable purpose | Action |
|---|---|---:|---|---|
| `extract_metadata_from_pdf` | `services/text_sanitizer.py:81` | 164 lines | First-generation single-pass PDF metadata extractor; superseded by `ExtractionService` (3-pass) | **Delete** — largest dead block in the backend |
| `batch_generate_embeddings` | `services/embedding_service.py:60` | 13 | Batch encoding helper; ingestion encodes one case at a time | Delete or use during backfill (475 cases have no vector) |
| `verify_csrf_header` | `core/security.py:214` | 16 | Duplicate of `CSRFValidationMiddleware`; was a dependency before middleware existed | **Delete** (middleware is authoritative) |
| `EnrichedCaseDetailResponse` | `schemas/case.py:59` | 24 | Planned rich case-detail contract | Delete or adopt |
| `StatutoryTest` | `schemas/case.py:6` | 5 | Nested schema never wired into a response model | Delete |
| `PrecedentCited` | `schemas/case.py:13` | 5 | Same | Delete |
| `assemble_cors_origins` | `core/config.py:68` | 6 | Pydantic validator — **framework-invoked**, false positive | Keep |
| `validate_production_security` | `core/config.py:76` | 14 | Pydantic validator — false positive | Keep |

### 7.2 Unused imports / variables (17 + 3 pyflakes findings)

17 unused imports (`typing.List` ×4, `typing.Optional` ×2, `os` ×2, `claude_service` ×2, `get_current_user` ×2, `settings` ×2, `typing.Dict`, `typing.Any`, `verify_sha256`), 3 unused locals (`sci_query` `cases.py:1091`, `acts_str` `comparator.py:128`, `full_sec_tag` `extraction_service.py:673`), 3 f-strings with no placeholders, plus the Python-3.12-only f-string at `bookmarks.py:247`. **All safe to remove** (≈25 lines).

### 7.3 Settings declared but never read (4)

| Setting | Why it exists | Action |
|---|---|---|
| `DEBUG` | Conventional flag, never consumed | Remove or wire to logging |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Refresh-token rotation was planned; no refresh endpoint exists | Remove or implement `/auth/refresh` |
| `CSRF_SECRET` | Intended signed CSRF tokens; implementation compares cookie values instead | Remove (or implement HMAC-signed tokens) |
| `QUANTIZATION_BITS` | 4-bit quantisation for the local LLM; `local_llm_service` never uses it | Remove or pass to Bits-and-Bytes config |

### 7.4 Dead model column

`DocumentVersion.changed_at` — never written or read. `DocumentVersion` itself is **write-only**: versions are created on upload (`cases.py:167,335`) but no endpoint ever lists them. Either expose a version-history endpoint (valuable for an audit product) or drop the writes.

---

## 8. Dead frontend code

### 8.1 `LG.*` members never used (14)

| Member | File:line | Note |
|---|---|---|
| `LG.config.APP_NAME` | `lexguard-core.js:16` | title is hard-coded per page |
| `LG.config.COURT_MADURAI` | `lexguard-core.js:18` | — |
| `LG.config.COURT_SUPREME` | `lexguard-core.js:19` | — |
| `LG.utils.formatScore` | `lexguard-core.js:140` | replaced by inline `Math.round` in `search.js:150` |
| 10 API wrappers | see §6.1 | 7 deletable, 3 to be adopted |

### 8.2 CSS

Unused custom selectors (6): `.badge-status-published`, `.btn-court-red`, `.lg-layout`, `.lg-mono`, `.lg-serif`, `.lg-sidebar-badge`.

Unused custom properties (8): `--lg-court-red`, `--lg-court-red-dark`, `--lg-court-red-light`, `--lg-court-red-subtle`, `--lg-court-red-border`, `--lg-gold`, `--lg-gold-hover`, `--lg-gold-subtle` (components hard-code the hex values instead of using the tokens).

Referenced but **never defined** (4) — these silently fall back to browser/Bootstrap defaults, which is why the search card looks inconsistent: `btn-xs` (34 uses), `fs-7` (9 uses), `query-chip` (the 5 suggestion chips on `search.html`), `btn-check`.

> `fs-7` and `btn-xs` are used by the hybrid-search result card itself, so this is a *visual bug*, not just dead code.
>
> **Correction (2026-11-01):** an earlier pass reported 20 undefined classes. Most were false positives — `badge-gold` is defined at `lexguard.css:477`, and `badge-phase1/2`, `status-pill`, `status-in-session`, `status-next`, `status-passed-over`, `status-disposed`, `query-pill` are all defined in `lexguard.css` too. The remaining names in the old list (`btn-close`, `btn-group`, `btn-danger`, `btn-outline-*`) ship with Bootstrap, which was excluded from the CSS corpus. One real naming defect survives: **`.badge-gold` is not gold** — it renders `#fef2f2` on `#991b1b`, i.e. a red outline badge.

Other CSS hygiene: **188 `!important`** occurrences (156 in `lexguard.css`) and 104 inline `style="…"` attributes across pages — both signals of style specificity fights rather than design tokens.

### 8.3 Duplicated markup

Every page repeats the same `<head>` (fonts, Bootstrap, icons, two CSS files) and the same 5–6 `<script>` tags. 20 pages × ~30 lines ≈ 600 lines of duplicated shell, and 68 markup clone pairs in `jscpd`. Extract into a server-side include or a tiny JS shell builder (already half-done with `lexguard-nav.js`).

---

## 9. One-off scripts (39 in `scripts/` + 8 in `backend/`)

These are the biggest source of "dead code" by line count. They are **not imported by the application**; they were executed once during development.

| Family | Examples | Purpose | Status |
|---|---|---|---|
| Seeding | `seed_35_more_cases_to_reach_200.py`, `seed_final_20_cases_to_reach_200.py`, `seed_55_landmark_and_hc_cases.py`, `seed_landmark_precedents.py`, `seed_top12_statutes.py`, `expand_judicial_cases.py`, `add_more_2026_cases.py` | Incrementally grew the corpus to round numbers (105 → 130 → 200 → 240) | **Superseded** by one idempotent seeder; three share a 130-statement `generate_case_pdf()` |
| PDF renames / moves | `standardize_and_rename_all_pdfs.py`, `rename_case_pdfs.py`, `reconcile_and_seed_all_pdfs.py`, `scan_recent_pdfs.py` | Canonical filename migration | Done; history only |
| HTML patchers | `update_search_ui.py`, `update_acts_ui.py`, `update_viewer_ui.py`, `patch_case_upload.py`, `apply_workstream_1_ui_polish.py` | String-replace HTML in place (some hard-code `e:/SEM 5 PROJECT/...`) | **Deleted 2026-11-01** — 11 patchers (2,312 lines) removed in `DEAD_CODE_SCAN.md` §2.1 |
| Terminology scrubbers | `scrub_all_prohibited_terms.py`, `scrub_remaining_terms.py`, `verify_prohibited_terms_and_dom.py` | Replace "Semester 5 Project", "PostgreSQL 17", "0-byte" wording | Historical; keep one as a style-guard test, delete rest |
| Ingest / download | `batch_ingest_judgments.py`, `bulk_ingest.py`, `ingest_30_new_cases.py`, `analyze_all_new_pdfs.py`, `enrich_corpus_from_pdfs.py`, `link_citation_network.py` | Corpus operations | Keep 2 (batch ingest, enrich); archive the rest |
| Screenshots / QA | `capture_all_screenshots.py`, `capture_html_red_white.py` (Playwright/Selenium), `find_404_errors.py` | Report screenshots and route validation | Keep `find_404_errors.py` (useful CI check), archive capture scripts |
| Schema migrations | `backend/migrate_columns.py`, `migrate_source_fields.py`, `migrations/001_add_structured_fields.py`, `scripts/migrate_v2_schema.py`, `migrate_bookmarks_binder.py` | Alembic-less ad-hoc migrations | **Consolidate** into one Alembic baseline |

**Recommendation:** create `tools/archive/` (or delete) and keep only `scripts/batch_ingest_judgments.py`, `scripts/enrich_corpus_from_pdfs.py`, `scripts/link_citation_network.py`, `scripts/find_404_errors.py`, `scripts/seed_*` → replaced by `scripts/seed_corpus.py`.

---

## 10. What looks dead but is not — do not delete

| Item | Why it must stay |
|---|---|
| `uvicorn`, `python-multipart`, `email-validator`, `psycopg2-binary` in `requirements.txt` | Used at runtime by the ASGI server, FastAPI form/file parsing, Pydantic `EmailStr`, and the SQLAlchemy PostgreSQL URL — never imported in source |
| `backend/storage/favicon.ico` | Served by `GET /favicon.ico` (`main.py:164`) |
| `assemble_cors_origins`, `validate_production_security` | Pydantic validators (framework-invoked) |
| `frontend/js/lexguard-crypto.js` | Loaded only by `verify.html` (SHA-256 in browser) |
| `PGVECTOR`/`pgvector` dependency | Activated only when PostgreSQL + extension are present (`models/case.py:9`) |
| `frontend/unauthorized.html` | Redirect target in `lexguard-auth.js:142` |
| `backend/seed_corpus/*.pdf` (29) | Referenced by `seed_corpus.py` and `manifest.json` |
| `cases_lacking_original_pdfs.json` | Historical audit evidence for a claim in the report |

---

## 11. Cleanup sequence (safe order)

> **Applied (2026-11-01):** the zero-risk half of this sequence has landed on `main` (`2d5da19`, `5370ddf`) and on this branch (237 files / 72.2 MB). See [`CLEANUP_LOG.md`](CLEANUP_LOG.md) for what each commit removed and which items were kept after re-verification. The remaining items are the code deletions in step 3, which need test runs and belong in their own commit.


```bash
# 0. Branch and baseline
git checkout -b chore/dead-code
python -m compileall -q backend || echo "fix bookmarks.py:247 first"

# 1. Zero-risk deletions (no references)
git rm mermaid.min.js frontend/screenshots.zip
git rm frontend/screenshots/react_*.png
git rm -r report_builder/archive
git rm backend/landmark_cases_manifest_template.csv backend/landmark_cases_manifest_template.json
git rm database/lexguard_dump.sql            # stale 145-case dump; README points at it by mistake
git rm index.html                            # duplicate of frontend/index.html
git rm database/seed_105_cases.py            # duplicate of backend/seed_105_cases.py

# 2. Move large non-code data out of Git
git rm -r --cached backend/incoming_cases backend/storage storage/cases
printf "backend/storage/\nbackend/incoming_cases/\nbackend/*.db\nstorage/\n" >> .gitignore
# then re-add storage/cases via Git LFS or an external download script

# 3. Code deletions (verify with tests after each block)
#    - text_sanitizer.extract_metadata_from_pdf, security.verify_csrf_header
#    - unused schemas StatutoryTest, PrecedentCited, EnrichedCaseDetailResponse
#    - 7 unused LG.api wrappers, LG.utils.formatScore, 3 LG.config constants
#    - 6 unused CSS selectors, 8 unused CSS variables

# 4. Automation so it does not come back
pip install vulture pyflakes
vulture backend/app --min-confidence 80
pyflakes backend/app
npx jscpd frontend --threshold 8
```

**Guard-rails to add**

- CI job: `pyflakes` + `vulture --min-confidence 80` + `jscpd --threshold 8` + `compileall` on Python 3.12.
- A `scripts/check_assets.py` test that fails when a file under `frontend/assets` is unreferenced for 30 days.
- Delete-on-sight rule for `update_*.py` / `scrub_*.py` patchers: any HTML change goes through the component layer, not regex rewriting.

---

## 12. Why the repo accumulated this (root cause)

1. **Two frontends.** A React client (`Sem-5-Project/frontend`) was replaced by the HTML client; its screenshots, CSS and page ideas stayed behind.
2. **Rename-and-scrub scripts instead of design changes.** 12 `update_*.py`/`scrub_*.py` files string-patched HTML, leaving orphan classes and inconsistent tokens.
3. **UI-first features.** Forgot/reset-password pages and API wrappers were written before endpoints existed, and never connected.
4. **Multiple data pipelines.** SQLite + two PostgreSQL dumps + manifests + incoming staging = four "sources of truth".
5. **No linting or CI.** Nothing ever failed for an unused import or a 3.2 MB orphan bundle.
6. **AI-assisted generation.** Large uniform blocks (docstrings, wrappers, full pages) were produced faster than they were wired up or pruned.

The cleanup above is mostly mechanical; the durable fix is the CI gate plus the component extraction described in `SEARCH_CARD_REDESIGN.md`.
