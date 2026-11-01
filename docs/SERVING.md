# Serving LexGuard — one origin, no hard-coded backend URL

## The problem this fixes

The frontend hard-coded `http://127.0.0.1:8000/api/v1` in three places (`lexguard-core.js:13`, plus duplicated fallbacks in `pages/acts-explorer.js` and `pages/index.js`). That meant:

- the app only worked on the developer's own machine,
- any deployment needed CORS, mixed-origin configuration and a matching CSP `connect-src`,
- a sandboxed or proxied preview could never reach the API.

## What changed

| File | Change |
|---|---|
| `frontend/js/lexguard-core.js` | `API_BASE` is resolved at runtime instead of hard-coded |
| `frontend/js/pages/acts-explorer.js`, `pages/index.js` | duplicated literal fallbacks removed; both use `LG.config.API_BASE` |
| `scripts/serve.py` | new stdlib-only server: static frontend + `/api/*` reverse proxy + gzip + cache headers |
| `README.md` | quick start uses `serve.py`; the plain `http.server 8888` path still documented |

### Resolution order

```
1. <meta name="lg-api-base" content="...">   per-deployment override
2. window.LG_API_BASE                        runtime override (tests, embeds)
3. file:// or port 8888                      legacy dev → http://127.0.0.1:8000/api/v1
4. anything else                             same origin → /api/v1
```

Rule 3 keeps the old two-terminal workflow working unchanged. Rule 4 is what makes
`serve.py` (and any reverse proxy in front of the API) work with no configuration.
Rule 1 lets one build point at a different API without a rebuild:

```html
<meta name="lg-api-base" content="https://api.example.org/api/v1">
```

## Running it

```bash
# terminal 1 — API
cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# terminal 2 — UI + proxy
python scripts/serve.py --port 8080
```

```
LexGuard UI   http://0.0.0.0:8080  (static: frontend/)
API proxy     /api/* -> http://127.0.0.1:8000
gzip on · cache on
```

Options: `--dir`, `--backend`, `--port`, `--bind`, `--no-gzip`, `--no-cache`.
Environment equivalents: `LG_PORT`, `LG_BIND`, `LG_BACKEND`.

## Measured behaviour

Verified against a live uvicorn instance on :8000:

| Request | Result |
|---|---|
| `GET /` | `200`, `Cache-Control: no-cache`, HTML served from `frontend/` |
| `GET /css/components.css` | `200`, `Content-Encoding: gzip`, `22,710 → 5,020 B` (−78 %), `Cache-Control: public, max-age=3600` |
| `GET /js/pages/search.js` | `200`, gzip, `Cache-Control: public, max-age=3600` |
| `GET /api/v1/cases/stats` | `200` proxied JSON `{"total_cases":607,…}`, `Cache-Control: no-store`, single `X-Content-Type-Options` |
| `GET /nope.html` | `404` (serves `frontend/404.html`) |
| Protocol | `HTTP/1.1` keep-alive, one `X-Content-Type-Options: nosniff` per response |
| Backend down | `502` with a plain-text explanation instead of a hang |

CSP is unaffected: same-origin `/api/*` satisfies `connect-src 'self'`, and the existing
page-level policies still permit `http://127.0.0.1:8000` for the legacy path.

## Deployment note

`serve.py` is a development server (threaded, no TLS, no rate limiting). For anything
public put nginx/Caddy in front of the same layout — static `frontend/` plus `/api` →
uvicorn — and let the proxy terminate TLS, gzip and cache. The frontend needs no change
because rule 4 already produces a same-origin base.

Remaining item from the delivery plan: vendoring Bootstrap/jQuery/Chart.js and adding
SRI hashes so the app does not depend on CDNs at runtime (currently every page loads
four of them).
