# Hybrid Search — Result Card: Code Review, Redesign & Implementation Plan

**Scope:** the single case result block on `frontend/search.html` (the "Hybrid Precedent Search" page) — the component shown in the screenshot for *In re Civil Appeal No 3843 of 2020*.
**Files involved**

| Layer | File | Lines |
|---|---|---|
| Markup shell | `frontend/search.html` | 1–263 (card container at 238) |
| Card renderer | `frontend/js/pages/search.js` | 148–260 (`renderResults`), actions 237–257 |
| Card styles | `frontend/css/components.css` | 245–288 (`.lg-case-card`), badges 200–243 |
| Theme tokens | `frontend/css/lexguard.css` | 1–82 |
| API client | `frontend/js/lexguard-api.js` | `search.query()` → `POST /api/v1/search/` |
| Backend | `backend/app/api/v1/endpoints/search.py` | 118–506; snippet builder 85–115 |
| Contract | `backend/app/schemas/search.py` | `SearchResultItem` |

---

## 1. What the card actually renders

`renderResults()` builds one big template literal per result and injects it into `#results-container` (`search.js:180`). Mapping the screenshot to code and data:

| Screenshot element | Source | Code |
|---|---|---|
| **In re Civil Appeal No 3843 of 2020** | `item.title`, linked to `case-viewer.html?id=` | 183–185 |
| **Supreme Court of India** (gold outline) | `item.court` → `courtBadgeClass()` | 187 (`lexguard-core.js:150`) |
| **Judgment** | `item.case_type` | 188 |
| **1961** | `item.year` | 189 |
| **Decided on Merits** | `item.outcome` via `badge-gold` | 190 |
| **green pill** | `item.precedential_status` | 191 |
| **1961 LexGuard HC FEE6CF7B** | `item.official_citation` | 193 |
| **Hon'ble Bench** | `item.judge` | 195 |
| Summary line | `item.summary` truncated to 240 chars (or `matched_snippets` if present) | 154–166 |
| **Constitution of India / Cr.P.C. / Section 482** | `item.act_tags` + `item.section_tags`, sliced to 6 | 168–177 |
| **Read Judgment / Compare / Copy Citation / 🔖** | static actions + handlers | 213–257 |
| **100% Match** (top right) | `Math.round(item.relevance_score * 100)` | 150, 199–203 |

The live record behind the screenshot (`backend/lexguard.db`):

```
title               In re Civil Appeal No 3843 of 2020
case_no             Civil Appeal No. 3843 of 2020
year / decision_date 1961 / 1961-10-22      ← should be 2020
judge               Hon'ble Bench           ← placeholder, not a judge
precedential_status Good Law
official_citation   1961 LexGuard HC FEE6CF7B   ← fabricated internal ID
outcome             Decided on Merits
summary             "Certified judgment from Supreme Court of India - Civil Appeal No. 3843 of 2020."
```

---

## 2. Problems with the current card

### 2.1 Data integrity (visible on screen)

| # | Problem | Evidence | Why it hurts |
|---|---|---|---|
| D1 | **Wrong year** — a 2020 appeal shows 1961 | `year=1961`, `decision_date=1961-10-22`, while `case_no` says 2020. **178 of the 434 rows whose case number ends in a year (41 %)** have a `year` field that contradicts it | Destroys credibility of a judicial product |
| D2 | **Fake "official citation"** | `official_citation` contains an internal `LexGuard` ID for **535 / 607** rows (`2026 LexGuard (Judg) 0249F2`) | Presenting an internal ID as an official citation is misrepresentation |
| D3 | **Placeholder judge** | `judge = "Hon'ble Bench"` for **308 / 607** rows | "Hon'ble Bench" is not a name; shows a person icon for nothing |
| D4 | **Status is self-asserted** | 397 rows "Good Law", 83 "Good Law (Binding Precedent)", only 2 "not checked"; Pydantic default is `"Good Law"` | A green trust pill on unverified data is a false assurance |
| D5 | **"100% Match" is not a match score** | For empty/browse queries the backend sets `relevance_score = 1.0` (search.py fast path) → every card shows 100 % | Users read it as semantic confidence; it is a placeholder |

### 2.2 Rendering / correctness

