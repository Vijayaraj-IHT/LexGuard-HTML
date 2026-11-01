# What to do next — options analysis

**Verified state at `00472d7` (branch, based on `main@7f36482`), 2026-11-01.** Every number below was re-measured today; nothing is carried over from the audit without re-checking.

## 1. Where the project actually stands

### Fixed since the audit (do not re-do)

| Item | Evidence |
|---|---|
| Backend imports on Python 3.11 again — the `bookmarks.py` f-string was rewritten as `bench_name = c.judge or "Hon'ble Bench"` | `python -m compileall backend/app` → 0 errors |
| 6 malformed JSON cells cleaned; `safe_json_deserializer` added to the SQLite engine | `json_valid()` → 0 bad rows on both columns |
| Dead assets removed, corpus de-duplicated, gallery restored | `docs/CLEANUP_LOG.md` |
| Docs corrected (`react_*.png`, `report_diagrams_*`, `badge-gold`) | `docs/DEAD_CODE_REPORT.md` §8 |

### Still open, with magnitudes

| Defect | Measured now | Where | Consequence |
|---|---|---|---|
| Browsing / empty query returns `relevance_score = 1.0` for every hit | `search.py:191` | frontend renders "100% Match" on all rows |
| `matched_snippets` interpolated unescaped | `search.js:156–162` | stored-XSS vector; `<`/`&` in judgment text breaks the card |
| Server-side `<mark>` highlights built then discarded by the client | `search.py:85–115` vs `search.js` | wasted work, inconsistent emphasis |
| `fs-7`, `btn-xs`, `query-chip`, `btn-check` referenced but never defined | 0 matching selectors in `frontend/css/*` | score text and small buttons fall back to defaults |
| `defer(Case.full_text)` defeated by `c.full_text` reads in the scoring loop | `search.py:246` vs `320`, `385` | one lazy load per row → the N+1 the defer was meant to prevent |
| Cases with no embedding | **475 / 607 (78 %)** | embedding column null | "semantic hybrid search" is keyword-only for most of the corpus |
| Cases with no extracted full text | **299 / 607 (49 %)** | `full_text` empty | snippet extraction and text matching have nothing to read |
| Placeholder judges | **308 / 607** | `judge` = "Hon'ble Bench" | card shows a non-answer where a name belongs |
| Duplicate `file_hash` groups | **9** | `cases` | same judgment reachable under two rows |
| Dangling `file_path` values | **2** | `cases` | download 404s |
| Wrong `year` vs `case_no` | 178 of 434 parseable rows | `cases` | a 2020 appeal renders as 1961 |
| Hard-coded API base | `lexguard-core.js:13` → `http://127.0.0.1:8000/api/v1` | frontend | app only works on the author's machine; cannot be previewed or deployed |
| No CI, no lint config, 49 tests unrun in CI | `backend/tests` 13 modules | repo | every defect above can silently return |
| README contradicts the corpus | "208 cases" at lines 18, 41 vs 607 | README | reviewers see stale numbers |
| Heavy dependency set | `requirements.txt` pins torch, sentence-transformers, transformers, accelerate, pymupdf | backend | install takes GBs; `pymupdf` is unused (AGPL, extraction is pdfplumber) |
| Repo weight | `.git` 115 MB, tracked files 135 MB | repo | clones are slow; history holds deleted blobs |

## 2. Candidate workstreams

Effort is engineering time for one person with the plans already written; risk is the chance of breaking something users rely on.

