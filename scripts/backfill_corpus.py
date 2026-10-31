#!/usr/bin/env python3
"""
backfill_corpus.py — fill the gaps in the case corpus.

Two independent jobs, because they have different dependency and compute profiles:

  text        extract `full_text` from the judgment PDFs (pdfplumber, seconds per file)
  embeddings  compute real 384-dim vectors with sentence-transformers (needs model weights)
  verify      report coverage and detect fake/empty vectors

Works against SQLite (default: backend/lexguard.db) or PostgreSQL (--db postgresql://...).
Every job is a dry run unless --apply is passed.

Examples
--------
    python scripts/backfill_corpus.py verify
    python scripts/backfill_corpus.py text --apply --report /tmp/text.json
    python scripts/backfill_corpus.py embeddings --db postgresql://lexguard:lexguard123@localhost:5432/lexguard --apply
    python scripts/backfill_corpus.py embeddings --replace-fallback --apply     # redo hashed vectors

Why embeddings refuse to run without a model: `EmbeddingService.generate_embedding()`
silently falls back to an MD5 token-hashing vectoriser when sentence-transformers is
missing. Those vectors are *not* semantic (they are a hashed bag of words), and the
shipped database is full of them. Writing more of them would hide the problem, so this
tool exits with an explanation instead. Pass --allow-fallback only if you consciously
want that behaviour.
"""
import argparse
import json
import os
import re
import statistics
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))

DEFAULT_SQLITE = os.path.join(ROOT, "backend", "lexguard.db")
DIM = 384
EMBED_TEXT_FIELDS = ("title", "summary", "section_tags", "keyword_tags")


# --------------------------------------------------------------------------- db
class DB:
    """Minimal adapter: sqlite3 or psycopg2, same small surface for this script."""

    def __init__(self, dsn: str):
        self.is_pg = dsn.startswith(("postgres://", "postgresql://"))
        if self.is_pg:
            import psycopg2
            import psycopg2.extras

            self.conn = psycopg2.connect(dsn)
            self.conn.autocommit = False
            self.cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            self.ph = "%s"
        else:
            import sqlite3

            if not os.path.exists(dsn):
                sys.exit(f"database not found: {dsn}")
            self.conn = sqlite3.connect(dsn)
            self.conn.row_factory = sqlite3.Row
            self.cur = self.conn.cursor()
            self.ph = "?"

    def rows(self, sql: str, params: Iterable = ()) -> List[Dict[str, Any]]:
        self.cur.execute(sql, tuple(params))
        return [dict(r) for r in self.cur.fetchall()]

    def execute(self, sql: str, params: Tuple = ()) -> int:
        sql = sql.replace("?", self.ph) if self.is_pg else sql
        self.cur.execute(sql, params)
        return self.cur.rowcount

    def commit(self):
        self.conn.commit()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass


def load_json(value) -> Optional[Any]:
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return None


