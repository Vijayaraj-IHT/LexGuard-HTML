# Case-file pattern analysis & key sets

**Scope:** how the judgment/order PDFs that enter LexGuard are actually *drafted*,
how to recognise each drafting template from the file itself, and which key sets
(anchor definitions) to load so that case-fact extraction is driven by the
document's own structure instead of one global bag of regexes.

**Artifacts**

| Artifact | Purpose |
|---|---|
| `backend/app/services/case_pattern_service.py` | Runtime engine: layout fingerprint → drafting profile → key set → section map → facts + fact sheet |
| `scripts/analyse_case_file_patterns.py` | Corpus sweep: per-file detection, key coverage, facts result, JSON + Markdown report |
| `docs/pattern_analysis/case_pattern_report.{json,md}` | Sweep output (regenerate with the analyser). Latest verified `storage/cases` run: **596 PDFs scanned**, **595 readable unique documents**, 39 profiles, 1 unreadable file, **99.5 %** specific-profile coverage |
| `backend/tests/test_case_pattern_service.py` | Fixture/profile tests, registry-merge, repair-gate, fact-sheet and corpus smoke tests |
| `backend/app/services/extraction_service.py` | Pass 1b — applies the key set to harden identity fields and lift `facts` |

---

## 1. Why patterns, not one big regex

The current `storage/cases` sweep covers **596 PDFs → 595 readable unique
documents** (one corrupt file is recorded as a failure; the separate seed corpus
adds 29 registry fixtures). They come from **20+ High Court registries plus the
Supreme Court, NCLAT and one law-report digest**, and they are drafted to
**at least 28 distinguishable templates**. Every template writes the same field
differently:

| Field | Madras Principal Seat | Madras Madurai Bench | Chhattisgarh | Patna | Punjab & Haryana |
|---|---|---|---|---|---|
| Decision date | `DATED: 09-10-2026` | `Date : 09.10.2026` | `Order passed on : 15.06.2026` | `dt.23-06-2026` (running header) | `Date of Decision:- 17.08.2026` |
| Reserved date | `RESERVED ON : 01.10.2026` | `RESERVED ON: 19.08.2026` | `Order Reserved on : 09.04.2026` | — | — |
| Coram | `CORAM` + `THE HON'BLE MR.JUSTICE …` | `PRESENT` + ``The Hon`ble Mr.Justice …`` | `Hon'ble Shri Justice …` | `HON'BLE MR. JUSTICE …` | `CORAM: HON'BLE MS. JUSTICE …` + `, J.` signature |
| Party designator | `..Petitioner(s)` | `... Petitioners/ Accused 5 & 3` | `--- Petitioner(s)` | `...  ...  Petitioner/s` | `… Petitioners` |
| Counsel block | `For Petitioner(s):` | `For Petitioners: Mr.…` | `For Petitioner` (newline) `:` | `Appearance :` | `Present:-` |
| Prayer | `PRAYER:` | `PRAYER :-` | quoted `relief(s):- “10.1 …”` | numbered `(i)…(vii)` | prose "filed this writ petition for …" |
| Signature | `JUDGE` | `K.MURALI SHANKAR,J` + `ORDER IN` | `Sd/- (Name) Judge` | `(Name) JUDGE` | `(Name) JUDGE` + DSC attestation |

A single regex set therefore either misses fields or, worse, picks the *wrong*
one — e.g. capturing the `RESERVED ON` date as the decision date, or a case
number cited in the body instead of the caption.

---

## 2. The model: three independent layers

```
PDF ──► ① layout fingerprint ──► ② drafting profile ──► ③ key set ──► fields
         (how to read it)         (which template)      (which anchors)
```

1. **Layout fingerprint** — page geometry, text-layer quality, dominant fonts
   (serif vs monospace), clipped/double-drawn text, columnar blocks, watermark,
   page-clock style, repeated running headers. This decides *how the text must be
   read*, before any legal parsing.
2. **Drafting profile** — a weighted signal set (required + supporting + negative
   evidence) that identifies the registry template and its seat.
3. **Key set** — the per-profile shortlist of anchors, grouped into 14
   categories, each key carrying its own confidence and extraction window.

---

## 3. Detected profiles (full corpus)

