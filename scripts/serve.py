#!/usr/bin/env python3
"""
serve.py — one process to run LexGuard locally.

Serves the static frontend and reverse-proxies /api/* to the FastAPI backend, so the
browser only ever talks to one origin. That removes the two things that made the app
undeployable:

  * `API_BASE` no longer has to be a hard-coded http://127.0.0.1:8000 (the frontend
    resolves `/api/v1` from the page origin — see js/lexguard-core.js)
  * no CORS or mixed-origin configuration is needed at all

Standard library only. Usage:

    python backend/...        # not needed; start the API separately:
    uvicorn app.main:app --port 8000          # inside backend/

    python scripts/serve.py                   # http://0.0.0.0:8080
    python scripts/serve.py --port 9000 --backend http://127.0.0.1:8001
    python scripts/serve.py --no-gzip --no-cache

Flags:
    --dir DIR          static root (default: frontend/)
    --backend URL      API origin to proxy (default: http://127.0.0.1:8000)
    --port PORT        listen port (default: 8080)
    --bind ADDR        listen address (default: 0.0.0.0)
    --no-gzip          disable response compression
    --no-cache         send no-store instead of cache headers
"""
import argparse
import gzip
import http.client
import mimetypes
import os
import posixpath
import sys
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

COMPRESSIBLE = {
    "text/html",
    "text/css",
    "text/plain",
    "text/javascript",
    "application/javascript",
    "application/json",
    "image/svg+xml",
    "application/xml",
}
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
GZIP_MIN_BYTES = 512


class Handler(SimpleHTTPRequestHandler):
    backend = "http://127.0.0.1:8000"
    use_gzip = True
    use_cache = True
    static_root = os.path.join(ROOT, "frontend")
    protocol_version = "HTTP/1.1"

    # ---------------------------------------------------------------- helpers
    def log_message(self, fmt, *args):  # quieter, single-line access log
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _cache_header(self, path):
        if not self.use_cache:
            return "no-store"
        ext = os.path.splitext(path)[1].lower()
        if ext in (".html", ".htm"):
            return "no-cache"
        if ext in (".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".woff2", ".ico"):
            return "public, max-age=3600"
        return "no-cache"

    def _maybe_gzip(self, body, content_type):
        if not self.use_gzip or len(body) < GZIP_MIN_BYTES:
            return body, None
        if content_type not in COMPRESSIBLE:
            return body, None
        if "gzip" not in (self.headers.get("Accept-Encoding") or "").lower():
            return body, None
        return gzip.compress(body, 6), "gzip"

    # ---------------------------------------------------------------- proxying
    def _proxy(self):
        parsed = urllib.parse.urlparse(self.backend)
        target = urllib.parse.urlsplit(self.path)
        upstream_path = target.path + (("?" + target.query) if target.query else "")

        body = None
        length = self.headers.get("Content-Length")
        if length:
            body = self.rfile.read(int(length))

        conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
        conn = conn_cls(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), timeout=120)
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP | {"host", "content-length"}}
        headers["Host"] = parsed.netloc
        if body is not None:
            headers["Content-Length"] = str(len(body))

        try:
            conn.request(self.command, upstream_path, body=body, headers=headers)
            resp = conn.getresponse()
            payload = resp.read()
        except Exception as exc:  # backend down, DNS failure, timeout
            msg = f"Backend unavailable at {self.backend}: {exc}".encode()
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(msg)
            return
        finally:
            try:
                conn.close()
            except Exception:
                pass

        content_type = resp.getheader("Content-Type", "application/octet-stream").split(";")[0].strip()
        encoded, encoding = self._maybe_gzip(payload, content_type)

        self.send_response(resp.status)
        for key, value in resp.getheaders():
            if key.lower() in HOP_BY_HOP or key.lower() in (
                "content-length",
                "content-encoding",
                "x-content-type-options",
            ):
                continue
            self.send_header(key, value)
        if encoding:
            self.send_header("Content-Encoding", encoding)
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(encoded)

    # ---------------------------------------------------------------- static
    def translate_path(self, path):
        # Serve from frontend/ regardless of where the process was started.
        path = urllib.parse.urlsplit(path).path
        path = posixpath.normpath(urllib.parse.unquote(path))
        parts = [p for p in path.split("/") if p and p not in (".", "..")]
        full = os.path.join(self.static_root, *parts)
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        return full

    def send_head(self):
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            not_found = os.path.join(self.static_root, "404.html")
            if self.path != "/404.html" and os.path.isfile(not_found):
                self.path = "/404.html"
                path = not_found
                self._forced_404 = True
            else:
                return super().send_head()

        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        try:
            with open(path, "rb") as fh:
                body = fh.read()
        except OSError:
            return super().send_head()

        encoded, encoding = self._maybe_gzip(body, ctype.split(";")[0])
        status = 404 if getattr(self, "_forced_404", False) else 200
        self._forced_404 = False

        self.send_response(status)
        self.send_header("Content-Type", ctype)
        if encoding:
            self.send_header("Content-Encoding", encoding)
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", self._cache_header(path))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()

        import io

        return io.BytesIO(encoded)

    # ---------------------------------------------------------------- verbs
    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._proxy()
        return super().do_GET()

    def do_HEAD(self):
        if self.path.startswith("/api/"):
            return self._proxy()
        return super().do_HEAD()

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self._proxy()
        self.send_error(405, "POST is only proxied under /api/")

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST

    def do_OPTIONS(self):
        if self.path.startswith("/api/"):
            return self._proxy()
        self.send_response(204)
        self.send_header("Allow", "GET, HEAD, OPTIONS")
        self.end_headers()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=os.path.join(ROOT, "frontend"))
    ap.add_argument("--backend", default=os.getenv("LG_BACKEND", "http://127.0.0.1:8000"))
    ap.add_argument("--port", type=int, default=int(os.getenv("LG_PORT", "8080")))
    ap.add_argument("--bind", default=os.getenv("LG_BIND", "0.0.0.0"))
    ap.add_argument("--no-gzip", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    if not os.path.isdir(args.dir):
        sys.exit(f"static directory not found: {args.dir}")

    Handler.static_root = args.dir
    Handler.backend = args.backend.rstrip("/")
    Handler.use_gzip = not args.no_gzip
    Handler.use_cache = not args.no_cache

    server = ThreadingHTTPServer((args.bind, args.port), Handler)
    print(f"LexGuard UI   http://{args.bind}:{args.port}  (static: {args.dir})")
    print(f"API proxy     /api/* -> {Handler.backend}")
    print(f"gzip {'on' if Handler.use_gzip else 'off'} · cache {'on' if Handler.use_cache else 'off'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
