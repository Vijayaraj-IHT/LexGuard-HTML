# LexGuard — Search Latency & Memory Benchmark Report

- **Generated:** 2026-11-01 08:55:48 UTC
- **Generator:** `scripts/benchmark_search.py` (Agent 5 — Performance, Test & QA)
- **Verdict:** **FAIL** — warm median 273.18 ms vs budget < 100 ms (sqlite)

## 1. Environment (verified on the machine that produced this report)

| Property | Value |
|---|---|
| Date (UTC) | 2026-11-01 08:55:48 UTC |
| Platform | Linux-6.1.158+-x86_64-with-glibc2.36 |
| Machine | x86_64 |
| Python | 3.11.2 |
| CPUs | 2 |
| Database backend | sqlite (`DATABASE_URL` scheme) |
| Corpus | 607 cases total, 606 published (searchable) |
| Embedding engine | deterministic 384-dim fallback vectorizer (sentence-transformers not installed) |
| Transport | FastAPI `TestClient` (in-process ASGI, no network hop) |

## 2. Methodology

1. `backend/lexguard.db` is copied to a temp file (repository DB is never mutated); `DATABASE_URL` points at the copy.
2. **Cold start** = first `POST /api/v1/search/` after process start (lazy embedding/LLM fallback init + first SQL round-trips).
3. **Warm queries** = 16 representative hybrid queries x 3 repeats each; each request is timed with `time.perf_counter()` around the full request/response cycle (`limit=10`).
4. **Memory** = RSS read from `/proc/self/statm` before and after a batch of 100 back-to-back search requests; peak RSS from `ru_maxrss`.
5. Latency budgets: median < 100 ms on local SSD/SQLite, < 50 ms on PostgreSQL.

## 3. Verified latency metrics

### 3.1 Cold start vs warm

| Metric | Latency (ms) | Results returned |
|---|---|---|
| Cold start (first query) | **417.77** | 606 |
| Warm median | **273.18** | — |
| Warm mean | 288.62 | — |
| Warm p95 | 341.41 | — |
| Warm max | 360.63 | — |
| Warm min | 233.62 | — |
| Std dev | 34.23 | — |
| Samples | 48 | — |

### 3.2 Per-query warm latency

| # | Query | Hits (total) | Median ms | Mean ms | p95 ms | Max ms |
|---|---|---|---|---|---|---|
| 1 | `anticipatory bail under section 438 CrPC` | 606 | 264.48 | 294.43 | 346.63 | 355.76 |
| 2 | `murder conviction section 302 IPC mens rea` | 606 | 273.79 | 276.5 | 282.19 | 283.12 |
| 3 | `quashing of FIR section 482 CrPC` | 606 | 322.86 | 305.74 | 325.24 | 325.5 |
| 4 | `dishonour of cheque section 138 NI Act` | 606 | 269.33 | 283.7 | 312.81 | 317.65 |
| 5 | `habeas corpus missing person custody` | 606 | 256.24 | 269.8 | 297.28 | 301.84 |
| 6 | `NDPS Act section 37 bail parity` | 606 | 268.96 | 286.93 | 323.57 | 329.64 |
| 7 | `"dying declaration" admissibility evidence` | 1 | 239.67 | 238.28 | 241.36 | 241.55 |
| 8 | `cruelty to wife section 498A IPC dowry` | 606 | 260.97 | 281.17 | 315.73 | 321.82 |
| 9 | `succession certificate Hindu Succession Act` | 606 | 262.56 | 285.75 | 328.22 | 335.52 |
| 10 | `writ of mandamus article 226 constitution` | 606 | 268.31 | 287.03 | 331.84 | 338.9 |
| 11 | `regular bail after charge sheet filed` | 606 | 270.93 | 289.38 | 323.54 | 329.39 |
| 12 | `land acquisition compensation fair market value` | 606 | 265.71 | 286.56 | 328.93 | 335.95 |
| 13 | `medical negligence hospital liability damages` | 606 | 282.4 | 300.54 | 332.67 | 338.25 |
| 14 | `cyber crime IT Act section 66 cheating online` | 606 | 306.5 | 310.03 | 327.04 | 329.32 |
| 15 | `service matter pension retirement benefits` | 606 | 288.3 | 304.04 | 353.4 | 360.63 |
| 16 | `income tax appeal substantial question of law` | 606 | 321.28 | 318.09 | 340.61 | 342.76 |

### 3.3 Memory (RSS) before/after batched requests

| Metric | Value |
|---|---|
| RSS before batch | 107.52 MiB |
| RSS after 100 requests | 107.52 MiB |
| RSS delta | **0.0 MiB** |
| Peak RSS before | 107.52 MiB |
| Peak RSS after | 107.52 MiB |
| Batch median latency | 279.42 ms |

Memory interpretation: no leak detected (delta within noise).

## 4. Budget check

| Budget | Threshold | Measured median | Verdict |
|---|---|---|---|
| SQLite (local SSD) median search latency | < 100 ms | 273.18 ms | **FAIL** |
| PostgreSQL median search latency (reference, requires PG) | < 50 ms | not measured here | N/A |

## 5. Notes

- Hybrid search = Reciprocal Rank Fusion over dense vector similarity, lexical/boolean keyword hits, and statutory section/act alignment, over all published cases.
- The corpus contains 600+ cases; every query scans the full published set, so these numbers are worst-case full-corpus hybrid search latencies.
- Empty-query browse (`match_type=browse`) takes the indexed fast path and is not part of the timed set above.
- Regenerate with: `python scripts/benchmark_search.py` (add `--strict` to exit non-zero when the budget is exceeded).
