# Dead Code & Unused Animation Audit — 2026-11-01

**Scope:** the tree as of `b55d7d3` (branch `arena/f0907ec3-lexguard-html`, based on `main@b3fe746`).
**Question answered:** *what is unused, what was it probably there for, and what did we remove?*
**Companion to:** `docs/DEAD_CODE_REPORT.md` (31 Oct snapshot, taken before the 237-file cleanup). This scan only reports what is still in the tree today and completes §3 of `docs/CLEANUP_LOG.md`.

---

## 1. Method

| Check | Tool | Threshold |
|---|---|---|
| Unused imports / locals / redefinitions | `ruff check --select F401,F811,F841,F821,F822,F823` | default |
| Unused functions, classes, variables | `vulture` on `backend/app` | confidence ≥ 70 |
| Cross-file Python import graph | AST walk → module → importer map | zero importers **and** no entry-point role |
| Unused frontend declarations | Acorn AST walk over all `frontend/js/*.js`, name counted across every `.js` file and every inline `<script>` | declared once, referenced nowhere |
| Unused `LG.api.*` client wrappers | Acorn parse of the `LG.api` object literal × literal call sites | zero call sites (no dynamic `LG.api[…]` access exists) |
| Unused CSS selectors | selector extraction × class tokens in HTML/JS | zero tokens |
| Unused / unreferenced files & assets | basename + path reference scan across HTML/JS/CSS/Py/MD/SH | zero references outside the file itself |
| Duplicate assets | SHA-256 over every non-PDF tracked file | byte-identical pairs |
| **Animations** | grep for `@keyframes`, `animation:`, `animation-name:`, `requestAnimationFrame`, `.animate(`, `lottie`/`bodymovin`/`GSAP`/`AOS`/`anime.js`, `prefers-reduced-motion`, plus asset-extension scan for `.gif/.webm/.mp4/.riv/.lottie` | see §4 |

**Not re-run** (results are final, per the standing decision): plagiarism/cross-repo scans, PDF-hash scans, corpus backfill measurements.

---

## 2. Removed in this PR

Nothing below had a live caller, and every item's *purpose* is stated so the removal can be undone knowingly.

### 2.1 Superseded UI patcher scripts — 11 files, 2,312 lines

**What they were for:** one-shot codemods written while the UI was being built. Each one held a literal `target`/`replacement` pair and rewrote `frontend/*.html` or `frontend/js/**` in place, then was never needed again.

**Why they are dead now:** every one of them resolves its inputs through absolute Windows paths from the original development machine (`e:\SEM 5 PROJECT\Lexguard\lexguard-html\...`) or through the pre-monorepo layout (`lexguard-html/js/pages/...`). On any current checkout those paths do not exist, so the scripts can only fail — and if the paths *did* exist, the string replacements would corrupt files that have since been rewritten by hand.

| Removed | Lines | Purpose it served | Evidence it cannot run |
|---|---:|---|---|
| `scripts/apply_workstream_1_ui_polish.py` | 273 | Batch "workstream 1" copy/colour polish across pages | 2 hard-coded `e:\SEM 5` roots, 6 in-place writes |
| `scripts/patch_case_upload.py` | 87 | Rewrote the upload success handler in `case-upload.js` | Opens `lexguard-html/js/pages/case-upload.js` (pre-monorepo path, gone) |
| `scripts/update_acts_ui.py` | 73 | Added the acts-explorer cards | 3 `e:\SEM 5` roots |
| `scripts/update_advocate_binders_ui.py` | 706 | Generated the whole bookmarks/binders page + modals | 2 `e:\SEM 5` roots |
| `scripts/update_case_upload_batch.py` | 99 | Inserted the batch-ingestion tab into `case-upload.html` | 2 `e:\SEM 5` roots |
| `scripts/update_case_viewer_certificate.py` | 240 | Injected the digital-seal ribbon and certificate modal | 4 `e:\SEM 5` roots |
| `scripts/update_index_metrics.py` | 106 | Rewrote the landing-page trust-metric cards (hard-coded "15 Courts / 130 Verified") | 3 `e:\SEM 5` roots |
| `scripts/update_precedent_ui.py` | 252 | Added citation badges and precedent panel to the case viewer | 6 `e:\SEM 5` roots |
| `scripts/update_search_ui.py` | 71 | Patched search-result markup | 1 `e:\SEM 5` root |
| `scripts/update_viewer_and_search_ui.py` | 355 | Combined viewer + search UI patch | 2 `e:\SEM 5` roots, 5 writes |
| `scripts/update_viewer_ui.py` | 50 | Small viewer-header patch | 3 `e:\SEM 5` roots |

