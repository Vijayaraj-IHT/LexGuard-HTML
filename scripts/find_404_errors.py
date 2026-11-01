#!/usr/bin/env python3
"""
find_404_errors.py — Broken link & route integrity crawler for LexGuard (Agent 5: Perf/QA).

Crawls all 20 HTML frontend pages through the real serving stack
(scripts/serve.py static+proxy -> uvicorn FastAPI backend) and verifies that:

  * every page            -> HTTP 200
  * every internal href / button link (a[href], link[href], script[src], img[src],
    form[action], inline onclick location.href / window.open, data-href)
    -> HTTP 200 (missing static assets are reported as 404s by serve.py)
  * every static asset referenced from CSS (url(...)) -> HTTP 200
  * every API endpoint called from frontend JS (url: '/...', LG.api.request('/...'),
    template literals with ${...}, string concatenation) -> matches a declared
    FastAPI route AND responds over HTTP (200 = OK; 401/403/422 = resolved but
    auth/validation-gated; routed-but-404/405/5xx or connection error = BROKEN).
    Referenced paths with NO backend route are listed separately as FINDINGS
    (product gaps) — pass --strict-api to also fail on those.

Dynamic path segments (${caseId}, ${hash}, ...) are instantiated with real values
from a temp copy of the corpus database, and each crawled API path is additionally
validated against the app's own OpenAPI route table (the "route validator").

The repository database is never mutated: the crawler copies backend/lexguard.db
to a temp file for its self-hosted backend.

Usage:
    python scripts/find_404_errors.py                 # self-hosted stack, full crawl
    python scripts/find_404_errors.py --base-url http://127.0.0.1:8080   # crawl a running instance
    python scripts/find_404_errors.py --offline       # pure filesystem check, no servers
    python scripts/find_404_errors.py --strict-api    # exit 1 also on unrouted API refs

Exit code: 0 when 0 broken internal links and 0 missing static assets (and, with
--strict-api, 0 unrouted API refs), else 1.
Standard library only for HTTP (urllib); the FastAPI app is imported only for
route-table validation when its dependencies are installed.
"""

import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = REPO_ROOT / "frontend"
BACKEND_DIR = REPO_ROOT / "backend"
SERVE_PY = REPO_ROOT / "scripts" / "serve.py"
DEFAULT_DB = BACKEND_DIR / "lexguard.db"

SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:", "sms:")
SENTINEL = "\x00{}\x00"  # placeholder for ${...} template segments


# ---------------------------------------------------------------------------
# HTTP helper (stdlib only)
# ---------------------------------------------------------------------------

def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "lexguard-404-crawler/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return resp.status, dict(resp.headers), body
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read() if hasattr(e, "read") else b""
    except Exception as e:
        return None, {}, str(e).encode()


def http_request(method, url, body=None, content_type=None, timeout=20):
    data = None
    headers = {"User-Agent": "lexguard-404-crawler/1.0"}
    if body is not None:
        data = body if isinstance(body, bytes) else body.encode()
        headers["Content-Type"] = content_type or "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            return resp.status
    except urllib.error.HTTPError as e:
        try:
            e.read()
        except Exception:
            pass
        return e.code
    except Exception:
        return None


# ---------------------------------------------------------------------------
# HTML / JS reference extraction
# ---------------------------------------------------------------------------