39 profiles, of which 4 are format profiles (a *shape* any court can print) and 2
are guards. Counts are from the sweep in
`docs/pattern_analysis/case_pattern_report.json`:

| Profile | Docs | Court | What identifies it | Facts strategy |
|---|---:|---|---|---|
| `BRIEF-CARD` | 179 | Unspecified Court | `CASE NO: … (YEAR: …)` + one-line `CORAM:` + `JUDICIAL HEADNOTE & SUMMARY` / `RATIO DECIDENDI` / `OPERATIVE ORDER` | `headed_facts` |
| `BOMBAY-HC` | 46 | Bombay High Court | `HIGH COURT OF (JUDICATURE AT) BOMBAY` + `<case>.doc` working header + `CORAM : NAME, J.` + `DATE :` | `coram_order` |
| `GAUHATI-HC` | 36 | Gauhati High Court | `THE GAUHATI HIGH COURT (HIGH COURT OF ASSAM, NAGALAND, MIZORAM AND ARUNACHAL PRADESH)` + `GAHC…` code + `Case No. : <type>/<n>/<year>` | `numbered_paras` |
| `GUJARAT-HC` | 29 | Gujarat High Court | `HIGH COURT OF GUJARAT AT AHMEDABAD` + `R/CR.MA/<n>/<year>` + `ORDER DATED:` | `order_sheet` |
| `MHC-MB-CORAM-ORDER` | 28 | Madras High Court | `BEFORE THE MADURAI BENCH …` + `CORAM` + `DATED:` | `coram_order` |
| `MHC-PS-CORAM-ORDER` | 28 | Madras High Court | `IN THE HIGH COURT OF JUDICATURE AT MADRAS` + `CORAM` + `DATED: dd-mm-yyyy` | `coram_order` |
| `ORISSA-HC` | 22 | Orissa High Court | `HIGH COURT OF ORISSA AT CUTTACK` + `ABLAPL No.<n> of <year>` + `..... Petitioner` + `Represented by Adv. -` | `order_sheet` |
| `TELANGANA-HC` | 21 | Telangana High Court | `HIGH COURT FOR THE STATE OF TELANGANA` + `(Special Original Jurisdiction)` + `WEDNESDAY, THE … DAY OF …` | `reserved_judgment` |
| `MADRAS-DAILY-ORDER` | 20 | Madras High Court | `Court No.8` / `S/L 34` + `CRM (M) <n> of <year>` + `In Re : An application for bail under Section 483 …` | `order_sheet` |
| `MHC-MB-CRIM-JURIS` | 18 | Madras High Court | Madurai Bench + `( Criminal Jurisdiction )` + `PRESENT` + `Date : dd.mm.yyyy` | `order_sheet` |
| `MHC-MB-RESERVED-JUDGMENT` | 16 | Madras High Court | `MADURAI BENCH` + `Reserved on` / `Pronounced on` | `reserved_judgment` |
| `PATNA-CWJC-JUDGMENT` | 16 | Patna High Court | `JUDICATURE AT PATNA` + `Civil Writ Jurisdiction Case No.` + `====` banners + `Patna High Court … dt.` | `headed_facts` |
| `TRIPURA-HC` | 16 | Tripura High Court | `HIGH COURT OF TRIPURA AGARTALA` + `TRHC…` code + `… APPELLANT-OPPOSITE PARTY(S)` + `VERSUS` | `coram_order` |
| `ALLAHABAD-HC` | 15 | Allahabad High Court | `HIGH COURT OF JUDICATURE AT ALLAHABAD` + `Neutral Citation No. - YYYY:AHC-…` | `headed_facts` |
| `RAJASTHAN-HC` | 13 | Rajasthan High Court | `HIGH COURT OF JUDICATURE FOR RAJASTHAN` + `[YYYY:RJ-JP:n]` + `CNR: RJHC… | URN: …` | `coram_order` |
| `CGHC-BILASPUR-ORDER` | 11 | High Court of Chhattisgarh | `HIGH COURT OF CHHATTISGARH AT BILASPUR` + `2026:CGHC:n` + `AFR/NAFR` | `numbered_paras` |
| `SC-GENERIC` | 10 | Supreme Court of India | `SUPREME COURT OF INDIA` caption | `reserved_judgment` |
| `JK-LADAKH-HC` | 9 | High Court of Jammu & Kashmir and Ladakh | `HIGH COURT OF JAMMU & KASHMIR AND LADAKH AT …` + `Uploaded on:` + `Through: Mr. …, Advocate` + `v/s` | `coram_order` |
| `KARNATAKA-HC` | 8 | Karnataka High Court | `HIGH COURT OF KARNATAKA` + `DATED THIS THE <n>TH DAY OF <month>` + `- 1 -` page clock | `reserved_judgment` |
| `CALCUTTA-HC` | 6 | Calcutta High Court | `IN THE HIGH COURT AT CALCUTTA` + `Appellate Side` + `Between:` / `-Vs-` | `order_sheet` |
| `MEGHALAYA-HC` | 5 | Meghalaya High Court | `HIGH COURT OF MEGHALAYA` + `Serial No.<n>` + `Regular List` + `Date of Decision:` + `Uploaded on:` | `coram_order` |
| `MHC-PS-RESERVED-JUDGMENT` | 5 | Madras High Court | `JUDICATURE AT MADRAS` + `RESERVED ON` / `PRONOUNCED ON` | `reserved_judgment` |
| `ANDHRA-HC` | 4 | Andhra Pradesh High Court | `HIGH COURT OF ANDHRA PRADESH` + `APHC…` code + `AT AMARAVATI` + `THE HONOURABLE SRI JUSTICE …` | `reserved_judgment` |
| `DAILY-CAUSE-ORDER` | 4 | High Court (inferred from caption) | `Court No. <n>` / `Ct. No. <n>` + `(Vacation Bench)` / `(Allowed)` + `In Re : An application for bail …` | `order_sheet` |
| `HIMACHAL-HC` | 4 | Himachal Pradesh High Court | `( YYYY:HHC:n )` + `Reserved on:` + `Date of decision:` + `Date of uploading on website:` | `reserved_judgment` |
| `PHHC-CWP-COLUMNAR` | 4 | Punjab & Haryana High Court | `HIGH COURT OF PUNJAB AND HARYANA AT CHANDIGARH` + `CWP-…(O&M)` + `Date of Decision:-` + DSC attestation | `columnar_judgment` |
| `BOMBAY-NEUTRAL-CITATION` | 3 | Bombay High Court | neutral citation `YYYY:BHC-<BENCH>:<n>` printed on every page + `WP <n>-<year>` clock | `coram_order` |
| `CALCUTTA-CAUSELIST` | 3 | Calcutta High Court | cause-list head (`Ct.No.07`, `Sl. No.`, `(NMD/D.Hira)`) + `WPA <n> of <year>` + `Vs.` | `order_sheet` |
| `JHARKHAND-HC` | 3 | Jharkhand High Court | `HIGH COURT OF JHARKHAND AT RANCHI` + `2026:JHHC:…-DB` + `--- Opposite Party` | `coram_order` |
| `DELHI-HC` | 2 | Delhi High Court | `IN THE HIGH COURT OF DELHI AT NEW DELHI` + `$~` reportability head + `Reserved on` / `Pronounced on` | `reserved_judgment` |
| `GENERIC-HC` | 2 | High Court | fallback only — never competes for a document | `generic` |
| `OFFICE-NOTES` | 1 | — | registry sheet `Office Notes, reports, orders or proceedings` + `Date or directions and COURT'S OR JUDGE'S ORDERS` + a bare `UKHC…`/`TRHC…` code | `order_sheet` |
| `ALLAHABAD-CASELINE` | 1 | Allahabad High Court | pure docket `Court No. - 26`, `Case :- …`, `Applicant :-`, `Opposite Party :-` — the court name is **not printed** | `headed_facts` |
| `KERALA-HC` | 1 | Kerala High Court | `HIGH COURT OF KERALA AT ERNAKULAM` + `THE HONOURABLE MR.JUSTICE …` + `NTH DAY OF <MONTH>, <year> / NTH <MALAYALAM MONTH>, <era>` | `reserved_judgment` |
| `LAW-REPORT-REPRINT` | 1 | — | `<appellant> vs <respondent> on <date>` + `Equivalent citations:` — a digest reprint, not a live order | `headed_facts` |
| `MADRAS-REVIEW-SLIP` | 1 | Madras High Court | `R.V.W. <n> of <year>` + `With` + `CAN <n> of <year>` | `order_sheet` |
| `MADRAS-SHORT-ORDER` | 1 | Madras High Court | `WMP. No.<n> of <year> in W.P. No.<n> of <year>` + `Ordered.` | `order_sheet` |
| `NON-JUDGMENT` | 1 | — | `Project Overview & Objectives` / `Tech Stack` / `System Architecture` headings — not a court document at all | `none` |
| `UTTARAKHAND-HC` | 2 | Uttarakhand High Court | `HIGH COURT OF UTTARAKHAND AT NAINITAL` + `UKHC…` code + `Reserved on` / `Delivered on` | `reserved_judgment` |