None of the eleven is referenced by code, tests, CI, or documentation; the only textual mention was the recommendation in `docs/DEAD_CODE_REPORT.md` §12 to delete them.

### 2.2 Dead CSS — 6 selectors, 44 lines

**What they were for:** styling hooks for markup that no longer exists (or was renamed). Verified by scanning every class token in all 20 HTML pages and 27 JS files.

| Removed | Rules | Purpose it served | Why dead |
|---|---:|---|---|
| `.lg-layout` | 1 | Page-level flex shell wrapper | No page carries the class; layout is driven by `body[data-active-page]` + Bootstrap containers |
| `.lg-sidebar-badge` | 1 | Counter pill in the sidebar | The pill markup was stripped by the terminology scrubbers |
| `.badge-status-published` | 1 (out of a 2-selector group) | Green "published" badge | `lexguard-core.js` emits `badge-status-verified` for published/verified/active |
| `.lg-case-card .case-snippet` (+ `mark`) | 2 | Pre-BEM snippet + highlight styling | `case-card.js` renders `lg-case-card__snippet` now |
| `.lg-serif` | 1 (alias in a group) | Alias of `.font-serif` (used 40×) | Alias never used |
| `.lg-mono` | 1 (alias in a group) | Alias of `.font-mono` (used 94×) | Alias never used |
| `.btn-court-red` (+ `:hover`/`:focus`) | 3 (alias in a group) | Red gradient button | `.btn-gold` (51 uses) and `.btn-judicial-outline` cover every button in the UI |

Selector groups were edited member-by-member, so the live classes keep their rules.

### 2.3 Dead client wrappers — 13 methods, 107 lines

**What they were for:** `lexguard-api.js` mirrored *every* backend route as a `LG.api.<area>.<method>()` helper. Pages ended up calling the generic `LG.api.request({url: …})` for several areas instead, leaving those mirrors with zero call sites (checked against literal `LG.api.<area>.<method>` occurrences; there is no computed `LG.api[…]` access anywhere, so the counts are exhaustive).

| Removed wrapper | Purpose (backend route it mirrored) | Call sites |
|---|---|---:|
| `LG.api.auth.me` | `GET /auth/me` — session re-hydration | 0 |
| `LG.api.cases.list` | `GET /cases/` — paged repository listing | 0 |
| `LG.api.cases.getView` | `GET /cases/{id}/view` — CIS viewer payload | 0 |
| `LG.api.cases.getOfficialContentUrl` | `GET /cases/{id}/official-content` — certified text download | 0 |
| `LG.api.cases.getLandmarks` | `GET /cases/landmarks` — landmark precedent list | 0 |
| `LG.api.cases.getCitations` | `GET /cases/{id}/citations` — citation graph | 0 |
| `LG.api.verification.lookupHash` | `GET /verification/lookup/{hash}` — hash lookup (GET form) | 0 (the POST form `lookup` is used) |
| `LG.api.verification.getStreamUrl` | `GET /verification/documents/{id}/stream` — inline PDF stream | 0 |
| `LG.api.comparison.compare` | `POST /comparison/compare` — two-case comparison | 0 |
| `LG.api.comparison.compareMulti` | `POST /comparison/compare-multi` — N-way comparison | 0 |
| `LG.api.draft.analyze` | `POST /draft/analyze` — draft critique | 0 |
| `LG.api.draft.getSessions` | `GET /draft/sessions` — saved drafts | 0 |
| `LG.api.draft.compareWithPrecedent` | `POST /draft/compare-with-precedent` | 0 |

The `draft` namespace is therefore gone; `pages/draft-assistant.js` reaches those routes through `LG.api.request`, which is unchanged. The file header and section numbering were corrected (9 areas → the 8 the UI uses). **The backend routes themselves are untouched** — re-adding a wrapper is a 5-line change if a page ever needs one.

### 2.4 Dead JS variables — 2

| Removed | File | Purpose it served |
|---|---|---|
| `const $submitBtn` | `js/pages/search.js` | Cached `#search-submit-btn`; submission is handled by the form's `submit` event, so the handle was never read |
| `const $pdfCanvas` | `js/pages/case-viewer.js` | Cached `#pdf-canvas`; PDF.js is given the `<canvas>` via its own id lookup |

### 2.5 Unused imports and locals — 33 Python files, −69 / +27

