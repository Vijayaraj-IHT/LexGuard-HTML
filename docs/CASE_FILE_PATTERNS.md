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
| `docs/pattern_analysis/case_pattern_report.{json,md}` | Current sweep output (52 unique documents) |
| `backend/tests/test_case_pattern_service.py` | 26 tests: synthetic fixtures per template + corpus smoke tests |
| `backend/app/services/extraction_service.py` | Pass 1b — applies the key set to harden identity fields and lift `facts` |

---

## 1. Why patterns, not one big regex

The corpus (79 PDFs → **52 unique judgments**, 27 re-downloads of the same
files) is drafted to **eight different registry templates across four courts**.
Every template writes the same field differently:

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

## 3. Detected profiles (current corpus)

| Profile | Docs | What identifies it | Facts strategy |
|---|---:|---|---|
| `MHC-PS-CORAM-ORDER` | 11 | `IN THE HIGH COURT OF JUDICATURE AT MADRAS` + `CORAM` + `DATED: dd-mm-yyyy` + JUDIS footer | `coram_order` |
| `MHC-MB-CORAM-ORDER` | 17 | `BEFORE THE MADURAI BENCH …` + `CORAM` + `DATED:` | `coram_order` |
| `MHC-MB-CRIM-JURIS` | 8 | Madurai Bench + `( Criminal Jurisdiction )` + `PRESENT` + `Date : dd.mm.yyyy`, monospace body, `n/N` page clock | `order_sheet` |
| `MHC-PS-RESERVED-JUDGMENT` | 4 | `JUDICATURE AT MADRAS` + `RESERVED ON` / `PRONOUNCED ON` | `reserved_judgment` |
| `MHC-MB-RESERVED-JUDGMENT` | 8 | `MADURAI BENCH` + `Reserved on` / `Pronounced on` | `reserved_judgment` |
| `CGHC-BILASPUR-ORDER` | 2 | `HIGH COURT OF CHHATTISGARH AT BILASPUR`, neutral citation `2026:CGHC:n`, `AFR/NAFR`, `Order Reserved on`, `--- Petitioner(s)` | `numbered_paras` |
| `PATNA-CWJC-JUDGMENT` | 1 | `JUDICATURE AT PATNA`, `Civil Writ Jurisdiction Case No.`, `====` banners, `Appearance :`, `Patna High Court … dt.` header | `headed_facts` |
| `PHHC-CWP-COLUMNAR` | 1 | `HIGH COURT OF PUNJAB AND HARYANA AT CHANDIGARH`, `CWP-…(O&M)`, `Date of Decision:-`, `****`, `, J.` + DSC attestation | `columnar_judgment` |

Plus two fallbacks: `SC-GENERIC` (Supreme Court furniture — no corpus sample yet,
marked unverified) and `GENERIC-HC` (never competes; only used when nothing
clears the acceptance threshold).

### Scoring and acceptance

* Hard gate: every `required` signal must match.
* `score = Σ required weights + Σ matched supporting weights − Σ matched negative weights`
  (layout signals participate on the same scale).
* Ranking is by **absolute evidence**, normalised score as tie-break, so the
  generic profile can never win by being trivially "100 % complete".
* `normalised = score / max_possible`; below `0.40` the file falls back to
  `GENERIC-HC` and the runner-up is reported for triage.

Detection is fully deterministic and offline (regex + geometry only), which keeps
ingestion auditable.

---

## 4. Drafting/layout hazards found in the corpus