**Coverage: 593/596 unique attempted documents (99.5 %) matched a specific
profile**; among the 595 readable documents this is 593/595 (99.7 %). Only 2
readable documents fall back to `GENERIC-HC`, and the single corrupt PDF is
reported separately instead of being force-classified. Before this extension the
fallback was 443/596 — the engine only knew Madras, Chhattisgarh, Patna and
Punjab & Haryana.

Two guard profiles earn their place:

* `NON-JUDGMENT` — one PDF in `storage/cases/` is a product/design brief, not an
  order. It is now labelled instead of being force-fitted to a court profile.
* `LAW-REPORT-REPRINT` — a pre-Independence digest reprint (`<party> vs <party>
  on <date>` + `Equivalent citations:`), which has no live caption at all.

### Format profiles vs registry profiles

The important structural finding: **many drafts identify a *format*, not a
court.** Brief cards (`CASE NO: … (YEAR: …)` + `RATIO DECIDENDI`), certified
cause-list order sheets (`Court No. 8` + `(Allowed)` + `In Re : An application for
bail …`), registry office-notes sheets and Allahabad-style dockets deliberately do
**not** print a court caption — the court is inferred from the caption body
(`COURT_NAME_MAP`) or from the registry code prefix (`REGISTRY_COURT`, e.g.
`UKHC010091362026` → Uttarakhand, `TRHC…` → Tripura). 179 of the 595 documents are
brief cards spanning the Supreme Court (159), Delhi (8), Madras (4), Bombay (2),
Allahabad, Gujarat, Karnataka, Kerala and NCLAT.