Applied with `ruff --fix` over `backend/`, `scripts/`, `report_builder/`. Examples: `Counter, defaultdict` → `Counter`; an unused `pdfplumber` import inside `text_sanitizer.py`; unused `os`/`re`/`json`/`sys` imports in one-off corpus scripts; unused imports in five test modules.

**Two false positives were deliberately preserved:**

| Kept | Why ruff is wrong |
|---|---|
| `backend/verify_db.py` — `from app.models import (User, Case, …)` | Side-effect imports: importing the models registers their tables on `Base.metadata` before the `create_all()` call three lines later. Deleting them silently empties the database. Now annotated `# noqa: F401` with an explanatory comment. |
| `backend/download_models.py` — `import hf_transfer` | Availability probe: the import *is* the check that flips `HF_HUB_ENABLE_HF_TRANSFER`. Now annotated `# noqa: F401`. |

### 2.6 A reference to a symbol that does not exist (fixed, not removed)

`backend/tests/test_case_pattern_service.py::test_every_profile_declares_a_resolvable_key_set` iterated `_PROFILES`, a name that has never existed in `case_pattern_service.py` (the public `PROFILES` list does). The test raised `NameError` on every run, so the invariant it guards was never checked. Fixed by importing `PROFILES`. The test now passes and the invariant holds.

---

## 3. Deliberately **not** removed

Each of these came up in the scan; each has a purpose that makes deletion a product decision rather than a cleanup.

| Item | Purpose | Recommendation |
|---|---|---|
| `frontend/reset-password.html` + `js/pages/reset-password.js` | Landing page for the emailed password-reset link (`POST /auth/reset-password`) | **Broken flow**: nothing links to it and the backend never builds the link. Wire it into the reset e-mail or delete the pair. |
| `frontend/screenshots-gallery.html` + `frontend/screenshots/*.png` (31 files: 17 `html_*`, 14 `react_*`, 4.4 MB) | "31-Task Visual Execution Showcase" linked from `README.md`; the page builds `src="screenshots/…"` from an inline array | Reachable by URL and advertised in the README — keep. The earlier cleanup already dropped the 2 `react_*` files the gallery never referenced. |
| `report_builder/diagrams/*.png` ↔ `report_diagrams_png/*.png` | 4 byte-identical pairs: the mini-project report embeds one set, the slides export uses the other | Keep both: the figures are referenced by `build_report.py` / `render_svg_chrome.py` by filename. |
| `report_builder/diagrams/LexGuard_Mini_Project_Report_user_saved.docx` (85 KB, 72 k chars) | An earlier autosaved revision of the mini-project report | Authorship artefact; not referenced by any build step. Move to `docs/archive/` if it should not sit next to the build assets. |
| `database/database_dump.sql` (3.8 MB) | pg_dump of the PostgreSQL schema shipped for the submission, referenced by `README.md` and `PROJECT_AUDIT.md` | Now superseded by `migrations/001` + `002`. Regenerate or relabel as "schema snapshot, not a restore path". |
| `scripts/seed_*.py`, `expand_judicial_cases.py`, `add_more_2026_cases.py` (7 files, 284 KB) | Corpus genesis: they hold the judgment text that produced the 607 stored cases | **Data provenance — do not delete.** They cannot be re-run (hard-coded Windows paths) but they are the only record of the seed content. |
| `scripts/scrub_all_prohibited_terms.py`, `scrub_remaining_terms.py`, `verify_prohibited_terms_and_dom.py` | Compliance scrubbing of prohibited wording ("Semester 5 Project", "PostgreSQL 17", "0-byte") | Historical; `verify_prohibited_terms_and_dom.py` is worth converting into a style-guard test. |
| `scripts/capture_all_screenshots.py`, `capture_html_red_white.py`, `find_404_errors.py` | QA: Playwright/Selenium screenshots for the report, plus a route check | Keep `find_404_errors.py`; the capture scripts need a browser stack the repo does not ship. |
| `backend/verify_db.py`, `integrity_report.py`, `enrich_case_structure.py`, `migrate_columns.py`, `migrate_source_fields.py`, `batch_ingest_1000.py`, `seed_105_cases.py`, `download_models.py`, `download_and_ingest_official.py` | Operational entry points (no importer, but each is a `python <file>` tool) | Keep; they are documented in `docs/NEXT_STEPS.md` / `README.md`. |
| `backend/storage/favicon.ico` | Byte-identical to `frontend/favicon.ico`, but served by `GET /favicon.ico` from the API | Keep (not dead). |
| 9 remaining `F841` locals (`cases.py:1137`, `comparator.py:128`, `extraction_service.py:923`, `batch_ingest_1000.py:85`, `download_models.py:152/154`, `render_svg_chrome.py:71`, `reconcile_and_seed_all_pdfs.py:457/621`) | Each is the result of a call that may have side effects (`compute_seal(...)`, model load) or sits in code that a rewrite will touch anyway | Ruff classifies every one as an *unsafe* fix; left alone rather than turning a lint win into a behaviour risk. |
| `scripts/verify_users.py` | Inspects the `users` table | Starts with a UTF-8 BOM, so it must be run as a file (never imported). Harmless; noted so nobody re-adds it by copy-paste. |

