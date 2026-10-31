#!/usr/bin/env python3
"""
Corpus-wide case-file pattern analysis.

Runs the deterministic pattern engine (``app.services.case_pattern_service``)
over a directory of judgment/order PDFs and produces:

* a machine-readable JSON report (profile per file, key coverage, layout
  fingerprint, facts extraction result),
* a Markdown summary suitable for review,
* a console table so an operator can eyeball misclassifications immediately.

The analysis is deduplicated by SHA-256: re-downloaded copies of the same
judgment (the corpus has many, because JUDIS exports are hash-named) collapse
into a single record.

Usage
-----
    python scripts/analyse_case_file_patterns.py \
        --dirs backend/seed_corpus/pdfs backend/incoming_cases \
        --out docs/pattern_analysis

    # only the summary
    python scripts/analyse_case_file_patterns.py --dirs backend/incoming_cases --quiet
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))


def _load_service():
    """Import the pattern service without importing the whole FastAPI app."""
    import importlib.util

    module_path = os.path.join(REPO_ROOT, "backend", "app", "services", "case_pattern_service.py")
    spec = importlib.util.spec_from_file_location("lexguard_case_pattern_service", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses need the module registered
    spec.loader.exec_module(module)
    return module


def sha256_of(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_pdfs(dirs, recursive: bool = True):
    found = []
    for directory in dirs:
        path = os.path.abspath(directory)
        if not os.path.isdir(path):
            print(f"  ! skipping missing directory: {directory}", file=sys.stderr)
            continue
        if recursive:
            for root, _dirs, files in os.walk(path):
                for name in files:
                    if name.lower().endswith(".pdf"):
                        found.append(os.path.join(root, name))
        else:
            for name in os.listdir(path):
                if name.lower().endswith(".pdf"):
                    found.append(os.path.join(path, name))
    return sorted(found)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyse case-file drafting patterns across a PDF corpus")
    parser.add_argument(
        "--dirs", nargs="+", default=[os.path.join(REPO_ROOT, "storage", "cases")],
        help="directories containing judgment PDFs (default: storage/cases, the full corpus)")
    parser.add_argument("--out", default="docs/pattern_analysis", help="output directory for JSON/Markdown")
    parser.add_argument("--no-recursive", action="store_true", help="do not descend into subdirectories")
    parser.add_argument("--quiet", action="store_true", help="suppress the per-file table")
    args = parser.parse_args()

    svc = _load_service()
    files = collect_pdfs(args.dirs, recursive=not args.no_recursive)
    if not files:
        print("No PDFs found.", file=sys.stderr)
        return 1

    seen_hashes: dict[str, str] = {}
    records = []
    duplicates = []
    failures = []

    print(f"Scanning {len(files)} PDF(s)…\n")
    for index, path in enumerate(files, start=1):
        name = os.path.basename(path)
        try:
            digest = sha256_of(path)
            if digest in seen_hashes:
                duplicates.append({"file": name, "duplicate_of": seen_hashes[digest]})
                continue
            seen_hashes[digest] = name
            report = svc.CasePatternService.analyse_pdf(path)
            # keep the JSON reviewable: key sets are summarised as ids, not anchors
            report["keys_found"] = sorted(
                f"{category}.{hit['key']}"
                for category, hits in report.pop("key_hits", {}).items()
                for hit in hits
            )
            report["sha256"] = digest
            report["directory"] = os.path.basename(os.path.dirname(path))
            records.append(report)
            if not args.quiet:
                profile = report["profile"]
                cov = report["key_coverage"]
                print(
                    f"[{index:>3}/{len(files)}] {name[:52]:<54} "
                    f"{profile['profile_id']:<26} conf={profile['confidence']:.2f} "
                    f"keys={cov['found']}/{cov['declared']} "
                    f"facts={report['facts']['length']:>5} chars ({report['facts']['strategy']})"
                )
        except Exception as exc:  # keep going: one bad PDF must not stop the sweep
            failures.append({"file": name, "error": f"{type(exc).__name__}: {exc}"})
            print(f"[{index:>3}/{len(files)}] {name[:52]:<54} FAILED — {exc}", file=sys.stderr)

    # ── aggregate ──────────────────────────────────────────────────────────
    profile_counts = Counter(r["profile"]["profile_id"] for r in records)
    strategy_counts = Counter(r["facts"]["strategy"] for r in records)
    layout_counts = Counter(sig for r in records for sig in r["layout"]["layout_signals"])
    quality_counts = Counter(r["profile"]["text_quality"] for r in records)
    text_status_counts = Counter(r.get("text_status", "ok") for r in records)

    by_profile = defaultdict(list)
    for record in records:
        by_profile[record["profile"]["profile_id"]].append(record)

    profile_summary = {}
    for profile_id, group in by_profile.items():
        catalogue = next((p for p in svc.profile_catalog() if p["id"] == profile_id), {})
        coverages = [g["key_coverage"]["ratio"] for g in group]
        fact_lengths = [g["facts"]["length"] for g in group]
        profile_summary[profile_id] = {
            "label": catalogue.get("label", profile_id),
            "court": catalogue.get("court"),
            "seat": catalogue.get("seat"),
            "facts_strategy": catalogue.get("facts_strategy"),
            "key_set": catalogue.get("key_set"),
            "key_set_ids": group[0]["profile"].get("key_set_ids") or [group[0]["profile"]["key_set_id"]],
            "courts": dict(Counter(g["profile"]["court"] for g in group).most_common()),
            "documents": len(group),
            "mean_key_coverage": round(sum(coverages) / len(coverages), 3),
            "mean_facts_chars": round(sum(fact_lengths) / len(fact_lengths), 1) if fact_lengths else 0,
            "examples": [g["file"] for g in group[:3]],
            "layout_signals": dict(Counter(s for g in group for s in g["layout"]["layout_signals"])),
            "pages_range": [
                min(g["layout"]["page_count"] for g in group),
                max(g["layout"]["page_count"] for g in group),
            ],
        }

    # key-hit frequency tells us which anchors actually earn their place
    key_hit_counts = Counter()
    key_declared = Counter()
    for record in records:
        keyset = svc.CasePatternService.key_set_for(record["profile"]["profile_id"])
        for category, keys in keyset.items():
            key_declared[category] += len(keys)
        for key in record.get("keys_found", []):
            key_hit_counts[key] += 1

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "directories": args.dirs,
        "pdfs_scanned": len(files),
        "unique_documents": len(records),
        "duplicates_skipped": len(duplicates),
        "failures": len(failures),
        "profiles": profile_summary,
        "profile_counts": dict(profile_counts),
        "facts_strategies": dict(strategy_counts),
        "layout_signals": dict(layout_counts),
        "text_quality": dict(quality_counts),
        "text_status": dict(text_status_counts),
        "insufficient_text": [r["file"] for r in records if r.get("text_status") == "insufficient_text"],
        "key_hit_frequency": dict(key_hit_counts.most_common()),
        "key_declared_by_category": dict(key_declared),
        "duplicates": duplicates,
        "errors": failures,
    }

    os.makedirs(args.out, exist_ok=True)
    json_path = os.path.join(args.out, "case_pattern_report.json")
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump({"summary": summary, "documents": records}, handle, indent=2, ensure_ascii=False)

    markdown = render_markdown(summary, records, svc)
    md_path = os.path.join(args.out, "case_pattern_report.md")
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write(markdown)

    print("\n" + "=" * 96)
    for profile_id, count in profile_counts.most_common():
        info = profile_summary[profile_id]
        print(f"  {profile_id:<28} {count:>3} doc(s)   key coverage {info['mean_key_coverage']:.2f}   "
              f"facts ~{info['mean_facts_chars']:.0f} chars")
    print("=" * 96)
    print(f"  duplicates skipped : {len(duplicates)}")
    print(f"  failures           : {len(failures)}")
    print(f"  JSON  -> {json_path}")
    print(f"  MD    -> {md_path}")
    return 0 if not failures else 2


def render_markdown(summary, records, svc) -> str:
    lines = []
    add = lines.append
    add("# Case-file pattern analysis")
    add("")
    add(f"Generated: `{summary['generated_at']}`")
    add("")
    add(f"- Directories scanned: {', '.join('`%s`' % d for d in summary['directories'])}")
    add(f"- PDFs scanned: **{summary['pdfs_scanned']}** · unique documents: **{summary['unique_documents']}** "
        f"· duplicates skipped: {summary['duplicates_skipped']} · failures: {summary['failures']}")
    add("")

    unique = summary["unique_documents"]
    generic = summary["profile_counts"].get("GENERIC-HC", 0)
    bodyless = summary["text_status"].get("insufficient_text", 0)
    add(f"- Profile cover: **{unique - generic}/{unique}** documents matched a specific registry/format "
        f"profile — generic fallback: **{generic}** ({(100 * generic / unique) if unique else 0:.1f} %)")
    add(f"- Cover-page-only PDFs (caption + CNR, no body): **{bodyless}**")
    add("")

    add("## 1. Detected drafting profiles")
    add("")
    add("| Profile | Documents | Mean key coverage | Mean facts length | Pages | Example |")
    add("|---|---:|---:|---:|---|---|")
    for profile_id, info in sorted(summary["profiles"].items(), key=lambda kv: -kv[1]["documents"]):
        pages = info["pages_range"]
        add(f"| `{profile_id}` — {info['label']} | {info['documents']} | {info['mean_key_coverage']:.2f} | "
            f"{info['mean_facts_chars']:.0f} | {pages[0]}–{pages[1]} | `{info['examples'][0]}` |")
    add("")

    add("## 2. Facts-extraction strategy used")
    add("")
    add("| Strategy | Documents |")
    add("|---|---:|")
    for strategy, count in sorted(summary["facts_strategies"].items(), key=lambda kv: -kv[1]):
        add(f"| `{strategy}` | {count} |")
    add("")

    add("## 3. Layout signals")
    add("")
    add("| Signal | Documents | Meaning |")
    add("|---|---:|---|")
    for signal, count in sorted(summary["layout_signals"].items(), key=lambda kv: -kv[1]):
        add(f"| `{signal}` | {count} | {svc.LAYOUT_SIGNALS.get(signal, '—')} |")
    add("")

    add("## 4. Text-layer quality")
    add("")
    add("| Quality | Documents |")
    add("|---|---:|")
    for quality, count in sorted(summary["text_quality"].items(), key=lambda kv: -kv[1]):
        add(f"| `{quality}` | {count} |")
    add("")

    add("## 5. Key sets — which anchors fire")
    add("")
    add("Declared keys per category:")
    add("")
    add("| Category | Keys declared | Hit documents |")
    add("|---|---:|---:|")
    for category, declared in sorted(summary["key_declared_by_category"].items()):
        hits = sum(v for k, v in summary["key_hit_frequency"].items() if k.startswith(category + "."))
        add(f"| `{category}` | {declared} | {hits} |")
    add("")
    add("Top individual keys (documents in which the anchor matched):")
    add("")
    add("| Key | Documents |")
    add("|---|---:|")
    for key, count in list(summary["key_hit_frequency"].items())[:30]:
        add(f"| `{key}` | {count} |")
    add("")

    add("## 5b. Key-set composition")
    add("")
    add("Court profiles compose a shared key set with a small registry extra set, so an")
    add("anchor added for one registry never leaks into another:")
    add("")
    add("| Profile | Key sets | Documents |")
    add("|---|---|---:|")
    for profile_id, info in sorted(summary["profiles"].items(), key=lambda kv: -kv[1]["documents"]):
        sets = ", ".join(f"`{sid}`" for sid in info.get("key_set_ids", []))
        add(f"| `{profile_id}` | {sets} | {info['documents']} |")
    add("")

    if summary.get("insufficient_text"):
        add("## 5c. Cover-page-only documents (no extractable body)")
        add("")
        for name in summary["insufficient_text"]:
            add(f"- `{name}`")
        add("")

    add("## 6. Per-document results")
    add("")
    add("| File | Profile | Conf. | Keys | Facts | Layout |")
    add("|---|---|---:|---|---:|---|")
    for record in records:
        layout = ", ".join(s.replace("layout:", "") for s in record["layout"]["layout_signals"]) or "—"
        add(f"| `{record['file']}` | `{record['profile']['profile_id']}` | {record['profile']['confidence']:.2f} | "
            f"{record['key_coverage']['found']}/{record['key_coverage']['declared']} | "
            f"{record['facts']['length']} | {layout} |")
    add("")
    if summary["errors"]:
        add("## Failures")
        add("")
        for err in summary["errors"]:
            add(f"- `{err['file']}` — {err['error']}")
        add("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