| # | Problem | Code |
|---|---|---|
| R1 | **Raw HTML injection** — `matched_snippets` is interpolated unescaped; the server wraps `<mark>` around *substrings of PDF text*, so any `<`, `>` or `&` in the judgment breaks the layout and is a stored-XSS vector | 156–162 |
| R2 | **Undefined CSS classes** — `fs-7` (score) and `btn-xs` are referenced but defined nowhere; `query-chip` (the suggestion chips above the form) is also undefined. `badge-gold` *is* defined (`lexguard.css:477`) but is misnamed: it paints a red outline, not gold | 190, 201; no matching selector in `components.css`/`lexguard.css` |
| R3 | **Green status pill renders as a blank chip** in the screenshot: `bg-success bg-opacity-15 text-success` + icon at `font-size:0.72rem` is low-contrast and indistinguishable from the "100% Match" green | 191 |
| R4 | **Citation copy format is non-standard**: `` `${title}, (${year}) ${court}` `` → "In re Civil Appeal No 3843 of 2020, (1961) Supreme Court of India" | 152 |
| R5 | Tags are acts + sections concatenated with no type distinction, no de-duplication, hard cap 6 | 168–177 |
| R6 | Two identical links to the same viewer (title + button); no `aria-label` on icon-only bookmark; 24 px hit target | 183, 214–227 |
| R7 | No `aria-live` on the results container; screen readers never hear "N results" | 262 |
| R8 | Bookmark button state is not restored (a bookmarked case still shows an empty bookmark) | 242–256 |

### 2.3 UX / design-system gaps

- No "why did this match?" affordance even though the API already returns `rrf_score`, `search_mode`, `matched_keywords`.
- No sorting (relevance / newest / most cited), no page-size control, no result count near the list.
- Card is visually flat: everything is a pill, so the eye has no hierarchy between *case identity*, *court/bench metadata*, *outcome*, and *actions*.
- Gold is used both as an accent and as text colour: `#d97706` on white is **3.19 : 1**, below WCAG AA 4.5 : 1. It is used for `text-warning` labels, "Suggested queries" text and icons.
- No skeleton loader — the list container is emptied and then re-filled, causing layout jump.
- Mobile: 8 badges wrap into 3–4 lines above the title's context; actions overflow.

---

## 3. Redesign goals

1. **Trust first.** Never display a synthetic value as an official one; mark provenance explicitly (`Repository ID` vs `Official citation`, `Verified` vs `Unverified`).
2. **Scan in 3 seconds.** Title → citation → court/bench → outcome → snippet → actions, in that order.
3. **Explain relevance.** Show *why* it matched (semantic / keyword / statute) instead of a fake percentage.
4. **Accessible by default.** WCAG 2.2 AA: contrast, 44 px targets, focus-visible, landmarks, live regions, keyboard order.
5. **Cheap to render.** One template component, event delegation, no per-card handler binding, no layout thrash.
6. **Reusable.** Same card component reused by bookmarks, admin queue and comparison tray.

---

## 4. Proposed card anatomy

```
┌────────────────────────────────────────────────────────────────────────────┐
│ ① In re Civil Appeal No 3843 of 2020                    [Open ↗] [⋯]      │
│    ② Civil Appeal No. 3843 of 2020 · Supreme Court of India · 2020         │
│ ③ [Supreme Court] [Judgment] [Decided on Merits] [◍ Unverified citation]  │
│                                                                            │
│ ④ "…the question of law raised in this appeal is whether…"  [p. 4]        │
│    matched: bail · Article 21 · Section 482          ← why-it-matched      │
│                                                                            │
│ ⑤ Constitution of India   Cr.P.C.   § 482                                  │
│ ────────────────────────────────────────────────────────────────────────── │
│ ⑥ [ Read judgment ]  [ Compare ]                    [Copy citation] [🔖]  │
└────────────────────────────────────────────────────────────────────────────┘
```

| Zone | Content | Notes |
|---|---|---|
| ① | Title (h3, 20 px semibold) + overflow menu | whole title is the link; one click target |
| ② | *Canonical citation line*: case number · court (short) · year | year from `decision_date` when available; flag mismatch instead of showing a wrong year |
| ③ | Chips: court, case type, disposition, **source state** | disposition stays; status chip becomes "Verified source / Not verified", not "Good Law" |
| ④ | Snippet with page chip + keyword chips | escaped text with server-provided highlight ranges |
| ⑤ | Act / section chips, max 4 + "+N" | separate act chips from section chips |
| ⑥ | Primary `Read`, secondary `Compare`, icon actions with tooltips | 44 px targets |