### Scoring and acceptance

* Hard gate: every `required` signal must match.
* `score = Σ required weights + Σ matched supporting weights − Σ matched negative weights`
  (layout signals participate on the same scale).
* Ranking is by **absolute evidence**, normalised score as tie-break, so the
  generic profile can never win by being trivially "100 % complete".
* Accept when `normalised ≥ 0.40` **or** the required court-caption signal alone
  fires (`net ≥ 1.0`). Registry office-notes exports often print nothing but the
  court name and a case number, and sending those to the generic fallback loses
  the court attribution entirely.
* Below both thresholds the file falls back to `GENERIC-HC` with the runner-up
  reported for triage.

Detection is fully deterministic and offline (regex + geometry only), which keeps
ingestion auditable.

---

## 4. Drafting/layout hazards found in the corpus

| Hazard | Where | Effect | Handling |
|---|---|---|---|
| **Shifted duplicate draw** (every line drawn twice at a small offset, so the extractor emits `IN` / `IN THE` / `THE HIGH` / `HIGH COURT` …) | Bombay `.doc`/`.odt` exports | a 43-page order explodes into thousands of shard lines; captions and dates never sit on one line | `_dedupe_lines` merges only genuine shard chains: a run of ≥4 lines whose first word repeats the previous line's last word, or a shorter run with a multi-word suffix/prefix overlap. Ordinary prose coincidences and nothing outside a run are left alone |
| **Two-column judgment body** | Patna, older reported judgments | left and right columns interleave line by line, producing sentences that jump between unrelated clauses | `_columnar_page_text` rebuilds the page column-by-column, but only when `_detect_columnar` sees at least two tall blocks sharing a vertical band on opposite sides of the gutter |
| **Cover-page-only PDFs** (caption + CNR, no body) | 32 documents (`SC_*` brief dockets, `MADRAS-DAILY-ORDER`, `MADRAS-SHORT-ORDER`) | zero facts and zero sections, which looks like an extraction bug | `analyse_pdf` now returns `text_status: "insufficient_text"` with `text_chars`, and the sweep lists them separately |
| **Double-drawn text layer** (1–2 pt duplicate render, words split across clips) | Punjab & Haryana, Bombay `.doc` captions | `IN T + THE + HIGH … + AN + ND` | `_choose_page_text` is gated by severe clipping (`clipped/blocks ≥ 0.25`) **or** genuine overlapping word runs. Overlapping runs are accepted when continuity improves; severe clipping alone must also look like a sharded blank-line layer and improve ≥1.4×, so clean Madras/Supreme Court judgments and table-heavy pages stay verbatim |
| **Monospace registry template** | Gujarat, Orissa, CGHC | different fonts/metrics | `layout:mono_font` signal |
| **Legal-size page** (612×1008) | CGHC, Patna, P&H | — | `layout:legal_page` |
| **JUDIS watermark** (`mhc.tn.gov.in/judis`) and registry footers | Madras, Allahabad, Delhi | pollutes body text and embeddings | `noise` keys strip them before parsing |
| **Page clocks** (`Page N of M`, `n/N`, `1 of 8`, `- 1 -`, `WP.358.2026.doc`) | most registries | break paragraph numbering; also a reliable *profile* signal | per-profile `noise` + `identity` keys |
| **Running headers** (`Patna High Court CWJC … dt.…`, `WP 207-2026 / Page 1 of 10 / 2026:BHC-GOA:2108`) | Patna, Bombay | repeated mid-sentence; the *first* occurrence carries the case number | repeated-edge-line detection keeps the first occurrence only |
| **Address blocks inside party captions** | CGHC, Patna, Orissa | party extraction grabs `R/o Ward No. 02 …` | caption party extractor rejects address-shaped lines and cuts at `S/o · D/o · Aged · R/o · Rep by` |
| **Filename prefixes lie** | `storage/cases/*` | `DHC_1973_Appeal…` is a Supreme Court brief card; many `BHC_*` files are Orissa/Gauhati/Allahabad orders | never key off the filename — all classification is text/geometry based |