| Hazard | Files | Effect | Handling |
|---|---:|---|---|
| **Double-drawn text layer** (each line rendered twice with a 1–2 pt offset, words split across clips) | P&H | naive extraction yields `IN T + THE + HIGH … + AN + ND`, words truncated (`Rajwanti and ano`) | word-geometry repair: group by baseline, merge fragments by bbox overlap (duplicate draw) or character overlap (split word); the repaired page is kept only when line continuity improves ≥1.4× |
| **Monospace registry template** | 3 | different fonts/metrics, no JUDIS footer | `layout:mono_font` signal |
| **Legal-size page** (612×1008) | 4 | CGHC / Patna / P&H | `layout:legal_page` |
| **JUDIS watermark** (`https://www.mhc.tn.gov.in/judis`) repeated per page | 44 | pollutes body text and embeddings | noise key stripped before parsing |
| **Page clocks**: `Page N of M`, `n/N`, bare integer | 44 / — / 4 | break paragraph numbering | per-profile noise keys |
| **Running headers** (`Patna High Court CWJC … dt.…`, `CRL OP No. …`) | Patna + Madras | repeated mid-sentence | repeated-edge-line detection + noise keys |
| **Address blocks inside party captions** | CGHC, Patna | party extraction grabs `R/o Ward No. 02 …` | caption party extractor rejects address-shaped lines and cuts at `S/o · D/o · Aged · R/o · Rep by` |

Text-quality states surfaced per file: `good` (51), `repaired` (1),
`ocr_required` (0 in this corpus — the flag exists for scans).

---

## 5. Key sets

Every profile maps to a key set with 14 categories. A key is
`{category, anchors[], window, confidence, note}`; `window` is `line` (first
matching line), `block` (anchor plus the following lines) or `span` (anchor to
the next stop anchor).

| Category | What it yields | Example anchors |
|---|---|---|
| `identity` | case number, CNR, neutral citation, page clock | `CNR: {HCMA012161402026}`, `2026:CGHC:36890`, `CWP-1744-2024 (O&M)` |
| `forum` | court line, bench, jurisdiction banner, reportability | `BEFORE THE MADURAI BENCH …`, `( Criminal Jurisdiction )`, `NAFR` |
| `dates` | reserved, pronounced/decision date | `RESERVED ON:`, `Date : dd.mm.yyyy`, `Order passed on`, `Date of Decision:-` |
| `coram` | judge(s), signature-name form | `CORAM` + `HON'BLE …JUSTICE`, `, J.` |
| `parties` | petitioner, respondent, versus, designators, accused tags | `..Petitioner(s)`, `--- Petitioner(s)`, `...  ...  Petitioner/s` |
| `counsel` | appearance/for-party blocks | `For Petitioner(s):`, `Appearance :`, `Present:-` |
| `relief` | verbatim prayer | `PRAYER:`, `relief(s):- “`, `(i) Also for declaring …` |
| `facts` | factual-matrix start/end anchors, explicit heading | `ORDER`, `J U D G M E N T`, `Brief Facts Of Case`, end anchors `I have heard`, `learned counsel` |
| `issues` | framed questions | `Whether`, `points for consideration` |
| `reasoning` | discussion start | `I have heard`, `Having heard`, `Consideration` |
| `operative` | result/order paragraph | `In the result`, `stands dismissed`, `With the aforesaid observations` |
| `signature` | judge sign, attestation, pre-delivery order | `JUDGE`, `Sd/-`, `(Name) JUDGE`, `I attest to the accuracy…` |
| `noise` | watermarks, page clocks, rules, running headers | `mhc.tn.gov.in/judis`, `Page N of M`, `====`, `****` |
| `statute_style` | citation idiom of the template | `Sections … read with … of the Act`, `Articles 226`, `Section 483 BNSS` |

### Anchor hit rates on the 52-document sweep

| Key | Docs | | Key | Docs |
|---|---:|---|---|---:|
| `parties.versus` | 51 | | `facts.start` | 43 |
| `dates.decision_date` | 50 | | `parties.petitioner` | 42 |
| `relief.prayer` | 49 | | `identity.case_no` | 40 |
| `counsel.for_petitioner` | 48 | | `statute_style.sections` | 35 |
| `signature.judge_sign` | 45 | | `coram.judge` | 27 |
| `forum.court_line` | 44 | | `facts.end` | 26 |
| `parties.respondent` | 43 | | `identity.cnr` | 22 |