---

## 5. Implementation plan (phased)

### Phase 0 — Data sanity before touching pixels (½ day)

1. **Backfill year** for the 178 mismatched rows from `case_no` / `decision_date`; add a DB check constraint and a `source_verified_at` column.
2. **Relabel citations:** rename the UI label to "Repository ID" for the 535 rows whose citation is an internal `LexGuard` ID; only show "Official citation" when a reporter citation has been verified. Suggested migration:
   ```sql
   UPDATE cases SET official_citation = NULL
   WHERE official_citation ILIKE '%LexGuard%';
   -- or keep the value in a new column: internal_citation_id
   ```
3. **Null-out placeholders:** `UPDATE cases SET judge = NULL WHERE judge ILIKE '%Hon%Bench%' OR judge = 'Bench';`
4. **Status defaults:** remove the `precedential_status="Good Law"` default from `schemas/search.py`; emit `None` when unknown.
5. **Fix browse score:** in `search.py`, for the empty-query fast path return `relevance_score = None` (or `match_type="browse"`), not `1.0`.

### Phase 1 — Extract the component (1 day)

Create `frontend/js/components/case-card.js`:

```js
// frontend/js/components/case-card.js
(function (window) {
  'use strict';
  window.LG = window.LG || {};
  LG.components = LG.components || {};

  const esc = LG.utils.escapeHtml;

  function fmtDate(iso) { /* Intl.DateTimeFormat('en-IN', {dateStyle:'medium'}) */ }

  function citationLine(c) {
    const parts = [];
    if (c.case_no) parts.push(c.case_no);
    if (c.court) parts.push(c.court);
    const y = c.decision_date ? new Date(c.decision_date).getFullYear() : c.year;
    if (y) parts.push(String(y));
    return parts.join(' · ');
  }

  function chips(c) {
    const out = [];
    out.push(`<span class="lg-chip lg-chip--court">${esc(c.court)}</span>`);
    if (c.case_type) out.push(`<span class="lg-chip">${esc(c.case_type)}</span>`);
    if (c.disposition || c.outcome) out.push(`<span class="lg-chip lg-chip--outcome">${esc(c.disposition || c.outcome)}</span>`);
    out.push(c.source_verified
      ? `<span class="lg-chip lg-chip--verified"><i class="bi bi-patch-check-fill"></i> Verified source</span>`
      : `<span class="lg-chip lg-chip--unverified"><i class="bi bi-question-circle"></i> Citation unverified</span>`);
    return out.join('');
  }

  LG.components.caseCard = {
    render(c) {
      return `
        <article class="lg-case-card" data-case-id="${esc(c.id)}" aria-labelledby="t-${esc(c.id)}">
          <header class="lg-case-card__head">
            <h3 class="lg-case-card__title" id="t-${esc(c.id)}">
              <a href="case-viewer.html?id=${encodeURIComponent(c.id)}">${esc(c.title)}</a>
            </h3>
            ${c.relevance_label ? `<span class="lg-case-card__match">${esc(c.relevance_label)}</span>` : ''}
          </header>
          <p class="lg-case-card__meta">${esc(citationLine(c))}</p>
          <div class="lg-case-card__chips">${chips(c)}</div>
          ${c.snippet ? `
            <blockquote class="lg-case-card__snippet">
              ${c.snippet.html}
              ${c.snippet.page ? `<span class="lg-chip lg-chip--page">p. ${c.snippet.page}</span>` : ''}
            </blockquote>` : ''}
          ${(c.matched_keywords || []).length ? `
            <div class="lg-case-card__why">
              <span class="lg-case-card__why-label">Matched</span>
              ${c.matched_keywords.slice(0, 4).map(k => `<span class="lg-chip lg-chip--kw">${esc(k)}</span>`).join('')}
            </div>` : ''}
          <footer class="lg-case-card__actions">
            <a class="btn btn-sm btn-gold" href="case-viewer.html?id=${encodeURIComponent(c.id)}" aria-label="Read judgment: ${esc(c.title)}">
              <i class="bi bi-book-half" aria-hidden="true"></i> Read judgment
            </a>
            <a class="btn btn-sm btn-judicial-outline" href="case-compare.html?case1=${encodeURIComponent(c.id)}">
              <i class="bi bi-columns-gap" aria-hidden="true"></i> Compare
            </a>
            <div class="lg-case-card__actions-end">
              <button type="button" class="btn btn-sm btn-judicial-outline js-copy-citation"
                      data-citation="${esc(c.citation_copy)}" aria-label="Copy citation">
                <i class="bi bi-quote" aria-hidden="true"></i><span class="d-none d-md-inline"> Copy citation</span>
              </button>
              <button type="button" class="btn btn-sm btn-judicial-outline js-bookmark"
                      data-id="${esc(c.id)}" aria-pressed="false" aria-label="Save to bookmarks">
                <i class="bi bi-bookmark" aria-hidden="true"></i>
              </button>
            </div>
          </footer>
        </article>`;
    }
  };
})(window);
```