# ------------------------------------------------------------------ pdf / text
def resolve_pdf(file_path: Optional[str]) -> Optional[str]:
    """The DB mixes './storage/cases\\x.pdf', 'storage/cases/x.pdf' and 'backend/...'."""
    if not file_path:
        return None
    q = file_path.replace("\\", "/").strip()
    q = re.sub(r"^\./", "", q)
    candidates = [
        os.path.join(ROOT, q),
        os.path.join(ROOT, "backend", q),
        os.path.join(ROOT, "storage", "cases", os.path.basename(q)),
        os.path.join(ROOT, "backend", "storage", "cases", os.path.basename(q)),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def clean_text(raw: str) -> str:
    """Reuse the app's sanitiser when importable; fall back to whitespace repair."""
    try:
        from app.services.text_sanitizer import text_sanitizer

        return text_sanitizer.clean_text(raw)
    except Exception:
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def extract_pdf_text(path: str, max_pages: int = 0) -> Tuple[str, int]:
    import pdfplumber

    with pdfplumber.open(path) as pdf:
        pages = pdf.pages if not max_pages else pdf.pages[:max_pages]
        chunks = [(p.extract_text() or "") for p in pages]
        return "\n".join(chunks), len(pdf.pages)


# ---------------------------------------------------------------------- jobs
def job_text(db: DB, args) -> Dict[str, Any]:
    rows = db.rows(
        "SELECT id, case_no, file_path, full_text FROM cases "
        "WHERE full_text IS NULL OR LENGTH(TRIM(full_text)) = 0"
    )
    if args.limit:
        rows = rows[: args.limit]

    stats: Dict[str, Any] = {
        "job": "text",
        "candidates": len(rows),
        "applied": bool(args.apply),
        "updated": 0,
        "skipped_missing_pdf": [],
        "skipped_short": [],
        "failed": [],
        "chars": [],
        "pages": [],
    }
    started = time.time()

    for i, row in enumerate(rows, 1):
        path = resolve_pdf(row["file_path"])
        if not path:
            stats["skipped_missing_pdf"].append(row["id"])
            continue
        try:
            raw, n_pages = extract_pdf_text(path)
        except Exception as exc:  # corrupt / not a real PDF / encrypted
            stats["failed"].append({"id": row["id"], "file": os.path.basename(path), "error": str(exc)[:160]})
            continue

        text = clean_text(raw)
        if len(text) < args.min_chars:
            stats["skipped_short"].append({"id": row["id"], "chars": len(text)})
            continue

        stats["chars"].append(len(text))
        stats["pages"].append(n_pages)
        if args.apply:
            db.execute("UPDATE cases SET full_text = ?, page_count = COALESCE(page_count, ?) WHERE id = ?"
                       if not db.is_pg else
                       "UPDATE cases SET full_text = %s, page_count = COALESCE(page_count, %s) WHERE id = %s",
                       (text, n_pages, row["id"]))
            if i % 25 == 0:
                db.commit()
        stats["updated"] += 1
        if i % 25 == 0 or i == len(rows):
            print(f"  [{i}/{len(rows)}] {stats['updated']} filled, {len(stats['failed'])} failed", file=sys.stderr)

    if args.apply:
        db.commit()

    if stats["chars"]:
        stats["char_stats"] = {
            "min": min(stats["chars"]),
            "median": int(statistics.median(stats["chars"])),
            "max": max(stats["chars"]),
        }
    stats["seconds"] = round(time.time() - started, 1)
    del stats["chars"]
    del stats["pages"]
    return stats


def embedding_text(row: Dict[str, Any], mode: str) -> str:
    title = (row.get("title") or "").strip()
    summary = (row.get("summary") or "").strip()
    tags = " ".join(list(load_json(row.get("section_tags")) or []) + list(load_json(row.get("keyword_tags")) or []))
    if mode == "full_text":
        body = (row.get("full_text") or "")[:4000]
        return f"{title}. {summary}. {tags}. {body}".strip()
    # Mirror the ingestion path (cases.py:142) so query-time similarity stays comparable.
    return f"{title}. {summary}. {tags}".strip()


def vector_is_fallback(vec: List[float]) -> bool:
    """Hashed bag-of-words vectors are sparse; MiniLM output is dense."""
    return sum(1 for x in vec if x != 0) < 360


def job_embeddings(db: DB, args) -> Dict[str, Any]:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        if not args.allow_fallback:
            sys.exit(
                "sentence-transformers is not installed, so no real embeddings can be computed.\n"
                "  pip install sentence-transformers   (downloads ~90 MB of wheels)\n"
                "  then run this again on a machine with access to huggingface.co\n"
                "Refusing to write hashed fallback vectors — that is what produced the current\n"
                "sparse vectors. Use --allow-fallback to override deliberately."
            )
        SentenceTransformer = None  # noqa: N806

    rows = db.rows(
        "SELECT id, case_no, title, summary, section_tags, keyword_tags, full_text, embedding FROM cases"
    )
    todo = []
    fallback_found = 0
    for row in rows:
        vec = load_json(row.get("embedding"))
        if vec is None:
            todo.append(row)
            continue
        if len(vec) != DIM:
            todo.append(row)
            continue
        if sum(1 for x in vec if x != 0) == 0:
            todo.append(row)
            continue
        if args.replace_fallback and vector_is_fallback(vec):
            fallback_found += 1
            todo.append(row)
    if args.limit:
        todo = todo[: args.limit]

    stats: Dict[str, Any] = {
        "job": "embeddings",
        "model": args.model,
        "text_mode": args.text_mode,
        "candidates": len(todo),
        "fallback_rows_seen": fallback_found,
        "applied": bool(args.apply),
        "written": 0,
    }
    if not todo:
        return stats

    model = None
    if SentenceTransformer is not None:
        print(f"loading {args.model} ...", file=sys.stderr)
        model = SentenceTransformer(args.model)
    started = time.time()

    for start in range(0, len(todo), args.batch_size):
        chunk = todo[start : start + args.batch_size]
        texts = [embedding_text(r, args.text_mode) or (r.get("case_no") or "") for r in chunk]
        if model is not None:
            vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            vectors = [[float(x) for x in v] for v in vectors]
        else:
            from app.services.embedding_service import embedding_service as svc

            vectors = [svc.generate_embedding(t) for t in texts]
        for row, vec in zip(chunk, vectors):
            payload = json.dumps(vec)
            if db.is_pg:
                db.execute("UPDATE cases SET embedding = %s::vector WHERE id = %s", (payload, row["id"]))
            else:
                db.execute("UPDATE cases SET embedding = ? WHERE id = ?", (payload, row["id"]))
            stats["written"] += 1
        db.commit()
        done = min(start + args.batch_size, len(todo))
        print(f"  [{done}/{len(todo)}] embedded", file=sys.stderr)

    stats["seconds"] = round(time.time() - started, 1)
    return stats


def job_verify(db: DB, args) -> Dict[str, Any]:
    total = db.rows("SELECT COUNT(*) AS n FROM cases")[0]["n"]
    no_text = db.rows(
        "SELECT COUNT(*) AS n FROM cases WHERE full_text IS NULL OR LENGTH(TRIM(full_text)) = 0"
    )[0]["n"]
    no_vec = db.rows("SELECT COUNT(*) AS n FROM cases WHERE embedding IS NULL")[0]["n"]
    rows = db.rows("SELECT id, file_path, embedding, file_hash FROM cases")

    zero = sparse = dense = wrong_dim = malformed = 0
    dangling = []
    for row in rows:
        vec = load_json(row["embedding"])
        if vec is not None:
            if not isinstance(vec, list):
                malformed += 1
            elif len(vec) != DIM:
                wrong_dim += 1
            elif sum(1 for x in vec if x != 0) == 0:
                zero += 1
            elif vector_is_fallback(vec):
                sparse += 1
            else:
                dense += 1
        if not resolve_pdf(row["file_path"]):
            dangling.append(row["id"])

    short = db.rows(
        "SELECT id, LENGTH(full_text) AS n FROM cases "
        "WHERE full_text IS NOT NULL AND LENGTH(TRIM(full_text)) BETWEEN 1 AND 999 "
        "ORDER BY LENGTH(full_text)"
    )

    hashes = {}
    for row in rows:
        h = row.get("file_hash")
        if h:
            hashes[h] = hashes.get(h, 0) + 1

    return {
        "job": "verify",
        "cases": total,
        "missing_full_text": no_text,
        "missing_embedding": no_vec,
        "vectors": {"zero": zero, "sparse_fallback_like": sparse, "dense": dense,
                    "wrong_dimension": wrong_dim, "malformed": malformed},
        "short_text_docs_under_1000_chars": len(short),
        "short_text_sample": [{"id": r["id"], "chars": r["n"]} for r in short[:5]],
        "dangling_pdf_paths": len(dangling),
        "duplicate_file_hash_groups": sum(1 for n in hashes.values() if n > 1),
    }


# ---------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("job", choices=["text", "embeddings", "verify"])
    ap.add_argument("--db", default=DEFAULT_SQLITE, help="SQLite path or postgresql:// DSN")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-chars", type=int, default=200, help="reject extracted texts shorter than this")
    ap.add_argument("--report", default="", help="write the JSON report here")
    ap.add_argument("--model", default=os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"))
    ap.add_argument("--text-mode", choices=["title_summary", "full_text"], default="title_summary")
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--replace-fallback", action="store_true", help="also redo sparse hashed vectors")
    ap.add_argument("--allow-fallback", action="store_true", help="permit the MD5 fallback vectoriser")
    args = ap.parse_args()

    db = DB(args.db)
    try:
        job = {"text": job_text, "embeddings": job_embeddings, "verify": job_verify}[args.job]
        result = job(db, args)
    finally:
        db.close()

    out = json.dumps(result, indent=2, default=str)
    print(out)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
