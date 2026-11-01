# LexGuard — Documentation Index

Planning and audit documents produced for the project. Start with the search-card plan if you are working on the UI; start with the audit if you need the project-wide picture.

> **Repository state.** The analysis below was made at commit `8d240fc`. `main` has since moved to `1b2068e` (*fix(search): resolve JSONDecodeError…*, 2026-11-01), which:
> - cleaned the 6 malformed JSON cells and re-synced `database/database_dump.sql` (verified: 0 malformed rows today);
> - added a `safe_json_deserializer` to the SQLite engine (`backend/app/core/database.py`);
> - added an XHR abort guard in `frontend/js/pages/search.js` (line 127), so cancelled searches no longer flash an error banner;
> - added `scripts/verify_users.py` (one-off suite is now 39 Python scripts).
>
> Everything else in these documents still holds. Items already resolved are marked with a *Status* note where they appear.

| Document | What it answers |
|---|---|
| [`../PROJECT_AUDIT.md`](../PROJECT_AUDIT.md) | Full project overview + plagiarism/originality audit, defect list, remediation plan, reproduction commands |
| [`SEARCH_CARD_REDESIGN.md`](SEARCH_CARD_REDESIGN.md) | Code walk-through of the hybrid-search result card, every defect with evidence, proposed markup/CSS/JS, backend contract changes, phased rollout, acceptance criteria |
| [`search-card-mockup.html`](search-card-mockup.html) | Visual comparison: current card vs proposed card vs verified/mobile variants (self-contained, open in any browser) |
| [`CORPUS_BACKFILL.md`](CORPUS_BACKFILL.md) | Measured corpus gaps, proof that the stored vectors are hashed fallbacks rather than MiniLM, the text backfill result (291/293 PDFs), and the PostgreSQL runbook |
| [`NEXT_STEPS.md`](NEXT_STEPS.md) | Verified state of the repo today, nine candidate workstreams with effort/impact/risk, dependency order, and the four decisions that need your call |
| [`CLEANUP_LOG.md`](CLEANUP_LOG.md) | What was actually removed (237 files / 72.2 MB), the evidence for each deletion, the three claims that re-verification corrected, and what Git history still holds |
| [`DEAD_CODE_REPORT.md`](DEAD_CODE_REPORT.md) | Every unused/duplicate/dead item with evidence, probable purpose, and delete/keep/archive decision + cleanup commands |
| [`OPTIMISATION_PLAN.md`](OPTIMISATION_PLAN.md) | Directory-by-directory optimisation: repo/storage, backend, database, frontend delivery, corpus, security, CI, measurable targets, sequencing |
| [`LOGO_DESIGN_BRIEF.md`](LOGO_DESIGN_BRIEF.md) | Brand audit, three concepts, recommended master mark with SVG source, palette/contrast, lockup rules, integration checklist |
| [`audit_evidence/cross_repo_duplication.csv`](audit_evidence/cross_repo_duplication.csv) | 158 files shared with `Vijayaraj-IHT/Sem-5-Project`, similarity ratios |
| [`audit_evidence/internal_clones.csv`](audit_evidence/internal_clones.csv) | 123 internal clone pairs (`jscpd`) with line ranges and token counts |

## Headline numbers

- **Duplication with the author's earlier repo:** 121 byte-identical + 31 near-identical files → 97.1 % of 42,799 overlapping lines.
- **Internal duplication:** 6.94 % of lines (HTML 22.3 %), 123 clone pairs.
- **Dead code:** 0 unused JS definitions outside the API layer, but 10 unused API wrappers, 6 real unused Python functions, 14 unused `LG.*` members, 14 unused CSS selectors/variables, 4 undefined CSS classes in use.
- **Reclaimable disk:** ≈ 75 MB of 299 MB (duplicate PDFs, unused Mermaid bundle, screenshots archive, docx archive, staging PDFs, stale dump).
- **Blocking bugs:** f-string syntax (`bookmarks.py:247`, Python 3.12 only) and the hard-coded `http://127.0.0.1:8000`. The 6 malformed JSON rows were fixed on `main` after this analysis.

## Suggested order of work

1. `SEARCH_CARD_REDESIGN.md` §7 — five-step hotfix (data honesty + escaping + missing CSS).
2. `DEAD_CODE_REPORT.md` §11 — zero-risk deletions and out-of-Git corpus move.
3. `OPTIMISATION_PLAN.md` §8 — Day 1 → Week 3 sequencing.
4. `LOGO_DESIGN_BRIEF.md` §7 — pick a concept, then generate the SVG masters.