class RefCollector(HTMLParser):
    """Collects every navigational/asset reference from an HTML page."""

    URL_ATTRS = {
        "a": ["href"], "link": ["href"], "script": ["src"], "img": ["src", "srcset"],
        "iframe": ["src"], "form": ["action"], "source": ["src", "srcset"],
        "video": ["src", "poster"], "audio": ["src"], "embed": ["src"], "object": ["data"],
        "button": ["data-href"], "div": ["data-href"], "span": ["data-href"],
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.refs = []          # (kind, raw_value, source_attr)
        self.inline_js = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for attr in self.URL_ATTRS.get(tag, []):
            if a.get(attr):
                raw_val = a[attr]
                if attr == "srcset":
                    # srcset is a comma-separated candidate list: "url 1x, url2 2x"
                    vals = [v.strip().split(" ")[0] for v in raw_val.split(",")]
                else:
                    vals = [raw_val.strip()]
                for val in vals:
                    if val:
                        self.refs.append((tag, val, attr))
        for attr, val in attrs:
            if attr.lower().startswith("on") and val:  # onclick="location.href='...'"
                self.inline_js.append(val)
        if tag == "script" and not a.get("src"):
            self._in_script = True

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_script = False

    def handle_data(self, data):
        if getattr(self, "_in_script", False):
            self.inline_js.append(data)


LOCATION_RE = re.compile(r"""(?:location\.href|window\.location|location)\s*=\s*['"]([^'"]+)['"]""")
WINDOW_OPEN_RE = re.compile(r"""window\.open\(\s*['"]([^'"]+)['"]""")
JS_STRING_RE = re.compile(r"""['"](/[A-Za-z0-9_\-./${}()]*)['"]""")
BACKTICK_RE = re.compile(r"`([^`]*)`")
JS_CONCAT_RE = re.compile(r"""'(/[a-z][a-z0-9_\-/]*?)'\s*\+[^;]{0,200}?\+\s*'(/[a-z0-9_\-]+)'""")
JS_PREFIX_CONCAT_RE = re.compile(r"""'(/[a-z][a-z0-9_\-/]*/)'\s*\+""")
CSS_URL_RE = re.compile(r"""url\(\s*['"]?([^'")]+)['"]?\s*\)""")
TEMPLATE_RE = re.compile(r"\$\{[^}]*\}")

# top-level API router prefixes mounted under /api/v1 (see backend/app/api/v1/api.py)
API_PREFIXES = (
    "/auth", "/users", "/cases", "/statutes", "/verification", "/comparison",
    "/search", "/draft", "/admin", "/bookmarks", "/health",
)


def _normalize_api_path(raw):
    """-> normalized /api/v1-prefixed path with sentinels for ${...}, or None to skip."""
    raw = raw.split("?")[0].split("#")[0]
    if not raw or raw == "/":
        return None
    raw = TEMPLATE_RE.sub(SENTINEL.format(0), raw)
    if not any(raw == p or raw.startswith(p + "/") for p in API_PREFIXES):
        return None
    if not raw.startswith("/api"):
        raw = "/api/v1" + raw
    if raw.rstrip("/") in ("/api", "/api/v1"):
        return None
    return raw


def extract_js_api_paths(js_files):
    """Returns sorted unique API paths (with sentinels) referenced from frontend JS."""
    paths = set()
    for path in js_files:
        try:
            content = Path(path).read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        # plain quoted strings: url: '/search/', LG.api.request('/admin/queue', ...)
        for m in JS_STRING_RE.finditer(content):
            norm = _normalize_api_path(m.group(1))
            if norm:
                paths.add(norm)
        # template literals: `${baseApi}/statutes/${act}/${sec}`
        for m in BACKTICK_RE.finditer(content):
            bt = m.group(1)
            slash = bt.find("/")
            if slash >= 0:
                norm = _normalize_api_path(bt[slash:])
                if norm:
                    paths.add(norm)
        # string concatenation: API_BASE + '/cases/' + id + '/download'
        for m in JS_CONCAT_RE.finditer(content):
            joined = m.group(1) + SENTINEL.format(0) + m.group(2)
            norm = _normalize_api_path(joined)
            if norm:
                paths.add(norm)
        # single prefix + dynamic value: url: '/admin/approve/' + encodeURIComponent(cid)
        for m in JS_PREFIX_CONCAT_RE.finditer(content):
            norm = _normalize_api_path(m.group(1) + SENTINEL.format(0))
            if norm:
                paths.add(norm)
    # drop bare prefix fragments of concatenated paths (e.g. '/cases/' or
    # '/verification/documents/<sentinel>' when the full '/.../<sentinel>/download'
    # was also captured) — they are not real endpoint calls
    prefixes = set()
    for p in paths:
        if any(q.startswith(p + "\x00") for q in paths):  # bare prefix of a concat path, e.g. '/admin/approve/'
            prefixes.add(p)
        if (p.endswith("/") or p.endswith("\x00")) and any(q != p and q.startswith(p + "/") for q in paths):
            prefixes.add(p)  # intermediate segment of a longer concat path
    paths = {p for p in paths if p not in prefixes}
    return sorted(paths)


def classify_ref(raw, page_url, base_origin):
    """-> ('page'|'asset'|'api'|'external'|'skip', absolute_url, request_path)"""
    val = raw.strip()
    if not val or val.startswith("#"):
        return ("skip", None, None)
    low = val.lower()
    if low.startswith(SKIP_SCHEMES):
        return ("skip", None, None)
    absolute = urllib.parse.urljoin(page_url, val)
    parsed = urllib.parse.urlsplit(absolute)
    if parsed.scheme in ("http", "https"):
        if parsed.netloc != urllib.parse.urlsplit(base_origin).netloc:
            return ("external", absolute, None)
    path = parsed.path or "/"
    if path.startswith("/api/"):
        return ("api", absolute, path)
    return ("asset", absolute, path)


# ---------------------------------------------------------------------------
# Route table validation (imports the FastAPI app when available)
# ---------------------------------------------------------------------------

def load_route_table(db_url):
    """-> list of (compiled_regex, path_template, methods) or None if app not importable.

    Uses the app's own OpenAPI schema (stable across FastAPI versions) so every
    mounted /api/v1 route — including {param} templates — is known.
    """
    os.environ["DATABASE_URL"] = db_url
    os.environ["ENVIRONMENT"] = "development"
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    try:
        import re as _re
        from app.main import app
        schema = app.openapi()
        table = []
        for path, ops in schema.get("paths", {}).items():
            methods = {m.upper() for m in ops.keys()}
            regex = _re.sub(r"\{[^}]+\}", r"[^/]+", path)
            table.append((_re.compile("^" + regex + "$"), path, methods))
        return table
    except Exception as e:
        print(f"[warn] route-table validation unavailable ({e}); relying on live HTTP checks only")
        return None


def match_route(route_table, path):
    if not route_table:
        return None
    for regex, template, methods in route_table:
        if regex.match(path):
            return template, methods
    return None


# ---------------------------------------------------------------------------
# Dynamic path instantiation with real corpus values
# ---------------------------------------------------------------------------

def corpus_values(db_path):
    import sqlite3
    vals = {"case_id": "x", "file_hash": "0" * 64, "act_code": "IPC", "section_no": "302"}
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute("SELECT id, file_hash FROM cases WHERE status='published' ORDER BY created_at DESC LIMIT 1").fetchone()
        if row:
            vals["case_id"], vals["file_hash"] = row[0], row[1]
        row = conn.execute("SELECT act_code, section_no FROM statute_sections ORDER BY act_code LIMIT 1").fetchone()
        if row:
            vals["act_code"], vals["section_no"] = row[0], row[1]
        conn.close()
    except Exception:
        pass
    return vals


def instantiate(path, vals):
    """Replace sentinel segments with real values chosen by path context."""
    segs = path.split("/")
    out = []
    statute_pos = 0
    for seg in segs:
        if seg.startswith("\x00"):
            prev = out[-1] if out else ""
            if prev == "lookup":
                out.append(vals["file_hash"])
            elif prev == "cases":
                out.append(vals["case_id"])
            elif "statutes" in out:
                out.append(vals["act_code"] if statute_pos == 0 else vals["section_no"])
                statute_pos += 1
            else:
                out.append("x")
        else:
            out.append(seg)
    return "/".join(out)


# ---------------------------------------------------------------------------
# Server boot (self-hosted mode)
# ---------------------------------------------------------------------------

def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def wait_http(url, timeout=45):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status, _, _ = http_get(url, timeout=3)
        if status is not None and status < 500:
            return True
        time.sleep(0.3)
    return False


class LiveStack:
    def __init__(self, db_path):
        self.db_path = db_path
        self.backend_port = free_port()
        self.proxy_port = free_port()
        self.procs = []

    def __enter__(self):
        env = dict(os.environ)
        env["DATABASE_URL"] = f"sqlite:///{self.db_path}"
        env["ENVIRONMENT"] = "development"
        backend = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app",
             "--host", "127.0.0.1", "--port", str(self.backend_port)],
            cwd=str(BACKEND_DIR), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        proxy = subprocess.Popen(
            [sys.executable, str(SERVE_PY), "--bind", "127.0.0.1",
             "--port", str(self.proxy_port), "--backend", f"http://127.0.0.1:{self.backend_port}"],
            cwd=str(REPO_ROOT),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.procs = [proxy, backend]
        ok_b = wait_http(f"http://127.0.0.1:{self.backend_port}/health")
        ok_p = wait_http(f"http://127.0.0.1:{self.proxy_port}/index.html")
        if not (ok_b and ok_p):
            self.__exit__(None, None, None)
            raise RuntimeError("could not boot uvicorn/serve.py (is the project venv active?)")
        self.backend = f"http://127.0.0.1:{self.backend_port}"
        self.base = f"http://127.0.0.1:{self.proxy_port}"
        return self

    def __exit__(self, *exc):
        for p in self.procs:
            p.terminate()
        for p in self.procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
        return False


# ---------------------------------------------------------------------------
# Crawl
# ---------------------------------------------------------------------------

def crawl(base_url, route_table, vals, verbose=False):
    base_origin = base_url.rstrip("/")
    pages = sorted(p.name for p in FRONTEND_DIR.glob("*.html"))
    js_files = sorted(FRONTEND_DIR.rglob("*.js"))
    css_files = sorted((FRONTEND_DIR / "css").glob("*.css"))

    report = {
        "pages": [], "assets": {}, "api_refs": set(), "api": {}, "broken_links": [],
        "broken_assets": [], "broken_api": [], "unrouted_api": [],
        "external": 0, "skipped": 0,
    }

    page_links = {}   # request_path -> count of references
    asset_paths = {}  # request_path -> kind

    # ---- 1. crawl every HTML page, collect refs ----
    for page in pages:
        page_url = f"{base_origin}/{page}"
        status, headers, body = http_get(page_url)
        report["pages"].append((page, status))
        if status != 200:
            report["broken_links"].append(f"PAGE {page} -> HTTP {status}")
            continue
        text = body.decode("utf-8", errors="ignore")
        collector = RefCollector()
        try:
            collector.feed(text)
        except Exception:
            pass
        refs = list(collector.refs)
        for js in collector.inline_js + re.findall(r"<script[^>]*>(.*?)</script>", text, re.S):
            for m in LOCATION_RE.finditer(js):
                refs.append(("inline-js", m.group(1), "location.href"))
            for m in WINDOW_OPEN_RE.finditer(js):
                refs.append(("inline-js", m.group(1), "window.open"))
        for kind, raw, attr in refs:
            cls, absolute, path = classify_ref(raw, page_url, base_origin)
            if cls == "skip":
                report["skipped"] += 1
            elif cls == "external":
                report["external"] += 1
            elif cls == "api":
                report["api_refs"].add(path)
            else:
                asset_paths.setdefault(path, kind)
                if path.endswith(".html"):
                    page_links.setdefault(path, 0)
                    page_links[path] += 1

    # ---- 2. API paths referenced from JS files ----
    for js_path in extract_js_api_paths(js_files):
        report["api_refs"].add(js_path)

    # ---- 3. CSS url() assets ----
    for css in css_files:
        css_url = f"{base_origin}/css/{css.name}"
        content = css.read_text(encoding="utf-8", errors="ignore")
        for m in CSS_URL_RE.finditer(content):
            ref = m.group(1).strip()
            if ref.startswith(("data:", "http", "//")):
                continue
            cls, absolute, path = classify_ref(urllib.parse.urljoin(f"/css/{css.name}", ref), css_url, base_origin)
            if cls == "asset":
                asset_paths.setdefault(path, "css")

    # ---- 4. verify pages linked from pages (internal .html links) ----
    for path in sorted(page_links):
        status, _, _ = http_get(base_origin + path)
        if status != 200:
            report["broken_links"].append(f"LINK {path} -> HTTP {status}")

    # ---- 5. verify static assets -> must be HTTP 200 ----
    for path in sorted(asset_paths):
        status, _, _ = http_get(base_origin + path)
        report["assets"][path] = status
        if status != 200:
            report["broken_assets"].append(f"ASSET {path} ({asset_paths[path]}) -> HTTP {status}")

    # ---- 6. verify API endpoints: route-table match + live HTTP ----
    for raw_path in sorted(report["api_refs"]):
        concrete = instantiate(raw_path, vals)
        # FastAPI routes may be declared with or without a trailing slash; try both.
        variants = []
        for v in (concrete, concrete.rstrip("/"), concrete.rstrip("/") + "/"):
            if v not in variants:
                variants.append(v)
        match = None
        checked = None
        if route_table:
            for v in variants:
                match = match_route(route_table, v)
                if match:
                    checked = v
                    break
            if match is None:
                report["unrouted_api"].append(concrete)
                report["api"][concrete] = "UNROUTED (no backend route)"
                if verbose:
                    print(f"    api {concrete:<58} -> UNROUTED")
                continue
        else:
            checked = concrete
        url = base_origin + checked
        methods = sorted(match[1]) if match else ["GET", "POST"]
        methods = [m for m in methods if m in ("GET", "POST", "PUT", "PATCH", "DELETE")] or ["GET"]
        search_body = '{"query": "crawl-check", "limit": 1}'
        best = None
        if "POST" in methods and "GET" not in methods:
            best = http_request("POST", url, body=search_body if "/search/" in checked else "{}")
        elif "GET" in methods:
            best = http_request("GET", url)
            if best in (405, 404) and "POST" in methods:
                best = http_request("POST", url, body=search_body if "/search/" in checked else "{}")
        else:
            best = http_request(methods[0], url, body="{}")
        if best is None:
            report["broken_api"].append(f"API {checked} -> connection error")
            report["api"][checked] = "connection error"
        elif best == 200:
            report["api"][checked] = "200 OK"
        elif best in (401, 403, 422):
            report["api"][checked] = f"resolved (HTTP {best}, auth/validation-gated)"
        elif best == 404 and match is not None and "{" in match[0]:
            report["api"][checked] = "route OK (404: dynamic resource id not in corpus)"
        elif best in (404, 405) or (isinstance(best, int) and best >= 500):
            report["broken_api"].append(f"API {checked} -> HTTP {best}")
            report["api"][checked] = f"HTTP {best}"
        else:
            report["api"][checked] = f"HTTP {best}"
        if verbose:
            print(f"    api {checked:<58} -> {report['api'].get(checked)}")

    return report, pages


# ---------------------------------------------------------------------------
# Offline filesystem check (kept from the original script, paths fixed)
# ---------------------------------------------------------------------------

def offline_check():
    print("=== Offline filesystem link check (frontend/) ===")
    broken = []
    pages = sorted(FRONTEND_DIR.glob("*.html"))
    existing = {p.name for p in FRONTEND_DIR.iterdir()}
    for page in pages:
        text = page.read_text(encoding="utf-8", errors="ignore")
        collector = RefCollector()
        try:
            collector.feed(text)
        except Exception:
            pass
        for kind, raw, attr in collector.refs:
            cls, _, path = classify_ref(raw, f"file:///{page.name}", "file:///")
            if cls in ("skip", "external"):
                continue
            target = (FRONTEND_DIR / path.lstrip("/")).resolve()
            if not target.exists():
                broken.append(f"{page.name}: {attr}={raw} -> missing {target}")
    print(f"pages scanned : {len(pages)}")
    print(f"broken refs   : {len(broken)}")
    for b in broken:
        print("  [MISSING]", b)
    return len(broken)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default=None,
                    help="crawl an already-running serve.py instance (default: boot a private stack)")
    ap.add_argument("--offline", action="store_true", help="filesystem-only check, no servers")
    ap.add_argument("--strict-api", action="store_true",
                    help="also fail (exit 1) when frontend JS references API paths with no backend route")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.offline:
        return 1 if offline_check() else 0

    tmp_dir = None
    db_path = None
    route_table = None
    vals = corpus_values(str(DEFAULT_DB)) if DEFAULT_DB.exists() else {}

    if args.base_url:
        base_url = args.base_url.rstrip("/")
        route_table = load_route_table(f"sqlite:///{DEFAULT_DB}") if DEFAULT_DB.exists() else None
    else:
        if not DEFAULT_DB.exists():
            sys.exit(f"corpus database not found: {DEFAULT_DB}")
        tmp_dir = tempfile.mkdtemp(prefix="lexguard_404_")
        db_path = os.path.join(tmp_dir, "lexguard_crawl.db")
        shutil.copy2(DEFAULT_DB, db_path)
        route_table = load_route_table(f"sqlite:///{db_path}")
        vals = corpus_values(db_path)
        print("[crawl] booting private uvicorn + serve.py stack (temp DB copy)...")
        stack_ctx = LiveStack(db_path)
        stack = stack_ctx.__enter__()
        base_url = stack.base
        try:
            report, pages = crawl(base_url, route_table, vals, verbose=args.verbose)
        finally:
            stack_ctx.__exit__(None, None, None)
        return summarize(report, pages, strict_api=args.strict_api)

    report, pages = crawl(base_url, route_table, vals, verbose=args.verbose)
    return summarize(report, pages, strict_api=args.strict_api)