Then in `search.js`:

```js
$resultsContainer.html(results.map(LG.components.caseCard.render).join(''));
$resultsContainer.attr('aria-live', 'polite');
// one delegated handler for the whole list (no rebinding per render)
$resultsContainer
  .off('.casecard')
  .on('click.casecard', '.js-copy-citation', function () {
    LG.utils.copyToClipboard($(this).data('citation'));
  })
  .on('click.casecard', '.js-bookmark', function () {
    const $b = $(this), id = $b.data('id');
    if (!LG.session.isAuthenticated()) return LG.toast('Sign in to bookmark.', 'warning');
    LG.api.bookmarks.add(id, 'Saved from Hybrid Search')
      .done(() => { $b.attr('aria-pressed', 'true').find('i').attr('class', 'bi bi-bookmark-fill text-warning'); })
      .fail(() => LG.toast('Already bookmarked.', 'info'));
  });
```

### Phase 2 — Visual system (1–2 days)

New tokens in `lexguard.css` (fixes AA contrast):

```css
:root {
  --lg-gold: #b45309;          /* 5.02:1 on white — AA for text */
  --lg-gold-bg: #fffbeb;
  --lg-success: #047857;       /* 5.48:1 on white */
  --lg-ink: #0f172a;
  --lg-ink-2: #475569;         /* 7.0:1 on white */
  --lg-border: rgba(153, 27, 27, .14);
  --lg-radius: 12px;
  --lg-card-pad: clamp(1rem, 2.2vw, 1.5rem);
}
```

```css
.lg-case-card {
  background: #fff;
  border: 1px solid var(--lg-border);
  border-radius: var(--lg-radius);
  padding: var(--lg-card-pad);
  transition: box-shadow .15s ease, border-color .15s ease;
}
.lg-case-card:hover { border-color: #991b1b; box-shadow: 0 10px 28px -12px rgba(153,27,27,.25); }
.lg-case-card:focus-within { outline: 3px solid rgba(153,27,27,.35); outline-offset: 2px; }

.lg-case-card__title { font-size: 1.15rem; font-weight: 700; line-height: 1.3; margin: 0; }
.lg-case-card__title a { color: var(--lg-ink); text-decoration: none; }
.lg-case-card__title a:hover { color: #991b1b; text-decoration: underline; text-underline-offset: 3px; }

.lg-case-card__meta { color: var(--lg-ink-2); font-size: .85rem; margin: .35rem 0 .6rem; }

.lg-chip {
  display: inline-flex; align-items: center; gap: .3rem;
  font-size: .72rem; font-weight: 600; line-height: 1;
  padding: .35rem .55rem; border-radius: 999px;
  border: 1px solid var(--lg-border); background: #f8fafc; color: var(--lg-ink-2);
}
.lg-chip--court   { background: #fef2f2; border-color: rgba(153,27,27,.25); color: #991b1b; }
.lg-chip--outcome { background: var(--lg-gold-bg); border-color: rgba(180,83,9,.3); color: var(--lg-gold); }
.lg-chip--verified   { background: #ecfdf5; border-color: #a7f3d0; color: var(--lg-success); }
.lg-chip--unverified { background: #f8fafc; border-style: dashed; color: #475569; }
.lg-chip--page { margin-left: .35rem; font-variant-numeric: tabular-nums; }

.lg-case-card__snippet {
  margin: .75rem 0; padding: .65rem .85rem;
  border-left: 3px solid rgba(153,27,27,.35);
  background: #fffbfb; color: #1f2937; font-size: .88rem; line-height: 1.65;
}
.lg-case-card__snippet mark { background: #fde68a; color: #7c2d12; padding: 0 .15rem; border-radius: 3px; }

.lg-case-card__actions { display: flex; flex-wrap: wrap; gap: .5rem; align-items: center;
  border-top: 1px solid #f1f5f9; padding-top: .75rem; margin-top: .75rem; }
.lg-case-card__actions .btn { min-height: 38px; }
.lg-case-card__actions-end { margin-left: auto; display: flex; gap: .5rem; }

@media (max-width: 575.98px) {
  .lg-case-card__actions .btn span { display: none; }
  .lg-case-card__actions .btn { padding-inline: .6rem; }
}
@media (prefers-reduced-motion: reduce) {
  .lg-case-card { transition: none; }
}
```

