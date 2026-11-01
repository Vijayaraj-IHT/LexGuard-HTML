#!/usr/bin/env python3
"""
benchmark_search.py — Search latency & memory profiling for LexGuard (Agent 5: Perf/QA).

Measures, against the real production corpus (600+ cases):

  * COLD START  — first hybrid-search request after process start (lazy model
                  fallbacks, first SQL round-trips, connection warm-up).
  * WARM QUERIES — repeated hybrid (RRF semantic + lexical + statute) searches;
                  reports min / mean / median / p95 / max latency per query and overall.
  * MEMORY RSS  — resident set size before and after a batched run of requests,
                  plus peak RSS (ru_maxrss), to detect leaks across batches.

Latency budgets (from the task spec):
  * median < 100 ms on local SSD / SQLite
  * median <  50 ms on PostgreSQL

The script never mutates the repository database: by default it copies
backend/lexguard.db to a temp file and points DATABASE_URL at the copy.

Outputs:
  * docs/BENCHMARK_REPORT.md  — human-readable report with the verified metrics
  * stdout summary            — PASS/FAIL against the latency budgets
  * optional --json dump      — machine-readable metrics

Usage:
    python scripts/benchmark_search.py                 # full run, writes the report
    python scripts/benchmark_search.py --repeat 5 --batch 200
    python scripts/benchmark_search.py --db postgresql+psycopg2://user:pw@host/db
    python scripts/benchmark_search.py --strict        # exit 1 if a budget is exceeded
"""

import argparse
import gc
import json
import os
import platform
import resource
import shutil
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
DEFAULT_DB = BACKEND_DIR / "lexguard.db"
DEFAULT_REPORT = REPO_ROOT / "docs" / "BENCHMARK_REPORT.md"

# Representative hybrid-search workload across legal domains / intents
QUERIES = [
    "anticipatory bail under section 438 CrPC",
    "murder conviction section 302 IPC mens rea",
    "quashing of FIR section 482 CrPC",
    "dishonour of cheque section 138 NI Act",
    "habeas corpus missing person custody",
    "NDPS Act section 37 bail parity",
    '"dying declaration" admissibility evidence',
    "cruelty to wife section 498A IPC dowry",
    "succession certificate Hindu Succession Act",
    "writ of mandamus article 226 constitution",
    "regular bail after charge sheet filed",
    "land acquisition compensation fair market value",
    "medical negligence hospital liability damages",
    "cyber crime IT Act section 66 cheating online",
    "service matter pension retirement benefits",
    "income tax appeal substantial question of law",
]

SQLITE_BUDGET_MS = 100.0
POSTGRES_BUDGET_MS = 50.0


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def percentile(samples, pct):
    """Linear-interpolation percentile (pct in [0, 100])."""
    if not samples:
        return 0.0
    xs = sorted(samples)
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    frac = k - lo
    return xs[lo] + (xs[hi] - xs[lo]) * frac


def stats(samples):
    return {
        "n": len(samples),
        "min_ms": round(min(samples), 2) if samples else 0.0,
        "mean_ms": round(statistics.fmean(samples), 2) if samples else 0.0,
        "median_ms": round(statistics.median(samples), 2) if samples else 0.0,
        "p95_ms": round(percentile(samples, 95), 2) if samples else 0.0,
        "max_ms": round(max(samples), 2) if samples else 0.0,
        "stdev_ms": round(statistics.stdev(samples), 2) if len(samples) > 1 else 0.0,
    }


