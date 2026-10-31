# Cleanup Log — 2026-11-01

Record of the cleanup work and of how it was reconciled with `main`, which received an overlapping cleanup while this branch was open.

| Stage | Commit | Result |
|---|---|---|
| Docs + plans | `a821990`, `35c2bbc` | Audit, search-card plan, dead-code report, optimisation plan, logo brief (now on `main` as `5370ddf`, `90a37e6`) |
| First cleanup pass | `a6bf512` | 237 files / 72.2 MB removed, README and `.gitignore` corrected |
| Reconciliation | this commit | Rebased onto `main@7f36482`; overlaps dropped, regressions fixed, docs made truthful again |

## 1. What `main` had already removed

`main` independently applied most of the deletions (`2d5da19`, `5370ddf`): `mermaid.min.js`, `frontend/screenshots.zip`, `report_builder/archive/`, `database/lexguard_dump.sql`, `database/seed_105_cases.py`, `backend/incoming_cases/`, `index.html`, and the duplicate PDFs in `storage/cases/`. This branch no longer re-deletes them; the evidence for each is in `DEAD_CODE_REPORT.md` §8.

`main` also removed three things this branch had deliberately kept:

| Removed on `main` | Why that was a regression | Resolution here |
|---|---|---|
| All 16 `frontend/screenshots/react_*.png` | **14 of them are rendered by `frontend/screenshots-gallery.html`** (its `galleryItems` array builds `src="screenshots/${filename}"`). Deleting them left 14 broken images on a page the README advertises as the "31-Task Visual Execution Showcase" | Restored the 14 referenced files (1.4 MB). The 2 unreferenced ones (`react_landing`, `react_search`) stay deleted |
| `index.html` (root) | Not a regression — the README serves `frontend/` on port 8888, so the root copy was never the entry point | Kept deleted; README tree updated |
| — | `README.md` still told users to restore from `database/lexguard_dump.sql`, a file that no longer exists | README now points at `database/database_dump.sql` and states that the shipped SQLite DB needs no setup |

## 2. Verification of the current tree

```bash
# Gallery integrity — 31 entries, 0 missing files
python - <<'PY'
import re, os
g = open('frontend/screenshots-gallery.html').read()
names = set(re.findall(r'filename:\s*"([^"]+)"', g))
print([n for n in names if not os.path.exists('frontend/screenshots/' + n)])   # []
PY

# Corpus integrity — 596 unique PDFs, no duplicate hashes, 607 rows resolve
# (2 dangling paths remain: they were dangling before any cleanup)

# No reference to a deleted path
grep -rn "lexguard_dump\|mermaid.min.js\|screenshots.zip" README.md backend frontend scripts   # no hits

# Backend unchanged
python -m compileall -q backend    # only the known bookmarks.py:247 f-string error
```

## 3. Still open

Code deletions from `DEAD_CODE_REPORT.md` §11 step 3 (`text_sanitizer.extract_metadata_from_pdf`, `security.verify_csrf_header`, unused schemas, `LG.*` members, unused CSS) — `main` has done part of this; the rest needs test runs and belongs in its own commit.

`Git` history still holds every removed blob, so `.git` does not shrink. Reclaiming it requires a deliberate `git filter-repo` pass, which invalidates existing clones.
