# Cleanup Log — 2026-11-01

Applied the zero-risk half of the sequence in [`DEAD_CODE_REPORT.md`](DEAD_CODE_REPORT.md) §11. **237 files, 72.2 MB** removed from the working tree, plus two docs/config corrections. No application logic changed and no database row was orphaned.

Branch: `arena/64b06a8b-lexguard-html` · base `1b2068e` · one commit.

## 1. What was deleted

| Target | Files | Size | Why it was safe | Evidence |
|---|---:|---:|---|---|
| `mermaid.min.js` (repo root) | 1 | 3.2 MB | Zero references in HTML/JS/Python; diagrams are rendered offline by `report_builder/render_svg_chrome.py` | `grep -r mermaid` → only the file itself and the audit doc |
| `frontend/screenshots.zip` | 1 | 5.1 MB | Archive of `frontend/screenshots/`, which is still present; nothing links to the zip | no `src`/`href`/`open()` reference |
| `report_builder/archive/` | 12 | 20 MB | Superseded `.docx` exports (`_backup`, `_latest`, `_updated_20261028_…`); the shipped report lives in `report_builder/` | 0 references outside the audit doc |
| `backend/incoming_cases/` | 50 | 12 MB | **Every** PDF is byte-identical to a file already in `storage/cases/` or `backend/seed_corpus/pdfs/`; it is an ingestion landing zone, not a source of truth. `backend/batch_ingest_1000.py:55` recreates the folder with `mkdir(parents=True, exist_ok=True)`, so the pipeline still runs | SHA-256 grouping: 50/50 matched an existing copy |
| Duplicate PDFs in `storage/cases/` | 160 | 27.2 MB | 160 byte-identical pairs (double ingestion of the same judgment under two hashed filenames). The copy the database `file_path` points at was **kept** in every pair | 160 groups, each with ≥1 DB-referenced member; 160 unreferenced members removed |
| `database/lexguard_dump.sql` | 1 | 2.1 MB | Stale 145-case export superseded by `database/database_dump.sql` (607 cases); README pointed at the wrong one | different row counts; README now updated |
| `database/seed_105_cases.py` | 1 | 6 KB | Byte-identical duplicate of `backend/seed_105_cases.py` | `cmp` → identical |
| `backend/landmark_cases_manifest_template.csv/.json` | 2 | 8 KB | Templates from an abandoned import flow; the live data is `landmark_cases_data.json` | 0 code references |
| Unreferenced screenshots | 9 | 1.3 MB | Not in `screenshots-gallery.html`'s `galleryItems` array and not referenced with a `screenshots/<name>` path anywhere | gallery array (31 entries) vs 40 files on disk |
| **Total** | **237** | **72.2 MB** | | |

Kept deliberately (see the report's do-not-delete list): `backend/seed_corpus/*.pdf` (used by `test_madras_hc_extraction.py` and the seeder), `report_diagrams_svg/*` (only copy of the Mermaid sources), `frontend/screenshots/react_*.png` (14 of 16 are rendered by the gallery), `backend/lexguard.db` (only SQLite copy of the corpus).

## 2. Corrections to the earlier report

Re-verification before deleting disproved three claims, which the report now marks as corrected:

1. **`react_*.png` were not dead.** 14 of 16 appear in `frontend/screenshots-gallery.html`, which builds `src="screenshots/${item.filename}"` from its `galleryItems` array. Deleting them would have broken the gallery.
2. **`report_diagrams_*` are not duplicates.** Only 4 of 13 PNGs match `report_builder/diagrams/`; the 19 files in `report_diagrams_svg/` (9 `.svg`, 9 `.mmd`, 1 `.html`) are unique and are the editable source of the report figures.
3. **`badge-gold` is defined** (`lexguard.css:477`) — only `fs-7`, `btn-xs`, `query-chip`, `btn-check` are missing.

## 3. Other changes in this commit

- **Root `index.html`** — was a byte-identical copy of `frontend/index.html` (386 lines). Replaced with a 15-line redirect. Note the README starts the static server inside `frontend/`, so the root copy was never the real entry point; the redirect only helps if someone serves the repo root.
- **`README.md`** — database restore command now uses `database/database_dump.sql`; notes that the shipped SQLite DB needs no setup; corpus size 208 → 607; tree no longer lists the deleted dump/seeder.
- **`.gitignore`** — ignores `backend/incoming_cases/`, `report_builder/archive/`, `frontend/screenshots.zip` so they cannot be re-added by a future `git add -A`.

## 4. Verification performed

```bash
# 1. No database row lost its file
python - <<'PY'   # 607 rows checked against file_path on disk
# → 2 missing, both pre-existing dangling paths documented in the audit
PY

# 2. Corpus still de-duplicated but complete
# storage/cases: 596 unique hashes before and after (the 160 removed were exact duplicates)

# 3. Nothing references a deleted path
grep -rn "lexguard_dump\|mermaid.min.js\|incoming_cases\|screenshots.zip" README.md backend frontend scripts
# → no hits outside docs/

# 4. Backend unchanged
python -m compileall -q backend   # only the known bookmarks.py f-string error (Python 3.12 syntax)
```

## 5. What this does *not* shrink

Git history still contains every removed blob, so `.git` stays at its current size — a fresh clone only avoids the 72 MB in the working tree. To reclaim history you need a rewrite (`git filter-repo --path … --invert-paths`), which invalidates every existing clone and should be a separate, deliberate operation. The shipped `backend/lexguard.db` and `storage/cases/*.pdf` are still tracked; moving the corpus out of Git needs an external host or Git LFS plus a fetch script, which is a data-hosting decision, not a cleanup step.

## 6. Still open from §11 step 3

Code deletions need test runs first: `text_sanitizer.extract_metadata_from_pdf`, `security.verify_csrf_header`, 3 unused schemas, 7 unused `LG.api` wrappers, `LG.utils.formatScore`, 3 `LG.config` constants, 6 unused CSS selectors, 8 unused CSS variables. Recommended as the next commit, one family at a time, with `pytest` between each.