def summarize(report, pages, strict_api=False):
    n_pages_ok = sum(1 for _, s in report["pages"] if s == 200)
    n_assets = len(report["assets"])
    n_assets_ok = sum(1 for s in report["assets"].values() if s == 200)
    api_results = list(report["api"].values())
    n_api_200 = sum(1 for v in api_results if v == "200 OK")
    n_api_gated = sum(1 for v in api_results if v.startswith("resolved") or v.startswith("route OK"))
    n_api_unrouted = len(report["unrouted_api"])

    print()
    print("=== LexGuard 404 / route integrity crawl ===")
    print(f"  HTML pages crawled      : {len(report['pages'])} (expected 20) — {n_pages_ok} returned HTTP 200")
    print(f"  internal page links     : checked — {len(report['broken_links'])} broken")
    print(f"  static assets (unique)  : {n_assets} — {n_assets_ok} returned HTTP 200, {len(report['broken_assets'])} missing")
    print(f"  API endpoints discovered: {len(api_results)} — {n_api_200} HTTP 200, {n_api_gated} resolved-but-gated, "
          f"{n_api_unrouted} unrouted, {len(report['broken_api'])} broken")
    print(f"  external refs skipped   : {report['external']} · non-link refs skipped: {report['skipped']}")

    if report["broken_links"]:
        print("\n  BROKEN INTERNAL LINKS:")
        for b in report["broken_links"]:
            print("   ", b)
    if report["broken_assets"]:
        print("\n  MISSING STATIC ASSETS:")
        for b in report["broken_assets"]:
            print("   ", b)
    if report["broken_api"]:
        print("\n  BROKEN API ENDPOINTS (routed but erroring):")
        for b in report["broken_api"]:
            print("   ", b)
    if report["unrouted_api"]:
        print("\n  FINDING — frontend references with NO backend route (product gap, not a link/asset 404):")
        for b in sorted(set(report["unrouted_api"])):
            print("   ", b)

    links_assets_clean = not report["broken_links"] and not report["broken_assets"] and not report["broken_api"]
    if links_assets_clean and not (strict_api and report["unrouted_api"]):
        print("\n  RESULT: PASS — 0 broken internal links, 0 missing static assets"
              + ("" if not report["unrouted_api"] else f", {n_api_unrouted} unrouted API refs listed as findings"))
        return 0
    print("\n  RESULT: FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
