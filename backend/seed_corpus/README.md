# Lexguard Seed Corpus

**29 Indian High Court judgments/orders** acquired from the shared Google Drive folder
[`1SUvTnpN6EbhO9nDR_EVJPMjNt5dJHZGu`](https://drive.google.com/drive/folders/1SUvTnpN6EbhO9nDR_EVJPMjNt5dJHZGu)
and prepared as a seed dataset for the Lexguard platform.

| File | Purpose |
|---|---|
| `manifest.json` | Curated metadata for every PDF: case number, title, court, year, decision date, judge, parties, case type, act/section/keyword tags, summary, outcome — plus SHA-256 hash, byte size and Drive file ID (fields align with the `Case` SQLAlchemy model / upload API) |
| `ANALYSIS.md` | Corpus analysis: court & subject distribution, statute coverage, data-quality findings, mapping to Lexguard features |
| `seed_corpus.py` | Loader that verifies hashes and uploads everything through `/api/v1/cases/upload` |
| `pdfs/` | The 29 PDFs with deduplicated case-number filenames (**git-ignored**, 7.3 MiB; source of truth is the Drive folder) |

## Quick start

```bash
# 1. Integrity only (no server needed)
python backend/seed_corpus/seed_corpus.py --verify-only

# 2. Start the backend (see backend/README.md), then seed it
export LEXGUARD_EMAIL="your-court-staff-email@example.com"
export LEXGUARD_PASSWORD="..."
python backend/seed_corpus/seed_corpus.py --approve          # upload + publish
python backend/seed_corpus/seed_corpus.py --limit 3          # smoke test first
```

- Re-uploading an already-seeded PDF returns **HTTP 409 duplicate** (the SHA-256 dedupe in action) and is reported as such, not an error.
- Use a `court_staff` or `senior_staff` account: the upload and approve endpoints enforce RBAC.

## Integrity

`manifest.json` stores the SHA-256 of every file at acquisition time (2026-10-12).
`--verify-only` recomputes and compares them — the same operation Lexguard's
document verification endpoint performs — and exits non-zero on any mismatch.