Text-quality states across the latest sweep: `good` 559, `repaired` 5,
`ocr_required` 31 (the flag exists for scans; no OCR stage is wired in). The
repair gate is intentionally strict: the previous 0.15 clipped-block threshold
re-flowed hundreds of clean single-column pages; the current gate leaves Madras,
Madurai and Supreme Court judgment text verbatim while still repairing the
double-drawn Punjab & Haryana and Bombay `.doc` layers.

### Geometric repair acceptance gates

`_choose_page_text()` separates *suspicion* from *acceptance*:

1. **Suspicion** — attempt repair only when `clipped / len(blocks) >= 0.25`, or
   `_has_double_drawn_runs()` sees a genuine double-drawn layer (≥6 overlapping
   neighbouring word pairs across ≥2 baselines, with near-coincident or
   character-overlapping fragments), or the raw text layer is empty.
2. **Acceptance** — keep the repaired text only when it preserves content
   (≥25 % of raw characters) and either:
   - the page is genuinely double-drawn and line continuity improves; or
   - the page is severely clipped **and** looks like a sharded blank-line layer
     (≥30 % blank lines, ≥50 % short fragments, low raw line score) **and**
     continuity improves ≥1.4×.

This is why a clean page with many narrow caption blocks or a table is not
re-flowed, while `28_cwp-1744-2024-ph.pdf` and the Bombay `WP.358.2026.doc`
caption are repaired.

---

## 5. Key sets

Every profile resolves to a key set with 14 categories. A key is
`{category, anchors[], window, confidence, note}`; `window` is `line` (first
matching line), `block` (anchor plus the following lines) or `span` (anchor to
the next stop anchor).

### Composition: one shared set + per-registry extras

Adding 20 registries to one flat key set would have let Bombay anchors fire on
Allahabad documents. Instead:

* `KEY-HC-COMMON` — the superset of anchors that hold across registries
  (caption furniture, `PRAYER:`, `J U D G M E N T`, `In the result`, `JUDGE`).
* `KEY-EXTRA-<COURT>` — a small set of registry-specific anchors
  (`ABLAPL No.`, `CORAM : NAME, J.`, `Case :-`, `Serial No.`, `R.V.W.` …).
