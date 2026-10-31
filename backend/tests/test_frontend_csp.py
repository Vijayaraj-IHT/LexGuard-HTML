"""
Static checks for the frontend Content-Security-Policy (D6).

The frontend is served by `python -m http.server`, which cannot send headers, so the
policy is a <meta http-equiv="Content-Security-Policy"> tag on every page. These tests
read the HTML and JS files directly. They do not load a browser, so they cannot prove
that a page works under the policy; that needs a manual browser check.

Standard library only; does not import the app.
Run from backend/:  python -m pytest tests/test_frontend_csp.py -q -p no:cacheprovider
"""
import glob
import os
import re
from html.parser import HTMLParser

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FRONTEND = os.path.join(REPO_ROOT, "frontend")
PAGES = sorted(glob.glob(os.path.join(FRONTEND, "*.html")))
JS_FILES = sorted(glob.glob(os.path.join(FRONTEND, "js", "**", "*.js"), recursive=True))


class _PageScan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.csp_metas = []
        self.inline_scripts = 0
        self.script_srcs = []
        self.stylesheet_hrefs = []
        self.on_attrs = []
        self.js_urls = []
        self._in_script_inline = False

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        for k, v in a.items():
            if k.startswith("on"):
                self.on_attrs.append((tag, k))
            if k in ("href", "src", "action") and v.strip().lower().startswith("javascript:"):
                self.js_urls.append((tag, k, v))
        if tag == "meta" and a.get("http-equiv", "").lower() == "content-security-policy":
            self.csp_metas.append(a.get("content", ""))
        if tag == "script":
            if a.get("src"):
                self.script_srcs.append(a["src"])
            else:
                self.inline_scripts += 1
        if tag == "link" and "stylesheet" in a.get("rel", "").lower():
            self.stylesheet_hrefs.append(a.get("href", ""))


def _parse_csp(text):
    directives = {}
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        name, *sources = part.split()
        directives[name.lower()] = sources
    return directives


def _host(url):
    m = re.match(r"^(https?)://([^/:]+)(?::\d+)?", url)
    return f"{m.group(1)}://{m.group(2)}" if m else None


def _scan(path):
    with open(path, encoding="utf-8") as fh:
        scan = _PageScan()
        scan.feed(fh.read())
    return scan


def test_pages_were_found():
    assert len(PAGES) >= 20, f"expected the 20 HTML pages, found {len(PAGES)}"


@pytest.mark.parametrize("page", PAGES, ids=[os.path.basename(p) for p in PAGES])
def test_page_has_one_csp_meta(page):
    scan = _scan(page)
    assert len(scan.csp_metas) == 1, f"{os.path.basename(page)}: expected exactly one CSP meta tag"


@pytest.mark.parametrize("page", PAGES, ids=[os.path.basename(p) for p in PAGES])
def test_policy_is_strict_where_it_matters(page):
    d = _parse_csp(_scan(page).csp_metas[0])
    assert d.get("default-src") == ["'self'"]
    assert d.get("object-src") == ["'none'"]
    assert d.get("base-uri") == ["'self'"]
    script = d.get("script-src", [])
    assert "'unsafe-inline'" not in script, "script-src must not allow inline scripts"
    assert "'unsafe-eval'" not in script, "script-src must not allow eval"
    assert "'unsafe-eval'" not in d.get("worker-src", [])


@pytest.mark.parametrize("page", PAGES, ids=[os.path.basename(p) for p in PAGES])
def test_no_inline_script_or_handlers_or_js_urls(page):
    scan = _scan(page)
    name = os.path.basename(page)
    assert scan.inline_scripts == 0, f"{name}: inline <script> block remains"
    assert scan.on_attrs == [], f"{name}: inline event handler attributes: {scan.on_attrs}"
    assert scan.js_urls == [], f"{name}: javascript: URLs: {scan.js_urls}"


@pytest.mark.parametrize("page", PAGES, ids=[os.path.basename(p) for p in PAGES])
def test_external_hosts_are_allowed_by_policy(page):
    scan = _scan(page)
    d = _parse_csp(scan.csp_metas[0])
    script_hosts = {s for s in d.get("script-src", []) if s.startswith("https://")}
    style_hosts = {s for s in d.get("style-src", []) if s.startswith("https://")}
    name = os.path.basename(page)
    for src in scan.script_srcs:
        if src.startswith(("http://", "https://")):
            assert _host(src) in script_hosts, f"{name}: script host not allowed: {src}"
    for href in scan.stylesheet_hrefs:
        if href.startswith(("http://", "https://")):
            assert _host(href) in style_hosts, f"{name}: stylesheet host not allowed: {href}"


@pytest.mark.parametrize("page", PAGES, ids=[os.path.basename(p) for p in PAGES])
def test_local_scripts_exist(page):
    scan = _scan(page)
    for src in scan.script_srcs:
        if src.startswith(("http://", "https://")):
            continue
        local = src.split("?")[0].split("#")[0]  # drop cache-busting query strings
        assert os.path.isfile(os.path.join(FRONTEND, local)), f"{os.path.basename(page)}: missing {src}"


_INLINE_HANDLER_IN_JS = re.compile(r"""\bon[a-z]+\s*=\s*\\?["']""")


@pytest.mark.parametrize("path", JS_FILES, ids=[os.path.relpath(p, FRONTEND) for p in JS_FILES])
def test_js_templates_have_no_inline_handlers(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    hits = _INLINE_HANDLER_IN_JS.findall(text)
    assert hits == [], f"{os.path.relpath(path, FRONTEND)}: inline handler attribute in JS template: {hits}"