Mean key coverage per profile lands between **0.46 and 0.70**. Coverage is not a
quality score — a short omnibus order legitimately has no reserved date, no
issues heading and no prayer (Madras orders are 2–4 pages) — it is the
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
tokens, action verbs such as *arrested / seized / filed / remanded*) minus
**argument markers** (*SCC, held that, it is settled, submissions, whether,
prays*), with heavy penalties for caption furniture (`..Petitioner`,
`For Petitioners:`). The winner is trimmed to a paragraph edge and capped at
4 500 characters.

### Results on the sweep

| Strategy | Documents |
|---|---:|
| `anchored_span` | 31 |
| `paragraph_scan` | 19 |
| `post_caption_body` | 1 |
| `explicit_heading` | 1 |

Example fact sheets (dates / crime numbers / places / offences):

* *CRL OP 26220/2026* — 9 dates, `Crime No.120 of 2025`, `C.C.No.597 of 2026`,
  Tiruvallur, `Sections 8(c) read with 20(b)(ii)(C), 25 and 29(1) of the Act`,
  `in custody since then`.
* *WPS 5957/2023 (CGHC)* — 8 dates, `Section 34 of the Rights of Persons with
  Disabilities Act, 2016`.
* *CWP-1744-2024 (P&H)* — 12 dates recovered from a repaired text layer.

Fact-sheet fields: `dates`, `crime_numbers`, `places`, `offences`, `custody`,
`arrest`, `amounts`. They are returned alongside the facts text and are the
natural feed for the draft-assistant gap analysis and precedent search.

---

## 7. Using it

```bash
# one-off analysis of any folder of judgments
python scripts/analyse_case_file_patterns.py \
    --dirs backend/seed_corpus/pdfs backend/incoming_cases \
    --out docs/pattern_analysis

# in code
from app.services.case_pattern_service import CasePatternService
report = CasePatternService.analyse_pdf("path/to/order.pdf")
report["profile"]["profile_id"]      # e.g. 'MHC-MB-CRIM-JURIS'
report["key_coverage"]               # {'found': 16, 'declared': 29, 'ratio': 0.55, ...}
report["facts"]["fact_sheet"]        # structured case facts
```

Uploads go through it automatically: `ExtractionService.extract_from_pdf` runs
**Pass 1b (pattern layer)** after the structural pass and adds
`pattern_profile`, `pattern_confidence`, `pattern_key_set`, `key_coverage`,
`layout_signals`, `text_quality`, `facts`, `fact_sheet`, `section_map` and
`neutral_citation` to the extraction payload. Any failure inside the layer is
logged and swallowed so ingestion cannot regress.

### Adding a new template

1. Probe a few files of the new court/registry: caption line, date idiom, coram
   idiom, party designators, counsel block, prayer unit, signature block.
2. Add the signals to `SIGNALS` (pattern + scope + weight).
3. Add a profile to `PROFILES` with `required` / `supporting` / `negative`
   signals and `min_score`.
4. Add (or clone) a key set in `KEY_SETS` and point the profile at it.
5. Pin the behaviour with a synthetic caption fixture in
   `backend/tests/test_case_pattern_service.py`, then re-run
   `scripts/analyse_case_file_patterns.py` to confirm no existing profile moves.

---

## 8. Known limitations / next steps

* **Coverage skew.** 46 of 52 documents are Madras HC; Chhattisgarh, Patna and
  Punjab & Haryana rest on 1–2 samples each. Templates from Allahabad, Bombay,
  Karnataka, Delhi (and the Supreme Court) still need their own profiles.
* **Scanned orders.** The `ocr_required` path flags the file but no OCR stage is
  wired in yet.
* **Facts boundary is heuristic.** On long reserved judgments (30–46 pages) the
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