| # | Workstream | Fixes | Effort | Impact | Risk | Prerequisite |
|---|---|---|---|---|---|---|
| **A** | **Search card redesign, phases 0–1** | relevance honesty, XSS, missing CSS, badge system, empty states, mobile layout | 0.5–1 day | **High** — the product's main surface, and the redesign you asked for | Med — changes the search API contract (`relevance_score: float \| None`) | none (plan + mockup done) |
| **B** | **Metadata repair** | 178 wrong years, 308 placeholder judges, 9 duplicate hashes, 2 dangling paths, README numbers | 0.5 day | **High** — every card shows better data; cheap | Low — SQL/data only, reversible | none |
| **C** | **Search performance** | `defer` defeat, limit-before-scoring, indexes, `/cases/stats` cache; later pgvector + FTS + RRF | 1 day (SQLite path) / 1 week (Postgres) | **High** — latency grows with rows loaded; 607 rows × 15 KB text per keystroke | Med — scoring changes can reorder results | C needs a quality harness to prove it improved |
| **D** | **Runtime configuration + serving** | `API_BASE` from `<meta>`, `serve.py` with gzip/cache + `/api` proxy, self-host CDN assets with SRI | 0.5 day | **High** — turns a localhost demo into something you can actually show or deploy | Low — additive | none |
| **E** | **Corpus completion** | 475 missing embeddings, 299 empty `full_text` | 2–3 days + compute | **High** for search quality | Med — needs a model choice and a batch job; extraction can fail per-file | decide local model vs API |
| **F** | **CI + test baseline** | lint/type/dead-code gates, runnable suite, `requirements` split | 1 day | Med — prevents regression of A–E | Low | deps must install (torch is currently required for import) |
| **G** | **Security hardening** | unused CSRF verifier, default secrets, silent SQLite fallback, CSP `unsafe-inline`, upload magic-byte checks, in-memory rate limit | 1 day | Med — matters if this ever leaves a laptop | Med — auth changes can lock people out | F (tests) ideally first |
| **H** | **Logo: build Concept A** | navbar mark, favicons, apple-touch, wordmark, `brand.html` | 2–3 h | Med — visible identity, but nothing functional | Low — additive | **your concept choice** |
| **I** | **Attribution pack** | `PROVENANCE.md` (self-reuse from `Sem-5-Project`), AI-use disclosure, `THIRD_PARTY_NOTICES.md` | 2–3 h | Med — it is what turns the audit's "97 % self-reuse" from a risk into a documented fact | Low | none |
| **J** | **Repo weight** | `.git` 115 MB → ~20 MB via `git filter-repo`; corpus to LFS or external host | 0.5 day | Low–Med — clone speed only | **High** — invalidates every existing clone; irreversible without backups | explicit sign-off |

## 3. Dependencies

```
D (serving/config) ──► makes A testable in a browser preview
A (card) ────────────► depends on B for honest metadata, on C for honest scores
B (metadata) ────────► independent, do first because it is cheap
C (performance) ─────► needs a measurement harness; benefits from E
E (embeddings) ──────► needs a model decision; makes "semantic" real
F (CI) ──────────────► locks in whatever A–E achieve; should follow the first two fixes
J ───────────────────► only with explicit approval
```

## 4. Two sensible orderings

### If the goal is "make it demo/viva-ready"

1. **D** — so it runs somewhere other than `127.0.0.1:8000`
2. **B** — real years and judges on every card, in an afternoon
3. **A** — the card redesign you asked for, now showing true data
4. **I** — attribution pack, because that is the question a reviewer will ask

### If the goal is "make it a real product"

1. **F** — get tests + lint running so changes are safe
2. **C** — fix the N+1 and limit-before-scoring; measure before/after
3. **E** — fill the 78 % embedding gap; re-measure
4. **A** → **B** → **D** → **G**

## 5. Decisions only you can make

| Decision | Options | Blocking |
|---|---|---|
| Logo concept | A "Guardian Scales" (recommended) / B "Seal & Cipher" / C "Monogram Arch" | H |
| Embeddings | local `sentence-transformers` (slow first run, no cost) vs an API (fast, costs money, needs a key) | E |
| Database | stay on SQLite (zero setup, no pgvector) vs Postgres (pgvector, FTS, the full perf plan) | C, E |
| History rewrite | yes (clone-friendly, breaks existing clones) / no (leave 115 MB) | J |

## 6. Recommended first move

**B + A together, as one PR**: repair the metadata, then ship the card that displays it. Both are cheap, both are visible, and together they fix the most obvious thing a reviewer sees — "100% Match" next to a 1961 date on a 2020 appeal. Add **D** in the same PR so it can be demonstrated in a browser rather than described.