`vulture` found **no** unused function or class in `backend/app` at confidence ≥ 70: the framework-referenced surface (route handlers, Pydantic models, SQLAlchemy columns) is the only thing a name-based scan would flag, and those are excluded by design.

---

## 4. Animation assets and animation code — inventory

The repository contains **no animation assets at all**: zero `.gif`, `.webm`, `.mp4`, `.riv`, `.lottie`, zero Lottie/Bodymovin JSON, zero animated SVGs (`<animate>`/`<animateTransform>` count: 0 across all 10 `.svg` files), and **zero `@keyframes` blocks** in either stylesheet or in any inline `<style>`. So there was nothing to delete in this category — the honest result is an empty set, not a fabricated one.

What the UI actually uses, and what happens to it:

| Construct | Where | Count | Verdict |
|---|---|---:|---|
| `transition:` declarations | `components.css` (20), `lexguard.css` (3) | 23 | **Live** — hover/focus states, sidebar collapse, progress ring |
| `@media (prefers-reduced-motion: reduce)` guard | `components.css:991` | 1 block | **Kept** — it neutralises exactly those 23 transitions for motion-sensitive users; removing it would be an accessibility regression, not a cleanup |
| `$('html, body').animate({scrollTop…})` | `js/pages/case-upload.js:122` | 1 | **Live** — jQuery is loaded on every page (`cdnjs` 3.7.1), so this is a real smooth-scroll, not a dead call |
| `transitionend` / `requestAnimationFrame` / `.animate(` beyond the above | — | 0 | Nothing to remove |
| Animated/vendor libraries (`animate.css`, GSAP, AOS, anime.js, Lottie) | — | 0 loaded | Nothing to remove |

The `stroke-dashoffset` transition (`components.css:356`) is the verification progress ring; it is driven by JS class toggles that exist in `js/pages/verify.js`.

---

## 5. Verification

```text
# before (b55d7d3, this venv)
4 failed, 274 passed, 7 skipped

# after (this PR, same venv)
3 failed, 275 passed, 7 skipped
```

The one-test improvement is the `_PROFILES` fix in §2.6. The three remaining failures are pre-existing and unrelated to this change:

| Test | Failure | Verdict |
|---|---|---|
| `test_case_pattern_service.py::test_corpus_profiles_cover_all_registries` | `assert report["profile"]["confidence"] >= 0.55` → `0.0` | Pre-existing detection regression in `case_pattern_service` (corpus file 01) |
| `test_case_pattern_service.py::test_corpus_repaired_layout_recovers_punjab_caption` | same profile scores 0.0 | Pre-existing |
| `test_milestone1.py::test_case_upload_tamper_detection_and_approval` | fails identically on `main@b3fe746` | Pre-existing |

Additional checks run for this PR:

```bash
node --check frontend/js/lexguard-api.js      # syntax OK after removing 13 wrappers
node --check <every frontend/js file>         # OK
ruff check --select F401,F811,F841,F821 backend scripts report_builder
                                              # only the 9 documented unsafe F841s remain
grep -c "lg-layout\|case-snippet\|btn-court-red\|lg-serif\|lg-mono" frontend/css/*.css   # 0
grep -rn "update_search_ui\|patch_case_upload\|…" backend frontend scripts docs          # 0 (except this file)
```

---

## 6. Totals

| Metric | Value |
|---|---|
| Files deleted | 11 (all superseded codemods) |
| Lines deleted | 2,312 script lines + 44 CSS lines + 107 JS lines + 69 Python lines |
| Python files touched by the import/variable pass | 33 |
| Dead CSS selectors removed | 6 (of 145 scanned) |
| Dead `LG.api` wrappers removed | 13 of 39 |
| Dead frontend declarations removed | 2 |
| Animation assets found | **0** |
| Animation-related removals | 0 (the one reduced-motion guard is load-bearing) |
| Broken symbol references fixed | 1 (`_PROFILES`) |
| Tests | 275 passed (was 274), same 3 pre-existing failures |