def rss_mb():
    """Current resident set size of this process in MiB (Linux /proc)."""
    try:
        with open("/proc/self/statm", "rb") as fh:
            pages = int(fh.read().split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE") / (1024 * 1024)
    except Exception:
        # ru_maxrss is KiB on Linux
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def peak_rss_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0  # KiB -> MiB on Linux


def db_backend_name(url):
    return "postgresql" if url.startswith("postgresql") else "sqlite"


# ---------------------------------------------------------------------------
# benchmark core
# ---------------------------------------------------------------------------

def run_benchmark(db_url, repeat, batch, limit, warmup):
    os.environ["DATABASE_URL"] = db_url
    os.environ["ENVIRONMENT"] = "development"
    os.environ.setdefault("SEED_DEMO_ACCOUNTS", "false")
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    os.chdir(BACKEND_DIR)  # mirror production cwd for relative storage paths

    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.database import SessionLocal
    from app.models.case import Case

    db = SessionLocal()
    try:
        total_cases = db.query(Case).count()
        published_cases = db.query(Case).filter(Case.status == "published").count()
    finally:
        db.close()

    results = {
        "db_url_kind": db_backend_name(db_url),
        "total_cases": total_cases,
        "published_cases": published_cases,
    }

    client = TestClient(app)
    with client:
        search_url = "/api/v1/search/"

        def timed_search(query):
            t0 = time.perf_counter()
            r = client.post(search_url, json={"query": query, "limit": limit})
            dt_ms = (time.perf_counter() - t0) * 1000.0
            assert r.status_code == 200, f"search failed for {query!r}: {r.status_code} {r.text[:200]}"
            return dt_ms, r.json().get("total", 0)

        # ---- cold start (very first request; includes lazy init) ----
        cold_ms, cold_total = timed_search(QUERIES[0])
        results["cold_start_ms"] = round(cold_ms, 2)
        results["cold_start_total"] = cold_total

        # ---- warm-up (not measured) ----
        for q in QUERIES[:warmup]:
            timed_search(q)

        # ---- measured warm queries ----
        per_query = []
        all_samples = []
        for q in QUERIES:
            samples = []
            totals = set()
            for _ in range(repeat):
                ms, total = timed_search(q)
                samples.append(ms)
                totals.add(total)
            per_query.append({"query": q, "total": sorted(totals)[-1], **stats(samples)})
            all_samples.extend(samples)

        results["per_query"] = per_query
        results["warm"] = stats(all_samples)
        results["warm_samples_ms"] = [round(x, 2) for x in all_samples]

        # ---- memory: RSS before/after a batched run ----
        gc.collect()
        rss_before = rss_mb()
        peak_before = peak_rss_mb()
        batch_samples = []
        for i in range(batch):
            ms, _ = timed_search(QUERIES[i % len(QUERIES)])
            batch_samples.append(ms)
        gc.collect()
        rss_after = rss_mb()
        peak_after = peak_rss_mb()
        results["memory"] = {
            "rss_before_mb": round(rss_before, 2),
            "rss_after_mb": round(rss_after, 2),
            "rss_delta_mb": round(rss_after - rss_before, 2),
            "peak_rss_before_mb": round(peak_before, 2),
            "peak_rss_after_mb": round(peak_after, 2),
            "batch_requests": batch,
            "batch_median_ms": round(statistics.median(batch_samples), 2) if batch_samples else 0.0,
        }

    return results


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def write_report(results, report_path, strict):
    backend = results["db_url_kind"]
    budget = POSTGRES_BUDGET_MS if backend == "postgresql" else SQLITE_BUDGET_MS
    median = results["warm"]["median_ms"]
    verdict = "PASS" if median < budget else "FAIL"
    cold = results["cold_start_ms"]
    mem = results["memory"]
    warm = results["warm"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = []
    lines.append("# LexGuard — Search Latency & Memory Benchmark Report")
    lines.append("")
    lines.append(f"- **Generated:** {now}")
    lines.append(f"- **Generator:** `scripts/benchmark_search.py` (Agent 5 — Performance, Test & QA)")
    lines.append(f"- **Verdict:** **{verdict}** — warm median {median} ms vs budget < {budget:.0f} ms ({backend})")
    lines.append("")
    lines.append("## 1. Environment (verified on the machine that produced this report)")
    lines.append("")
    lines.append("| Property | Value |")
    lines.append("|---|---|")
    lines.append(f"| Date (UTC) | {now} |")
    lines.append(f"| Platform | {platform.platform()} |")
    lines.append(f"| Machine | {platform.machine()} |")
    lines.append(f"| Python | {platform.python_version()} |")
    lines.append(f"| CPUs | {os.cpu_count()} |")
    lines.append(f"| Database backend | {backend} (`DATABASE_URL` scheme) |")
    lines.append(f"| Corpus | {results['total_cases']} cases total, {results['published_cases']} published (searchable) |")
    try:
        import sentence_transformers  # noqa: F401
        emb = "sentence-transformers/all-MiniLM-L6-v2 (live model)"
    except Exception:
        emb = "deterministic 384-dim fallback vectorizer (sentence-transformers not installed)"
    lines.append(f"| Embedding engine | {emb} |")
    lines.append(f"| Transport | FastAPI `TestClient` (in-process ASGI, no network hop) |")
    lines.append("")
    lines.append("## 2. Methodology")
    lines.append("")
    lines.append("1. `backend/lexguard.db` is copied to a temp file (repository DB is never mutated); "
                 "`DATABASE_URL` points at the copy.")
    lines.append("2. **Cold start** = first `POST /api/v1/search/` after process start "
                 "(lazy embedding/LLM fallback init + first SQL round-trips).")
    lines.append(f"3. **Warm queries** = {len(QUERIES)} representative hybrid queries x "
                 f"{results['warm']['n'] // len(QUERIES)} repeats each; each request is timed with "
                 "`time.perf_counter()` around the full request/response cycle (`limit=10`).")
    lines.append(f"4. **Memory** = RSS read from `/proc/self/statm` before and after a batch of "
                 f"{mem['batch_requests']} back-to-back search requests; peak RSS from `ru_maxrss`.")
    lines.append("5. Latency budgets: median < 100 ms on local SSD/SQLite, < 50 ms on PostgreSQL.")
    lines.append("")
    lines.append("## 3. Verified latency metrics")
    lines.append("")
    lines.append("### 3.1 Cold start vs warm")
    lines.append("")
    lines.append("| Metric | Latency (ms) | Results returned |")
    lines.append("|---|---|---|")
    lines.append(f"| Cold start (first query) | **{cold}** | {results['cold_start_total']} |")
    lines.append(f"| Warm median | **{warm['median_ms']}** | — |")
    lines.append(f"| Warm mean | {warm['mean_ms']} | — |")
    lines.append(f"| Warm p95 | {warm['p95_ms']} | — |")
    lines.append(f"| Warm max | {warm['max_ms']} | — |")
    lines.append(f"| Warm min | {warm['min_ms']} | — |")
    lines.append(f"| Std dev | {warm['stdev_ms']} | — |")
    lines.append(f"| Samples | {warm['n']} | — |")
    lines.append("")
    lines.append("### 3.2 Per-query warm latency")
    lines.append("")
    lines.append("| # | Query | Hits (total) | Median ms | Mean ms | p95 ms | Max ms |")
    lines.append("|---|---|---|---|---|---|---|")
    for i, q in enumerate(results["per_query"], 1):
        lines.append(f"| {i} | `{q['query']}` | {q['total']} | {q['median_ms']} | {q['mean_ms']} | {q['p95_ms']} | {q['max_ms']} |")
    lines.append("")
    lines.append("### 3.3 Memory (RSS) before/after batched requests")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---|")
    lines.append(f"| RSS before batch | {mem['rss_before_mb']} MiB |")
    lines.append(f"| RSS after {mem['batch_requests']} requests | {mem['rss_after_mb']} MiB |")
    lines.append(f"| RSS delta | **{mem['rss_delta_mb']} MiB** |")
    lines.append(f"| Peak RSS before | {mem['peak_rss_before_mb']} MiB |")
    lines.append(f"| Peak RSS after | {mem['peak_rss_after_mb']} MiB |")
    lines.append(f"| Batch median latency | {mem['batch_median_ms']} ms |")
    lines.append("")
    leak_note = ("no leak detected (delta within noise)" if mem["rss_delta_mb"] < 50
                 else "delta > 50 MiB — investigate per-request retention")
    lines.append(f"Memory interpretation: {leak_note}.")
    lines.append("")
    lines.append("## 4. Budget check")
    lines.append("")
    lines.append("| Budget | Threshold | Measured median | Verdict |")
    lines.append("|---|---|---|---|")
    lines.append(f"| {'PostgreSQL' if backend == 'postgresql' else 'SQLite (local SSD)'} median search latency "
                 f"| < {budget:.0f} ms | {median} ms | **{verdict}** |")
    if backend == "sqlite":
        lines.append(f"| PostgreSQL median search latency (reference, requires PG) | < {POSTGRES_BUDGET_MS:.0f} ms | not measured here | N/A |")
    lines.append("")
    lines.append("## 5. Notes")
    lines.append("")
    lines.append("- Hybrid search = Reciprocal Rank Fusion over dense vector similarity, lexical/boolean "
                 "keyword hits, and statutory section/act alignment, over all published cases.")
    lines.append("- The corpus contains 600+ cases; every query scans the full published set, so these "
                 "numbers are worst-case full-corpus hybrid search latencies.")
    lines.append("- Empty-query browse (`match_type=browse`) takes the indexed fast path and is not part "
                 "of the timed set above.")
    lines.append("- Regenerate with: `python scripts/benchmark_search.py` (add `--strict` to exit non-zero "
                 "when the budget is exceeded).")
    lines.append("")

    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return verdict, budget


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=None,
                    help="DATABASE_URL to benchmark (default: temp copy of backend/lexguard.db)")
    ap.add_argument("--repeat", type=int, default=3, help="repeats per query (default 3)")
    ap.add_argument("--batch", type=int, default=100, help="batched requests for the memory delta (default 100)")
    ap.add_argument("--warmup", type=int, default=2, help="unmeasured warm-up queries (default 2)")
    ap.add_argument("--limit", type=int, default=10, help="search result limit per request (default 10)")
    ap.add_argument("--report", default=str(DEFAULT_REPORT), help="markdown report path")
    ap.add_argument("--json", default=None, help="optional path for a JSON dump of raw metrics")
    ap.add_argument("--strict", action="store_true", help="exit 1 when the latency budget is exceeded")
    args = ap.parse_args()

    tmp_db = None
    if args.db:
        db_url = args.db
    else:
        if not DEFAULT_DB.exists():
            sys.exit(f"corpus database not found: {DEFAULT_DB} (pass --db)")
        tmp_db = os.path.join(tempfile.mkdtemp(prefix="lexguard_bench_"), "lexguard_bench.db")
        shutil.copy2(DEFAULT_DB, tmp_db)
        db_url = f"sqlite:///{tmp_db}"

    print(f"[benchmark] backend={db_backend_name(db_url)} corpus={DEFAULT_DB if not args.db else args.db}")
    print(f"[benchmark] queries={len(QUERIES)} repeat={args.repeat} batch={args.batch} limit={args.limit}")

    t0 = time.perf_counter()
    results = run_benchmark(db_url, args.repeat, args.batch, args.limit, args.warmup)
    elapsed = time.perf_counter() - t0

    verdict, budget = write_report(results, args.report, args.strict)

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")

    warm = results["warm"]
    mem = results["memory"]
    print()
    print("=== LexGuard search benchmark (verified metrics) ===")
    print(f"  corpus            : {results['published_cases']} published / {results['total_cases']} total cases")
    print(f"  db backend        : {results['db_url_kind']}")
    print(f"  cold start        : {results['cold_start_ms']} ms")
    print(f"  warm median       : {warm['median_ms']} ms  (budget < {budget:.0f} ms -> {verdict})")
    print(f"  warm mean/p95/max : {warm['mean_ms']} / {warm['p95_ms']} / {warm['max_ms']} ms  (n={warm['n']})")
    print(f"  RSS before/after  : {mem['rss_before_mb']} -> {mem['rss_after_mb']} MiB (delta {mem['rss_delta_mb']} MiB, "
          f"peak {mem['peak_rss_after_mb']} MiB over {mem['batch_requests']} batched requests)")
    print(f"  report            : {args.report}")
    print(f"  wall time         : {elapsed:.1f}s")
    print(f"  VERDICT           : {verdict}")

    if tmp_db:
        shutil.rmtree(os.path.dirname(tmp_db), ignore_errors=True)

    if args.strict and verdict == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