* Court profiles declare `key_set: ["KEY-HC-COMMON", "KEY-EXTRA-<COURT>"]`, and
  `key_set_for()` merges them: same key id → anchors unioned, confidence = max,
  inputs never mutated. `Detection.key_set_id` keeps the primary id for storage
  and `key_set_ids` records the full composition.

22 key sets exist: `KEY-HC-COMMON`, 11 court extras (`ALLAHABAD`, `BOMBAY`,
`CALCUTTA`, `GAUHATI`, `JK`, `KARNATAKA`, `MADRAS-INRE`, `MEGHALAYA`, `ORISSA`,
`TELANGANA`, `BRIEF-CARD`), the 8 originals and `KEY-GENERIC`.

| Category | What it yields | Example anchors |
|---|---|---|
| `identity` | case number, CNR, neutral citation, registry code, page clock | `CNR: {HCMA012161402026}`, `2026:CGHC:36890`, `ABLAPL No.11991 of 2026`, `UKHC010091362026` |
| `forum` | court line, bench, jurisdiction banner, reportability | `BEFORE THE MADURAI BENCH …`, `( Criminal Jurisdiction )`, `KOHIMA BENCH`, `NAFR` |
| `dates` | reserved, pronounced/decision date | `RESERVED ON:`, `Date : dd.mm.yyyy`, `DATE : OCTOBER 22, 2026.`, `DATED THIS THE 14TH DAY OF …` |
| `coram` | judge(s), signature-name form | `CORAM` + `HON'BLE …JUSTICE`, `CORAM : MILIND N. JADHAV, J.`, `, J.` |
| `parties` | petitioner, respondent, versus, designators, accused tags | `..Petitioner(s)`, `Applicant :-`, `..... Petitioner`, `--- Opposite Party` |
| `counsel` | appearance/for-party blocks | `For Petitioner(s):`, `Through: Mr. …, Advocate`, `Represented by Adv. -` |
| `relief` | verbatim prayer | `PRAYER:`, `relief(s):- “`, `(i) Also for declaring …` |
| `facts` | factual-matrix start/end anchors, explicit heading | `ORDER`, `J U D G M E N T`, `Brief Facts Of Case`, end anchors `I have heard`, `learned counsel` |
| `issues` | framed questions | `Whether`, `points for consideration` |
| `reasoning` | discussion start | `I have heard`, `Having heard`, `Consideration` |
| `operative` | result/order paragraph | `In the result`, `stands dismissed`, `(Allowed)`, `Ordered.` |
| `signature` | judge sign, attestation, pre-delivery order | `JUDGE`, `Sd/-`, `(Name) JUDGE`, `Uploaded on:` |
| `noise` | watermarks, page clocks, rules, running headers | `mhc.tn.gov.in/judis`, `Page N of M`, `====`, `-Vs-` |
| `statute_style` | citation idiom of the template | `Sections … read with … of the Act`, `Articles 226`, `Section 483 BNSS` |

### Anchor hit rates on the 595-document sweep

| Key | Documents |
|---|---:|
| `forum.court_line` | 563 |
| `signature.judge_sign` | 562 |
| `identity.case_no` | 454 |
| `parties.versus` | 409 |
| `statute_style.sections` | 397 |
| `parties.petitioner` | 394 |
| `parties.respondent` | 344 |
| `facts.start` | 325 |
| `dates.decision_date` | 317 |
| `operative.conclusion` | 293 |
| `facts.end` | 292 |
| `counsel.counsel_for` | 253 |
| `forum.jurisdiction` | 223 |
| `coram.judge` | 222 |
| `relief.prayer` | 218 |
| `coram.coram_inline` | 200 |

Mean key coverage per profile sits between 0.06 and 0.52. Coverage is not a
quality score — a one-page brief card has no prayer, no reserved date and no
issues heading; a certified order sheet has no parties block. It is the
*shortlist* the extractor is allowed to rely on.

Two rules matter when reading the shortlist:

* **Caption scoping** — identity anchors are searched in the first 2 500
  characters first (`in_caption: true`). Body hits are only used if the caption
  has none; body text cites *other* case numbers, which is how `CWP-1744-2024`
  could otherwise be replaced by a cited `CWP No.12741 of 2009`.
