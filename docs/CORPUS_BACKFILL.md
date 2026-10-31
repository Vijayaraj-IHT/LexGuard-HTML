# Corpus completion — findings and tooling

**Goal:** make the corpus complete enough for search to be honest — every case with extractable text, and every case with a real vector.

Tool: [`scripts/backfill_corpus.py`](../scripts/backfill_corpus.py) (SQLite or PostgreSQL, dry-run by default).

## 1. What the corpus looks like right now

| Measure | Count | Meaning |
|---|---:|---|
| Cases | 607 | 606 published |
| `full_text` empty | 299 (49 %) | snippets and text matching have nothing to read |
| `embedding` NULL | 475 (78 %) | no vector at all |
| Embedding rows that exist | 132 | see §2 — almost none are real |
| Vectors with **zero** magnitude | 4 | all-zero arrays, cosine similarity always 0 |
| Vectors with **fewer than 360 non-zero dims** | 113 | hashed bag-of-words, not a neural embedding |
| `judge` = "Hon'ble Bench" | 308 | placeholder shown on the card |
| Duplicate `file_hash` groups | 9 | same judgment under two rows |
| Dangling `file_path` | 2 | download 404s |
| Unparseable PDF | 1 | `No /Root object! - Is this really a PDF?` (`HC_2026_CRL_A_0A6C947A_2026_0a6c947a.pdf`) |

## 2. The "semantic" search is not semantic

`EmbeddingService.generate_embedding()` loads `all-MiniLM-L6-v2`, and on **any** failure — package missing, no network, model not cached — silently returns `_deterministic_fallback_vector()`: an MD5 token-hash projection into 384 dimensions.

Evidence that the shipped vectors came from that fallback, not from MiniLM:

1. **Sparsity.** A MiniLM vector has 384 non-zero components. Of the 132 stored vectors, the median number of non-zero components is **46.5**; 113 have fewer than 360. That is exactly what token hashing produces (one bucket per distinct token).
2. **4 vectors are all zeros** — `generate_embedding("")` returns `[0.0] * 384` before the model is ever consulted.
3. **Values are rounded to 6 decimal places**, which only the fallback does (`round(x / norm, 6)`).
4. The 15 "dense" rows are long documents whose token hashes happen to cover most buckets — still hashing, not inference.

Consequence: hybrid search currently combines a lexical scorer with a **hashed bag-of-words** scorer. It behaves like a second, worse keyword index. Nothing in the UI or README says so.

**The tool refuses to reproduce this.** `embeddings` exits with instructions when `sentence-transformers` is unavailable; `--allow-fallback` is required to opt back into hashed vectors.

> This sandbox cannot download model weights (only PyPI/npm/GitHub are reachable, not huggingface.co), so the embedding backfill has to run on your machine. The text backfill did not have that constraint and was executed here.

## 3. Text backfill — executed and measured

Command (dry-run first, then `--apply`), against a copy of the shipped database:

```bash
python scripts/backfill_corpus.py text --apply --report /tmp/text_report.json
```

| Result | Value |
|---|---:|
| Candidates (empty `full_text`) | 293 after a first limited pass |
| Filled | **291 (99.3 %)** |
| Failed — corrupt PDF | 1 |
| Skipped — no resolvable file | 1 (`1ff843da…`, its `file_path` points at a PDF that is not on disk) |
| Total text added | 4.36 M characters |
| Median per document | 2,027 chars |
| Range | 401 – 112,042 chars |
| Still empty after the run | 2 (the two failures above) |
| Documents under 1,000 chars | 94 |

The 94 short documents were spot-checked and are genuinely short orders ("`WMP. No.48807 of 2026 … Ordered. 23.10.2026`"), not failed OCR. They do not need a scan pipeline; they need the metadata repair pass so their dates and judges are right.

Extraction cost: **118 seconds for 293 PDFs** (~0.4 s each, single-threaded, pdfplumber).

## 4. Running it against PostgreSQL

```bash
pip install pdfplumber psycopg2-binary sentence-transformers

# 1. text
python scripts/backfill_corpus.py text \
    --db postgresql://lexguard:lexguard123@localhost:5432/lexguard --apply

# 2. embeddings (needs model weights; downloads ~90 MB the first time)
python scripts/backfill_corpus.py embeddings \
    --db postgresql://lexguard:lexguard123@localhost:5432/lexguard --apply --batch-size 32
#    add --replace-fallback to also rewrite the 113 hashed vectors

# 3. prove it
python scripts/backfill_corpus.py verify \
    --db postgresql://lexguard:lexguard123@localhost:5432/lexguard
```

`embedding` is `Vector(384)` on PostgreSQL (`models/case.py:11`), so the tool writes `%s::vector`. After the backfill, build the index the optimisation plan calls for:

```sql
CREATE INDEX CONCURRENTLY idx_cases_embedding_hnsw
    ON cases USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
ANALYZE cases;
```

Verification queries:

```sql
-- coverage
SELECT count(*) FILTER (WHERE embedding IS NULL)                AS no_vector,
       count(*) FILTER (WHERE full_text IS NULL OR full_text = '') AS no_text,
       count(*)                                                  AS total
FROM cases;

-- a real vector is dense: expect 384 for MiniLM output
SELECT id, vector_dims(embedding) AS dims,
       (SELECT count(*) FROM unnest(embedding::real[]) x WHERE x <> 0) AS nonzero
FROM cases WHERE embedding IS NOT NULL ORDER BY nonzero LIMIT 5;
```

Anything returning `nonzero < 360` is a fallback vector again.

## 5. Notes for the embedding run

- **Text to embed.** The tool mirrors the ingestion path (`cases.py:142`): `title. summary. section_tags keyword_tags`. That keeps query-time similarity comparable to how rows were originally written. `--text-mode full_text` embeds the first 4,000 characters of the judgment instead — better recall, but then *every* row must be re-embedded, or the index mixes two distributions. Pick one and stay consistent.
- **Dimension.** `all-MiniLM-L6-v2` = 384, matching `Vector(384)` and the 384-dim fallback. Switching to a larger model means a schema migration (`vector(768)`/`vector(1024)`) and re-embedding everything.
- **Batch size.** 32 is conservative; 128 is fine on CPU with `normalize_embeddings=True`. Expect roughly 1–3 ms per case on CPU after model load.
- **Failure policy.** Any exception during `encode` is fatal for that batch — better than silently writing fallback rows. The tool commits per batch, so a crash loses at most one batch.

## 6. Still open in the corpus workstream

| Item | Why it is not done here |
|---|---|
| 475 missing embeddings | needs model weights; blocked by sandbox network policy |
| 113 hashed + 4 zero vectors | same; `--replace-fallback` rewrites them once a model is available |
| 308 placeholder judges, 178 wrong years, 9 duplicate hashes | separate metadata pass (planned workstream B), SQL-only |
| 1 corrupt PDF, 1 missing PDF, 2 dangling paths | need the source files re-fetched; both are recorded in the report output |
| 3 scripts call the removed `text_sanitizer.extract_metadata_from_pdf` (`batch_ingest_judgments.py`, `enrich_corpus_from_pdfs.py`, `standardize_and_rename_all_pdfs.py`) | `main`'s cleanup deleted that method; `backfill_corpus.py` supersedes the middle one. The other two need repointing or removal — they will raise `AttributeError` at runtime today |