### Phase 3 — Backend contract (1–2 days)

New shape for `SearchResultItem` (additive, backward compatible):

```python
class Snippet(BaseModel):
    page: int | None = None
    text: str                     # plain text only
    highlights: list[list[int]]   # [[start, end], ...] ranges in `text`

class SearchResultItem(BaseModel):
    ...
    relevance_score: float | None = None
    match_type: Literal["browse", "semantic", "keyword", "statute", "hybrid"] = "hybrid"
    relevance_label: str | None = None      # "Strong match", "Related", ...
    snippet: Snippet | None = None
    matched_keywords: list[str] = []
    citation_display: str | None = None     # safe canonical line
    source_verified: bool = False
    repository_id: str | None = None        # replaces fake official_citation
```

Server-side snippet builder (`search.py:85`) should stop emitting HTML:

```python
def _extract_matched_snippets(text, tokens, max_snippets=2):
    for line in text.splitlines():
        ...
        spans = []
        for tok in tokens:
            for m in re.finditer(re.escape(tok), line, re.I):
                spans.append([m.start(), m.end()])
        snippets.append(Snippet(page=current_page, text=line[:400], highlights=spans))
```

Client renders highlights by slicing text and escaping each segment — XSS is structurally impossible.

### Phase 4 — Polish & measurement (1 day)

- Skeleton cards while loading (3 placeholders).
- Result toolbar: `N results · sorted by relevance`; sort dropdown (`Relevance | Newest | Most cited`).
- "Why it matched" chips from `match_type` + `matched_keywords`.
- Bookmark state hydration via `GET /bookmarks` ids.
- Telemetry (optional): `search_result_click`, `read_click`, `compare_click` to measure the redesign.

---

## 6. Acceptance criteria

| Area | Criterion |
|---|---|
| Data | No card shows a year conflicting with `case_no`; no field labelled "official citation" that is actually an internal `LexGuard` ID; no "Hon'ble Bench" |
| Truthfulness | Match label shown only for non-browse queries; unverified sources visibly marked |
| Security | Payload `<img src=x onerror=alert(1)>` inside a judgment renders as text (test in `tests/` + manual) |
| A11y | axe DevTools 0 critical issues; tab order reaches title → Read → Compare → Copy → Bookmark; visible focus ring; results announced |
| Responsive | 320 px: title wraps, chips wrap, actions never overflow; tap targets ≥ 44 px |
| Contrast | All text ≥ 4.5:1 (gold token changed to `#b45309`) |
| Performance | Card list of 10 renders < 16 ms; no handler growth across 5 searches (delegation) |
| Reuse | Same component used by `bookmarks.html` and the compare tray |

---

## 7. What to change first (ordered, minimal diff)

1. `search.js:159` — escape snippet text (hotfix, 2 lines) and `search.js:150` — hide match badge for browse queries.
2. `search.py` fast path — `relevance_score = None`.
3. `components.css` — add the missing `btn-xs`, `fs-7`, `query-chip` definitions (or delete their usage); `badge-gold` exists but is misnamed, so either rename it or restyle it as a real gold token.
4. Data migration for year / citation / judge placeholders.
5. Extract `case-card.js` + delegated handlers (Phase 1), then style tokens (Phase 2).

These five steps give ~80 % of the perceived quality improvement with no backend redesign.