* **Confidence-weighted merging** — the key set overrides a Pass-1 value only
  when Pass-1 is empty, a placeholder, low-confidence, or year-inconsistent with
  the caption.

---

## 6. Case-facts extraction

Facts are the field Pass 1 never produced (`fact`/`facts` were empty, and the
upload endpoint silently fell back to the *prayer*). The pattern layer now
produces a bounded factual matrix plus a structured fact sheet.

### Strategy ladder

1. **Explicit registry heading** — `Brief Facts Of Case` (Patna), `Facts of the
   case` — highest confidence.
2. **Profile anchors** — `ORDER` / `ORDER :` / `J U D G M E N T` /
   `Order on Board` / `, J.` signature line, closed by the profile's end anchors
   (`I have heard`, `learned counsel`, `Consideration`, `Discussion`).
3. **Rolling paragraph runs** — for the majority of Madras orders that print no
   heading at all, every plausible run of contiguous narrative paragraphs is
   proposed.
4. **Post-caption body** — for reserved judgments with no `JUDGMENT` heading:
   the first narrative paragraph after the last prayer unit.

Each candidate is scored on **factuality** (dates, crime/CC numbers, place
tokens, police stations, action verbs such as *arrested / seized / filed /
remanded*) minus **argument markers** (*SCC, held that, it is settled,
submissions, whether, prays*), with heavy penalties for caption furniture
(`..Petitioner`, `For Petitioners:`). The winner is trimmed to a paragraph edge
and capped at 4 500 characters.

### Results on the sweep (595 unique documents)

| Strategy | Documents |
|---|---:|
| `anchored_span` | 227 |
| `paragraph_scan` | 202 |
| `explicit_heading` | 130 |
| `order_sheet` | 21 |
| `reserved_judgment` | 10 |
| `post_caption_body` | 5 |

* **0 of 563 body-text documents return empty facts** (mean 1 938 chars, median
  1 421, min 135, max 7 114). The remaining 32 are cover-page-only PDFs, now
  labelled `insufficient_text` instead of silently producing nothing.
* Brief cards (179) extract 636 chars on average — they have no factual narrative,
  only a headnote, so `headed_facts` correctly returns the summary section.

Example fact sheets (dates / crime numbers / police stations / places / offences):

* *CRL OP 26220/2026 (Madras)* — 9 dates, `Crime No.120 of 2025`, `C.C.No.597 of
  2026`, Tiruvallur, `Sections 8(c) read with 20(b)(ii)(C), 25 and 29(1) of the Act`,
  `in custody since then`.
* *CRL OP(MD) 23127/2026 (Madurai)* — `Crime No.206 of 2026`,
  `Mallanginar` police station (merged from the respondent caption even though it
  sits outside the factual matrix), `Section 25(1B)(b) of Arms Act`,
  `remanded to judicial custody`.
* *WPS 5957/2023 (CGHC)* — 8 dates, `Section 34 of the Rights of Persons with
  Disabilities Act, 2016`.
* *WP.358.2026 (Bombay)* — dates and `Directorate of Enforcement` recovered from a
  shift-repaired text layer that previously produced only shard lines.

Fact-sheet fields: `dates`, `crime_numbers`, `police_stations`, `places`,
`offences`, `custody`, `arrest`, `amounts`. `crime_numbers` covers Crime / Cr /
FIR / C.C. / R.C. / charge-sheet / final-report numbers; `police_stations`
captures both `X Police Station` and `P.S. X` forms and rejects case-number /
institution-shaped false positives. They are returned alongside the facts text
and are the natural feed for the draft-assistant gap analysis and precedent
search.

---

## 7. Using it

```bash
# full-corpus sweep (storage/cases is the default) — ~4–5 minutes for 596 PDFs
# exits 0 when >=99% of unique attempted documents match a specific profile
python scripts/analyse_case_file_patterns.py --out docs/pattern_analysis

# one-off analysis of any folder of judgments
python scripts/analyse_case_file_patterns.py \
    --dirs backend/seed_corpus/pdfs backend/incoming_cases \
    --out docs/pattern_analysis

# in code
from app.services.case_pattern_service import CasePatternService
report = CasePatternService.analyse_pdf("path/to/order.pdf")
report["profile"]["profile_id"]      # e.g. 'BOMBAY-HC'
report["profile"]["court"]           # derived court (brief cards carry any court)
report["profile"]["key_set_ids"]     # ('KEY-HC-COMMON', 'KEY-EXTRA-BOMBAY')
report["key_coverage"]               # {'found': 16, 'declared': 29, 'ratio': 0.55, ...}
report["text_status"]                # 'ok' | 'insufficient_text' (cover-page PDFs)
report["facts"]["fact_sheet"]        # structured case facts
```

Uploads go through it automatically: `ExtractionService.extract_from_pdf` runs
**Pass 1b (pattern layer)** after the structural pass and adds
`pattern_profile`, `pattern_confidence`, `pattern_key_set`, `key_coverage`,
`layout_signals`, `text_quality`, `facts`, `fact_sheet`, `section_map` and
`neutral_citation` to the extraction payload. Any failure inside the layer is
logged and swallowed so ingestion cannot regress.

**Offline contract.** The ingestion path is geometry + regex + PyMuPDF /
pdfplumber only. Pass 2 (`pass2_regex`) and Pass 3 (`pass3_deterministic`) do not
call the AI microservice, Ollama, or Hugging Face, and they do not download model
weights. The same PDF bytes produce the same extraction payload, which is
pinned by `test_extraction_passes_are_offline_and_deterministic`.

### Adding a new template

1. Probe a few files of the new court/registry: caption line, date idiom, coram
   idiom, party designators, counsel block, prayer unit, signature block.
2. Add the signals to `SIGNALS` (pattern + scope + weight).
3. Add a profile to `PROFILES` with `required` / `supporting` / `negative`
   signals and `min_score`.
4. Add a `KEY-EXTRA-<COURT>` set in `KEY_SETS` (reuse `KEY-HC-COMMON`) and point
   the profile at `["KEY-HC-COMMON", "KEY-EXTRA-<COURT>"]`; add a `COURT_REGISTRY`
   row instead when the court can be expressed as one caption regex.
5. Pin the behaviour with a synthetic caption fixture in
   `backend/tests/test_case_pattern_service.py`, then re-run
   `scripts/analyse_case_file_patterns.py` to confirm no existing profile moves.

---

## 8. Known limitations / next steps

* **Two residual generic documents.** Both are Calcutta cause-list slips whose
  only court cue is a case-number prefix that Calcutta shares with Madras
  (`CRM (M)`); leaving them generic is preferable to a 50/50 court guess.
* **Court attribution for format profiles** depends on `COURT_NAME_MAP` /
  `REGISTRY_COURT`; a brief card from an unlisted tribunal stays `court: ""`
  (reported as unknown) rather than being given a wrong court.
* **Scanned orders.** The `ocr_required` path flags the file (31 in this sweep)
  but no OCR stage is wired in yet.
* **Facts boundary is heuristic.** On long reserved judgments (30–125 pages) the
  facts cap may cut before the full factual narrative; a continuation window
  (`facts` + `facts_continuation`) would help.
* **Judge strings in body citations.** Pass 1 can still pick a judge name from a
  cited judgment; the pattern layer only repairs the shape of the string, not
  its provenance.
* **Party blocks with multi-accused formats.** `1.Jeyaprakash @ Jeyaprakashraj`
  works; long address-mixed blocks still favour the first acceptable line.
* **No persistence of the profile yet.** `pattern_profile` is returned in the
  extraction payload but is not stored on the `Case` model — adding a
  `pattern_profile` / `layout_quality` column would let the review UI filter
  "needs OCR" and "unrecognised template" queues.
* **One corrupt file.** `storage/cases/HC_2026_CRL_A_0A6C947A_2026_0a6c947a.pdf`
  raises `FileDataError`; the sweep records it in `summary.errors`, counts it in
  the coverage denominator, and continues. The latest run still meets the 99 %
  target (593/596 specific profiles), so the analyser exits 0 while surfacing the
  unreadable file for triage.
* **Police-station names are regex-shaped.** `X Police Station` / `P.S. X`
  captures the common forms and rejects case-number/institution false positives,
  but unusual station names embedded in long address blocks may still need a
  registry-specific anchor.
