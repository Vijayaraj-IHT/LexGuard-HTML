"""
LexGuard Case-File Pattern Service
==================================

Deterministic, offline recognition of *how* an Indian court case file was drafted,
so that the downstream extraction pipeline can load the right **key set** for the
document instead of guessing one global regex bundle.

Why this exists
---------------
Indian High Court judgments/orders are not drafted to one template. In the seed
corpus alone there are eight recurring drafting templates across seven registries
(Madras Principal Seat, Madras Madurai Bench x3 sub-templates, Chhattisgarh,
Patna, Punjab & Haryana). The same field (say the decision date) is written as
``DATED: 09-10-2026``, ``Date  : 09.10.2026``, ``Order passed on : 15.06.2026``,
``Date of Decision:- 17.08.2026`` or ``Pronounced on : 09.10.2026`` depending on
the template. A single catch-all regex either misses fields or picks the wrong
one (e.g. the "reserved on" date instead of the "pronounced on" date).

Modelling
---------
The service models a case file as three independent layers:

1. **Layout fingerprint** (physical): page geometry, text layer quality, mono vs
   serif fonts, clipped/duplicated text draws, columnar blocks, watermarks and
   running headers. Layout determines *how text must be read*.
2. **Drafting profile** (registry template): a weighted signal set describing the
   court, seat, caption idiom, date idiom, coram idiom, party designators,
   counsel block, prayer unit and signature block.
3. **Key set** (per profile): ordered anchor definitions per category
   (identity / forum / dates / coram / parties / counsel / relief / facts /
   issues / reasoning / operative / signature / noise / statute style). These are
   the keys we shortlist against a PDF; each key carries its own anchors, a
   confidence weight and the extraction window it applies to.

Everything here is regex + geometry only: no model download, no network, and the
same result for the same bytes (important for an auditable ingestion pipeline).

Public API
----------
``CasePatternService.analyse_pdf(path)`` -> full report (layout + profile + key hits)
``CasePatternService.detect(text, layout=None)`` -> profile detection only
``CasePatternService.key_set_for(profile_id)`` -> key set dict
``CasePatternService.map_sections(text, detection)`` -> anchored section map
``CasePatternService.extract_case_facts(text, detection)`` -> facts + fact sheet
``extract_pdf_text(path)`` -> (text, layout) with layout-aware repair
"""

from __future__ import annotations

import logging
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Signal library
# ---------------------------------------------------------------------------
# Every signal is a cheap, explainable probe. ``scope`` decides which text slice
# is searched: "header" = first three pages (caption + coram), "full" = whole
# document, "tail" = last three pages (operative order + signature).

SIGNALS: Dict[str, Dict[str, Any]] = {
    # ── Court / registry ────────────────────────────────────────────────────
    "court_madras_judicature": {
        "pattern": r"IN\s+THE\s+HIGH\s+COURT\s+OF\s+JUDICATURE\s+AT\s+MADRAS",
        "scope": "header", "weight": 3.0,
        "label": "Madras HC principal-seat caption",
    },
    "court_madurai_bench": {
        "pattern": r"BEFORE\s+THE\s+MADURAI\s+BENCH\s+OF\s+MADRAS\s+HIGH\s+COURT",
        "scope": "header", "weight": 3.0,
        "label": "Madras HC Madurai Bench caption",
    },
    "court_cg": {
        "pattern": r"HIGH\s+COURT\s+OF\s+CHHATTISGARH(?:\s+AT\s+BILASPUR)?",
        "scope": "header", "weight": 3.0,
        "label": "Chhattisgarh HC (Bilaspur) caption",
    },
    "court_patna": {
        "pattern": r"IN\s+THE\s+HIGH\s+COURT\s+OF\s+JUDICATURE\s+AT\s+PATNA",
        "scope": "header", "weight": 3.0,
        "label": "Patna HC caption",
    },
    "court_ph": {
        "pattern": r"HIGH\s+COURT\s+OF\s+PUNJAB\s+AN\s?D\s+HARYANA",
        "scope": "header", "weight": 3.0,
        "label": "Punjab & Haryana HC caption (tolerates doubled glyphs)",
    },
    "court_sc": {
        "pattern": r"IN\s+THE\s+SUPREME\s+COURT\s+OF\s+INDIA",
        "scope": "header", "weight": 3.0,
        "label": "Supreme Court caption",
    },

    # ── Bench / jurisdiction ────────────────────────────────────────────────
    "crim_jurisdiction": {
        "pattern": r"\(\s*Criminal\s+Jurisdiction\s*\)",
        "scope": "header", "weight": 2.5,
        "label": "( Criminal Jurisdiction ) banner",
    },
    "bench_md_token": {
        "pattern": r"(?:CRL|W\.?P|WMP|CONT|CMA|CMP)[\s\.]*[A-Z]*\s*\(\s*MD\s*\)|\(\s*MD\s*\)",
        "scope": "header", "weight": 1.0,
        "label": "(MD) bench token inside case number",
    },

    # ── Date idioms ────────────────────────────────────────────────────────
    "dated_colon_dash": {
        "pattern": r"DATED\s*:\s*\d{1,2}-\d{1,2}-\d{4}",
        "scope": "header", "weight": 1.5,
        "label": "DATED: dd-mm-yyyy",
    },
    "date_dot_slash": {
        "pattern": r"Date\s*:\s*\d{1,2}[./]\d{1,2}[./]\d{4}",
        "scope": "header", "weight": 1.5,
        "label": "Date : dd.mm.yyyy",
    },
    "dated_colon_text": {
        "pattern": r"DATED\s*:\s*\d{1,2}[./]\d{1,2}[./]\d{4}",
        "scope": "header", "weight": 1.2,
        "label": "DATED: dd.mm.yyyy / dd/mm/yyyy",
    },
    "reserved_pronounced": {
        "pattern": r"RESERVED\s+ON",
        "scope": "header", "weight": 2.0,
        "label": "RESERVED ON / PRONOUNCED ON dual date",
    },
    "pronounced_on": {
        "pattern": r"PRONOUNCED\s+ON|Delivered\s+on|Pronounced\s+on",
        "scope": "header", "weight": 1.5,
        "label": "Pronounced-on date line",
    },
    "order_reserved_cg": {
        "pattern": r"Order\s+Reserved\s+on",
        "scope": "header", "weight": 2.5,
        "label": "Chhattisgarh Order Reserved on / Order passed on",
    },
    "date_of_decision": {
        "pattern": r"Date\s+of\s+Decision\s*:",
        "scope": "header", "weight": 2.5,
        "label": "P&H 'Date of Decision:-' line",
    },

    # ── Coram idioms ───────────────────────────────────────────────────────
    "coram_word": {
        "pattern": r"^\s*CORAM\s*:?\s*$",
        "scope": "header", "weight": 1.5,
        "label": "CORAM block",
    },
    "present_word": {
        "pattern": r"^\s*PRESENT\s*:?\s*$",
        "scope": "header", "weight": 1.2,
        "label": "PRESENT block (Madurai criminal template)",
    },
    "hon_ble": {
        "pattern": r"HON[’'`]?BLE",
        "scope": "header", "weight": 0.6,
        "label": "HON'BLE coram prefix",
    },
    "honourable": {
        "pattern": r"HONOURABLE",
        "scope": "header", "weight": 0.6,
        "label": "HONOURABLE coram prefix",
    },

    # ── Party designators ──────────────────────────────────────────────────
    "pet_dots": {
        "pattern": r"\.\.\s*Petitioner", "scope": "header", "weight": 1.2,
        "label": "'..Petitioner(s)' designator",
    },
    "pet_slash": {
        "pattern": r"Petitioner\s*/\s*s|Petitioner/s", "scope": "header", "weight": 1.2,
        "label": "'Petitioner/s' designator",
    },
    "dash_pet": {
        "pattern": r"---\s*Petitioner", "scope": "header", "weight": 1.5,
        "label": "'--- Petitioner(s)' designator (CGHC)",
    },
    "versus_word": {
        "pattern": r"^\s*Versus\s*$", "scope": "header", "weight": 1.5,
        "label": "'Versus' on its own line",
    },
    "vs_line": {
        "pattern": r"^\s*Vs\.?\s*$", "scope": "header", "weight": 0.8,
        "label": "'Vs' on its own line",
    },

    # ── Prayer / relief ────────────────────────────────────────────────────
    "prayer": {
        "pattern": r"PRAYER", "scope": "full", "weight": 1.0,
        "label": "PRAYER unit",
    },
    "prayer_indented_cg": {
        "pattern": r"relief\(s\)\s*:?-?\s*[“\"]", "scope": "full", "weight": 1.2,
        "label": "Quoted relief block in body",
    },

    # ── Counsel block ──────────────────────────────────────────────────────
    "counsel_for": {
        "pattern": r"For\s+(?:the\s+)?Petitioner", "scope": "header", "weight": 1.0,
        "label": "For Petitioner(s) block",
    },
    "appearance": {
        "pattern": r"^\s*Appearance\s*:", "scope": "header", "weight": 2.0,
        "label": "Patna 'Appearance :' block",
    },

    # ── Identity / citation ────────────────────────────────────────────────
    "cnr": {
        "pattern": r"CNR\s*:?\s*\{?[A-Z]{4}\d{12}", "scope": "header", "weight": 1.2,
        "label": "CNR code block",
    },
    "neutral_cg": {
        "pattern": r"\d{4}\s*:\s*CGHC\s*:\s*\d+", "scope": "header", "weight": 2.5,
        "label": "Neutral citation (year:CGHC:n)",
    },
    "afr": {
        "pattern": r"^\s*(?:N?AFR)\s*$", "scope": "header", "weight": 1.0,
        "label": "AFR / NAFR reportability tag",
    },
    "judis_url": {
        "pattern": r"mhc\.tn\.gov\.in", "scope": "full", "weight": 1.0,
        "label": "JUDIS footer URL",
    },

    # ── Operative / signature ──────────────────────────────────────────────
    "sd_sign": {
        "pattern": r"Sd/-", "scope": "tail", "weight": 1.5,
        "label": "Sd/- signature marker",
    },
    "judge_word": {
        "pattern": r"^\s*JUDGE\s*$", "scope": "tail", "weight": 1.2,
        "label": "JUDGE signature label",
    },
    "jcomma": {
        "pattern": r"[A-Z][A-Z\.\s]+,?\s*J\.\s*$", "scope": "tail", "weight": 1.2,
        "label": "'NAME, J.' signature",
    },
    "justice_sign": {
        "pattern": r"\(\s*[A-Z][A-Za-z\.\s]+\s*\)\s*\n?\s*JUDGE", "scope": "tail", "weight": 1.2,
        "label": "(Name) JUDGE signature",
    },
    "order_heading": {
        "pattern": r"^\s*(?:ORDER|J\s*U\s*D\s*G\s*M\s*E\s*N\s*T)\s*$",
        "scope": "full", "weight": 1.0,
        "label": "ORDER / J U D G M E N T heading",
    },

    # ── Additional registry idioms (expanded corpus: 20+ courts) ──────────
    "brief_card": {
        "pattern": r"JUDICIAL\s+HEADNOTE|RATIO\s+DECIDENDI|OPERATIVE\s+ORDER|LexGuard\s+Immutable",
        "scope": "full", "weight": 3.5,
        "label": "One-page case-brief card (headnote / ratio / operative headings)",
    },
    "appellate_jurisdiction": {
        "pattern": r"(?:JUDICIAL\s+)?APPELLATE\s+JURISDICTION",
        "scope": "header", "weight": 1.2,
        "label": "APPELLATE JURISDICTION banner",
    },
    "cnr_field": {
        "pattern": r"CNR\s*(?:No\.?)?\s*:\s*[A-Z]{2,4}\d{8,}",
        "scope": "header", "weight": 1.5,
        "label": "CNR: <code> field",
    },
    "registry_code": {
        "pattern": r"\b(?:[A-Z]{2,4}HC\d{10,})\b",
        "scope": "header", "weight": 1.5,
        "label": "Registry code (APHC/TRHC/UKHC/ODHC/GAHC/GJHC…)",
    },
    "allahabad_case_line": {
        "pattern": r"^\s*Case\s*:-\s*", "scope": "header", "weight": 3.0,
        "label": "Allahabad 'Case :-' / 'Applicant :-' / 'Opposite Party :-' block",
    },
    "gauhati_case_no": {
        "pattern": r"^\s*Case\s+No\.?\s*:\s*", "scope": "header", "weight": 2.0,
        "label": "Gauhati 'Case No. :' line",
    },
    "calcutta_between": {
        "pattern": r"(?m)^\s*(?:-\s*Vs\.?\s*-|Between\s*:|Vs\.?)\s*$", "scope": "header", "weight": 2.0,
        "label": "Calcutta 'Between:' / '-Vs-' caption",
    },
    "telangana_soj": {
        "pattern": r"\(\s*Special\s+Original\s+Jurisdiction\s*\)", "scope": "header", "weight": 1.5,
        "label": "(Special Original Jurisdiction) — Telangana / Andhra",
    },
    "dated_this_the": {
        "pattern": r"DATED\s+THIS\s+THE\s+\d{1,2}(?:ST|ND|RD|TH)?\s+DAY\s+OF", "scope": "header",
        "weight": 2.0, "label": "'DATED THIS THE n TH DAY OF …' (Karnataka / Kerala / Telangana)",
    },
    "meghalaya_serial": {
        "pattern": r"^\s*(?:Serial\s+No\.?|Supp\.?\s+List|Regular\s+List)", "scope": "header",
        "weight": 1.5, "label": "Cause-list furniture (Serial No. / Regular List)",
    },
    "jk_through": {
        "pattern": r"^\s*Through\s*:?\s*(?:-|Mr|Ms|None)", "scope": "header", "weight": 2.0,
        "label": "J&K 'Through :' counsel line",
    },
    "orissa_adv": {
        "pattern": r"Represented\s+by\s+Adv", "scope": "header", "weight": 2.5,
        "label": "Orissa 'Represented by Adv. -' block",
    },
    "bombay_doc_header": {
        "pattern": r"(?m)^\s*(?:[\w\-\.]+\.docx?|[\d]+/[\d]+\s+\S+\.doc|[\d]+\s+wp\s+\d+[\-\.]\d+|"
                   r"(?:wp|wpcr|cria|cra|cp|caw|crmaba|crlwp|sa|pil|wpst|wmp)[\s\.\-]*\d{1,6}[\s\.\-]+"
                   r"(?:of[\s\.\-]+)?\d{2,4}(?:[\s\.\-]+\w+)?)\s*$",
        "scope": "header",
        "weight": 1.5, "label": "Bombay '.doc/.docx' working header",
    },
    "bombay_coram_date": {
        "pattern": r"CORAM\s*:\s*[A-Z][A-Za-z\.\s,]+,?\s*J\.", "scope": "header", "weight": 2.0,
        "label": "Bombay inline 'CORAM : NAME, J.'",
    },
    "in_re_bail": {
        "pattern": r"In\s+Re\s*:?\s*An?\s+application", "scope": "header", "weight": 2.5,
        "label": "Madras 'In Re : An application for bail …' daily order",
    },
    "court_no_line": {
        "pattern": r"^\s*Court\s+No\.?\s*-?\s*\d+", "scope": "header", "weight": 0.8,
        "label": "'Court No.' cause-list line",
    },
    "submitted_brief_sections": {
        "pattern": r"Acts\s+Referred|Sections\s*:|JUDGMENT\s*&\s*REASONING", "scope": "full",
        "weight": 1.5, "label": "'Acts Referred' / 'JUDGMENT & REASONING' brief sections",
    },

    "bombay_neutral_citation": {
        "pattern": r"\b\d{4}:BHC-[A-Z]{2,5}:\d+\b",
        "scope": "header", "weight": 2.5,
        "label": "Bombay neutral citation '2026:BHC-GOA:2108'",
    },
    "madras_rvw": {
        "pattern": r"\bR\.?\s?V\.?\s?W\.?\s*\d+\s+of\s+\d{4}\b",
        "scope": "header", "weight": 2.5,
        "label": "Madras review petition 'R.V.W. 369 of 2024'",
    },

    "office_notes": {
        "pattern": r"(?:Office\s+Notes|Court'?s\s+or\s+Judge'?s\s+orders|"
                    r"Date\s+or\s+directions\s+and\s+COURT'?S\s+OR\s+JUDGE'?S)",
        "scope": "header", "weight": 2.0,
        "label": "Registry office-notes sheet header (no separate judgment caption)",
    },
    "law_report_reprint": {
        "pattern": r"(?:Equivalent\s+citations\s*:|\bvs\.?\s+[A-Z][A-Za-z\.\s]+\s+on\s+\d{1,2}\s+[A-Z][a-z]+,\s*\d{4}\b)",
        "scope": "header", "weight": 2.0,
        "label": "Digest/law-report reprint ('Equivalent citations:', '<party> vs <party> on <date>')",
    },
    "madras_short_order": {
        "pattern": r"WMP?\.?\s*No\.?\s*\d+\s+of\s+\d{4}\s+in\s+\n?\s*W\.?\s?P\.?\s*No\.",
        "scope": "header", "weight": 2.0,
        "label": "Madras short order slip ('WMP. No. … in W.P. No. …')",
    },

    "not_a_judgment": {
        "pattern": r"(?:Project\s+Overview|Objectives\s+&\s+Scope|Tech\s+Stack|System\s+Architecture|"
                    r"Table\s+of\s+Contents|Executive\s+Summary)\s*\n",
        "scope": "header", "weight": 3.0,
        "label": "Specification/summary document headings — not a judgment",
    },

    # ── Statutory citation style ───────────────────────────────────────────
    "statute_modern_codes": {
        "pattern": r"\bBNSS?\b|\bBharatiya\s+(?:Nyaya|Nagarik|Sakshya)",
        "scope": "full", "weight": 0.8,
        "label": "Post-2024 codes (BNS/BNSS/BSA) cited",
    },
    "statute_legacy_codes": {
        "pattern": r"\b(?:Cr\.?P\.?C|I\.?P\.?C)\b|Code\s+of\s+Criminal\s+Procedure",
        "scope": "full", "weight": 0.8,
        "label": "Legacy codes (IPC/CrPC) cited",
    },
}

# Signals derived from the physical layout rather than the text.  Profiles can
# reference them with the ``layout:`` prefix.
LAYOUT_SIGNALS: Dict[str, str] = {
    "layout:mono_font": "Courier / monospace dominant (Madurai criminal template)",
    "layout:serif": "Times / serif dominant (judgment typesetting)",
    "layout:legal_page": "Legal-size page (>= 600x950 pt) — CGHC / Patna / P&H",
    "layout:a4_page": "A4 page (≈595x842) — JUDIS / MHC",
    "layout:no_text_layer": "No usable text layer — OCR required",
    "layout:clipped_blocks": "Text drawn as clipped/overlapping blocks — needs geometric repair",
    "layout:columnar": "Genuine multi-column blocks present",
    "layout:watermark": "Repeating JUDIS/registry watermark",
}


# ---------------------------------------------------------------------------
# 2. Drafting profiles
# ---------------------------------------------------------------------------
# ``required``  - must all be present (hard gate)
# ``supporting``- (signal_id, weight) evidence
# ``negative``  - if matched, subtract the weight
# ``min_score`` - normalised score needed to accept the profile
# ``key_set``   - id of the key set used for field extraction

PROFILES: List[Dict[str, Any]] = [
    {
        "id": "MHC-MB-CRIM-JURIS",
        "label": "Madras HC, Madurai Bench — 'Criminal Jurisdiction' order sheet",
        "court": "Madras High Court",
        "seat": "Madurai Bench",
        "drafting_style": "Registry order sheet: ( Criminal Jurisdiction ) banner, PRESENT coram, "
                          "monospace body, running 'CaseNo / <n>/<N>' page clock",
        "required": ["court_madurai_bench", "crim_jurisdiction"],
        "supporting": [
            ("present_word", 1.2), ("date_dot_slash", 1.2), ("layout:mono_font", 1.0),
            ("pet_dots", 0.8), ("counsel_for", 0.6),
        ],
        "negative": [("reserved_pronounced", 1.2), ("court_madras_judicature", 1.5)],
        "min_score": 0.55,
        "key_set": "KEY-MHC-MB-CRIM",
        "facts_strategy": "order_sheet",
    },
    {
        "id": "MHC-MB-RESERVED-JUDGMENT",
        "label": "Madras HC, Madurai Bench — reserved long-form judgment",
        "court": "Madras High Court",
        "seat": "Madurai Bench",
        "drafting_style": "Reserved judgment: 'Reserved on' / 'Pronounced on' dual dates, numbered "
                          "paragraph judgment body, J. signature, JUDIS footer",
        "required": ["court_madurai_bench"],
        "supporting": [
            ("reserved_pronounced", 2.0), ("pronounced_on", 1.2), ("coram_word", 0.8),
            ("judis_url", 0.6), ("order_heading", 0.6),
        ],
        "negative": [("crim_jurisdiction", 1.5)],
        "min_score": 0.55,
        "key_set": "KEY-MHC-MB-RESERVED",
        "facts_strategy": "reserved_judgment",
    },
    {
        "id": "MHC-MB-CORAM-ORDER",
        "label": "Madras HC, Madurai Bench — CORAM + DATED order",
        "court": "Madras High Court",
        "seat": "Madurai Bench",
        "drafting_style": "CORAM block followed by a single DATED line; '..Petitioner(s)' designators; "
                          "PRAYER unit then ORDER",
        "required": ["court_madurai_bench"],
        "supporting": [
            ("coram_word", 1.2), ("dated_colon_dash", 1.0), ("dated_colon_text", 0.8),
            ("judis_url", 0.5), ("pet_dots", 0.4),
        ],
        "negative": [("crim_jurisdiction", 1.5), ("reserved_pronounced", 1.0)],
        "min_score": 0.45,
        "key_set": "KEY-MHC-MB-CORAM",
        "facts_strategy": "coram_order",
    },
    {
        "id": "MHC-PS-RESERVED-JUDGMENT",
        "label": "Madras HC, Principal Seat — reserved long-form judgment",
        "court": "Madras High Court",
        "seat": "Principal Seat, Chennai",
        "drafting_style": "JUDICATURE AT MADRAS caption + RESERVED ON / PRONOUNCED ON, long-form "
                          "judgment, JUDIS footer, 'Page N of M' watermark",
        "required": ["court_madras_judicature", "reserved_pronounced"],
        "supporting": [
            ("pronounced_on", 1.2), ("coram_word", 0.8), ("judis_url", 0.6),
            ("order_heading", 0.6),
        ],
        "negative": [],
        "min_score": 0.55,
        "key_set": "KEY-MHC-PS-RESERVED",
        "facts_strategy": "reserved_judgment",
    },
    {
        "id": "MHC-PS-CORAM-ORDER",
        "label": "Madras HC, Principal Seat — CORAM + DATED order",
        "court": "Madras High Court",
        "seat": "Principal Seat, Chennai",
        "drafting_style": "JUDICATURE AT MADRAS caption, CORAM block, DATED line, PRAYER unit, ORDER",
        "required": ["court_madras_judicature"],
        "supporting": [
            ("coram_word", 1.2), ("dated_colon_dash", 1.0), ("dated_colon_text", 0.8),
            ("judis_url", 0.5), ("pet_dots", 0.3),
        ],
        "negative": [("reserved_pronounced", 0.5)],
        "min_score": 0.45,
        "key_set": "KEY-MHC-PS-CORAM",
        "facts_strategy": "coram_order",
    },
    {
        "id": "CGHC-BILASPUR-ORDER",
        "label": "Chhattisgarh HC at Bilaspur — AFR/NAFR order on board",
        "court": "High Court of Chhattisgarh",
        "seat": "Bilaspur",
        "drafting_style": "Neutral citation year:CGHC:n, AFR/NAFR tag, 'Order Reserved on / Order passed "
                          "on', '--- Petitioner(s)' / 'versus', numbered paragraphs, 'Sd/- (Judge) Judge'",
        "required": ["court_cg"],
        "supporting": [
            ("neutral_cg", 2.0), ("afr", 1.0), ("order_reserved_cg", 1.5),
            ("dash_pet", 1.2), ("versus_word", 0.8), ("sd_sign", 0.8),
            ("layout:legal_page", 0.8),
        ],
        "negative": [],
        "min_score": 0.5,
        "key_set": "KEY-CGHC",
        "facts_strategy": "numbered_paras",
    },
    {
        "id": "PATNA-CWJC-JUDGMENT",
        "label": "Patna HC — Civil Writ Jurisdiction Case judgment",
        "court": "Patna High Court",
        "seat": "Patna",
        "drafting_style": "Banner-separated caption ('====='), 'Petitioner/s' / 'Respondent/s', "
                          "'Appearance :' block, running header 'Patna High Court CWJC ... dt.<date>' "
                          "and 'n/N' footer, explicit 'Brief Facts Of Case' heading",
        "required": ["court_patna"],
        "supporting": [
            ("appearance", 1.5), ("pet_slash", 1.2), ("versus_word", 0.8),
            ("layout:legal_page", 0.8), ("coram_word", 0.4),
        ],
        "negative": [],
        "min_score": 0.5,
        "key_set": "KEY-PATNA",
        "facts_strategy": "headed_facts",
    },
    {
        "id": "PHHC-CWP-COLUMNAR",
        "label": "Punjab & Haryana HC — CWP (O&M) columnar judgment",
        "court": "Punjab & Haryana High Court",
        "seat": "Chandigarh",
        "drafting_style": "CWP-<n>-<year> (O&M) caption, 'Date of Decision:-', CORAM + Present:- block, "
                          "'****' rule, ', J.' + '(Name) JUDGE' signature and DSC attestation text; "
                          "text layer is double-drawn so extraction needs geometric repair",
        "required": ["court_ph"],
        "supporting": [
            ("date_of_decision", 2.0), ("jcomma", 1.0), ("justice_sign", 0.8),
            ("layout:legal_page", 0.8), ("layout:clipped_blocks", 1.0),
            ("coram_word", 0.4),
        ],
        "negative": [],
        "min_score": 0.5,
        "key_set": "KEY-PHHC",
        "facts_strategy": "columnar_judgment",
    },
    {
        "id": "SC-GENERIC",
        "label": "Supreme Court of India — generic judgment",
        "court": "Supreme Court of India",
        "seat": "New Delhi",
        "drafting_style": "IN THE SUPREME COURT OF INDIA, 'J U D G M E N T', HON'BLE MR./MS. JUSTICE "
                          "coram, 'Leave granted' / 'Civil Appeal No. ... of ...'",
        "required": ["court_sc"],
        "supporting": [("order_heading", 0.8), ("hon_ble", 0.6)],
        "negative": [],
        "min_score": 0.5,
        "key_set": "KEY-SC",
        "facts_strategy": "reserved_judgment",
    },
    {
        "id": "GENERIC-HC",
        "label": "Unrecognised High Court / tribunal template",
        "court": "High Court",
        "seat": "",
        "drafting_style": "Fallback: caption + numbered paragraphs, no registry-specific template matched",
        "required": [],
        "supporting": [("order_heading", 0.5), ("prayer", 0.4)],
        "negative": [],
        "min_score": 0.0,
        "key_set": "KEY-GENERIC",
        "facts_strategy": "generic",
    },
]


# ---------------------------------------------------------------------------
# 3. Key sets
# ---------------------------------------------------------------------------
# Each key: {category, anchors (regex, ordered), window, confidence, note}
# ``window`` semantics (used by KeySetRunner):
#   "line"   – first line containing an anchor match
#   "block"  – the block of lines following the anchor until a stop line
#   "span"   – from anchor to the next stop anchor (used for sections)

def _k(category: str, anchors: Sequence[str], window: str = "line", confidence: float = 0.9,
       note: str = "") -> Dict[str, Any]:
    return {"category": category, "anchors": list(anchors), "window": window,
            "confidence": confidence, "note": note}


COMMON_NOISE_KEYS = {
    "judis_footer": _k("noise", [r"https?://www\.mhc\.tn\.gov\.in/judis"], "line", 1.0,
                       "JUDIS footer URL — strip before parsing body"),
    "page_clock_of": _k("noise", [r"^\s*Page\s*\d+\s*of\s*\d+\s*$"], "line", 1.0),
    "page_clock_slash": _k("noise", [r"^\s*\d{1,3}\s*/\s*\d{1,3}\s*$"], "line", 1.0),
    "bare_page_number": _k("noise", [r"^\s*\d{1,3}\s*$"], "line", 0.8),
    "rule_lines": _k("noise", [r"^\s*[_=*]{4,}\s*$"], "line", 1.0),
    "cav_marker": _k("noise", [r"^\s*(?:CAV|Taken on Board|Order on Board|Judgment on Board)\s*.*$"],
                     "line", 0.7),
}

KEY_SETS: Dict[str, Dict[str, Any]] = {
    # ── Madras Principal Seat, CORAM + DATED ───────────────────────────────
    "KEY-MHC-PS-CORAM": {
        "identity": {
            "case_no": _k("identity", [r"(?m)^\s*((?:CRL\s*OP|CRL\s*MP|CRL\s*A|WP\s*CRL|W\.?P\.?|C\.?M\.?P|"
                                       r"CONT[\s\.]*P|CMA|OSA|A\.\s*Nos?|T\.?O\.?S\.?)[^\n]{0,60}?of\s+\d{4})"],
                          "line", 0.95),
            "cnr": _k("identity", [r"CNR\s*:?\s*\{?([A-Z]{4}\d{12})\}?"], "line", 0.97),
        },
        "forum": {
            "court_line": _k("forum", [r"IN\s+THE\s+HIGH\s+COURT\s+OF\s+JUDICATURE\s+AT\s+MADRAS"],
                             "line", 0.98),
            "bench": _k("forum", [r"\(\s*MD\s*\)"], "line", 0.7,
                        "no (MD) → Principal Seat"),
            "jurisdiction": _k("forum", [r"\(\s*Criminal\s+Jurisdiction\s*\)"], "line", 0.8),
        },
        "dates": {
            "decision_date": _k("dates", [r"DATED\s*:\s*(\d{1,2}[-./]\d{1,2}[-./]\d{4})"], "line", 0.95),
            "reserved_on": _k("dates", [r"RESERVED\s+ON\s*:\s*([^\n]+)"], "line", 0.95),
            "pronounced_on": _k("dates", [r"PRONOUNCED\s+ON\s*:\s*([^\n]+)"], "line", 0.95),
        },
        "coram": {
            "judge": _k("coram", [r"CORAM\s*:?\s*\n+\s*(?:THE\s+)?HON[’'`]?BLE[^\n]+"], "block", 0.95),
        },
        "parties": {
            "petitioner": _k("parties", [r"\.\.\s*Petitioner"], "block", 0.9),
            "respondent": _k("parties", [r"\.\.\s*Respondent"], "block", 0.9),
            "versus": _k("parties", [r"^\s*Vs\.?\s*$"], "line", 0.95),
        },
        "counsel": {
            "for_petitioner": _k("counsel", [r"For\s+(?:the\s+)?Petitioners?\s*\(?s?\)?\s*:"], "block", 0.9),
            "for_respondent": _k("counsel", [r"For\s+(?:the\s+)?Respondents?\s*\(?s?\)?\s*:"], "block", 0.9),
        },
        "relief": {
            "prayer": _k("relief", [r"PRAYER\s*:", r"PRAYER\b"], "span", 0.95),
        },
        "facts": {
            "start": _k("facts", [r"^\s*ORDER\s*[:\-]\s*", r"^\s*ORDER\s*$",
                                    r"^\s*J\s*U\s*D\s*G\s*M\s*E\s*N\s*T\s*$"], "line", 0.85,
                        "facts begin after the ORDER/JUDGMENT heading"),
            "end": _k("facts", [r"I\s+have\s+heard", r"Heard\s+(?:the\s+)?(?:learned|ld\.)",
                                r"^\s*DISCUSSION", r"^\s*Consideration", r"^\s*CONCLUSION",
                                r"The\s+point[s]?\s+(?:for|that)\s+(?:arises|arise)"], "line", 0.75),
        },
        "issues": {
            "issues": _k("issues", [r"The\s+point[s]?\s+(?:for|that)\s+(?:arises|arise)[^\n]*",
                                    r"^\s*(\d+[\.\)]\s*)?(?:Whether|WHETHER)\b"], "span", 0.7),
        },
        "reasoning": {
            "from": _k("reasoning", [r"I\s+have\s+heard", r"Heard\s+(?:the\s+)?(?:learned|ld\.)"], "line", 0.7),
        },
        "operative": {
            "conclusion": _k("operative", [r"In\s+the\s+result", r"^\s*(\d+[\.\)]\s*)?In\s+the\s+result"],
                             "span", 0.85),
        },
        "signature": {
            "judge_sign": _k("signature", [r"^\s*JUDGE\s*$", r"[A-Z][A-Za-z\.\s]+,?\s*J\.\s*$"], "line", 0.9),
        },
        "noise": dict(COMMON_NOISE_KEYS),
        "statute_style": {
            "sections": _k("statute_style", [r"\bSections?\s+\d+[^\n]{0,80}(?:of\s+the\s+[A-Z][^,\.\n]{2,60})?"],
                           "line", 0.8),
            "articles": _k("statute_style", [r"\bArticles?\s+\d+"], "line", 0.9),
            "read_with": _k("statute_style", [r"read\s+with\s+(?:Section[s]?\s+)?"], "line", 0.8),
        },
    },

    # ── Madras Principal Seat, reserved judgment ───────────────────────────
    "KEY-MHC-PS-RESERVED": {
        "identity": {
            "case_no": _k("identity", [r"(?m)^\s*((?:A\.\s*Nos?|O\.A\.\s*Nos?|T\.?O\.?S\.?|C\.?S\.?|"
                                       r"CRL\s*OP|W\.?P\.?|WA|CMA|OSA|CMP|CONT\s*P)[^\n]{0,70}?of\s+\d{4})"],
                          "line", 0.95),
            "linked_cases": _k("identity", [r"O\.A\.\s*Nos?\.?\s*[\d\s&,]+of\s+\d{4}"], "line", 0.8),
            "cnr": _k("identity", [r"CNR\s*:?\s*\{?([A-Z]{4}\d{12})\}?"], "line", 0.97),
        },
        "forum": {
            "court_line": _k("forum", [r"IN\s+THE\s+HIGH\s+COURT\s+OF\s+JUDICATURE\s+AT\s+MADRAS"], "line", 0.98),
            "bench": _k("forum", [r"BEFORE\s+THE\s+MADURAI\s+BENCH"], "line", 0.9),
        },
        "dates": {
            "reserved_on": _k("dates", [r"RESERVED\s+ON\s*:\s*([^\n]+)"], "line", 0.95),
            "pronounced_on": _k("dates", [r"PRONOUNCED\s+ON\s*:\s*([^\n]+)"], "line", 0.96),
            "decision_date": _k("dates", [r"^\s*(\d{1,2}[-./]\d{1,2}[-./]\d{4})\s*$"], "line", 0.8,
                                "date printed above the signature at the end"),
        },
        "coram": {
            "judge": _k("coram", [r"CORAM\s*:?\s*\n+\s*(?:THE\s+)?HON[’'`]?BLE[^\n]+"], "block", 0.95),
            "signature_name": _k("coram", [r"([A-Z][A-Z\.\s]{3,40}),\s*J\."], "line", 0.85),
        },
        "parties": {
            "petitioner": _k("parties", [r"\.\.\s*(?:Petitioner|Applicant)"], "block", 0.9),
            "respondent": _k("parties", [r"\.\.\s*Respondent"], "block", 0.9),
            "versus": _k("parties", [r"^\s*Vs\.?\s*$"], "line", 0.95),
        },
        "counsel": {
            "for_petitioner": _k("counsel", [r"For\s+(?:the\s+)?(?:Petitioners?|Applicants?)"], "block", 0.9),
            "for_respondent": _k("counsel", [r"For\s+(?:the\s+)?Respondents?"], "block", 0.9),
        },
        "relief": {
            "prayer": _k("relief", [r"PRAYER\s+(?:IN\s+[^\n:]+)?:", r"PRAYER\b"], "span", 0.95),
        },
        "facts": {
            "start": _k("facts", [r"^\s*J\s*U\s*D\s*G\s*M\s*E\s*N\s*T\s*$", r"^\s*ORDER\s*$"], "line", 0.9),
            "end": _k("facts", [r"^\s*\d+[\.\)]\s*(?:The\s+)?(?:point|question)s?\b",
                                r"I\s+have\s+heard", r"^\s*DISCUSSION", r"^\s*Submission"], "line", 0.7),
        },
        "issues": {
            "issues": _k("issues", [r"(?:framed|the following)\s+(?:the\s+)?(?:issues?|points?)",
                                    r"The\s+point[s]?\s+for\s+consideration"], "span", 0.75),
        },
        "reasoning": {
            "from": _k("reasoning", [r"I\s+have\s+(?:heard|considered)", r"^\s*DISCUSSION"], "line", 0.7),
        },
        "operative": {
            "conclusion": _k("operative", [r"In\s+the\s+result", r"^\s*CONCLUSION"], "span", 0.85),
        },
        "signature": {
            "judge_sign": _k("signature", [r"[A-Z][A-Z\.\s]{2,40},?\s*J\.\s*$", r"^\s*JUDGE\s*$"], "line", 0.9),
            "pre_delivery_order": _k("signature", [r"PRE-DELIVERY\s+ORDER\s+MADE\s+IN"], "line", 0.9),
        },
        "noise": dict(COMMON_NOISE_KEYS),
        "statute_style": {
            "sections": _k("statute_style", [r"\bSections?\s+\d+[^\n]{0,80}"], "line", 0.8),
            "read_with": _k("statute_style", [r"read\s+with"], "line", 0.8),
        },
    },

    # ── Madurai Bench, CORAM + DATED ───────────────────────────────────────
    "KEY-MHC-MB-CORAM": {
        "identity": {
            "case_no": _k("identity", [r"(?m)^\s*((?:WP\s*Crl|CRL\s*OP|CRL\s*A|WP|CONT[\s\.]*P)"
                                       r"[^\n]{0,70}?of\s+\d{4})"], "line", 0.95),
            "cnr": _k("identity", [r"CNR\s*:?\s*\{?([A-Z]{4}\d{12})\}?"], "line", 0.97),
        },
        "forum": {
            "court_line": _k("forum", [r"BEFORE\s+THE\s+MADURAI\s+BENCH\s+OF\s+MADRAS\s+HIGH\s+COURT"],
                             "line", 0.98),
            "jurisdiction": _k("forum", [r"\(\s*Criminal\s+Jurisdiction\s*\)"], "line", 0.8),
        },
        "dates": {
            "decision_date": _k("dates", [r"DATED\s*:\s*(\d{1,2}[-./]\d{1,2}[-./]\d{4})"], "line", 0.95),
            "reserved_on": _k("dates", [r"(?:Reserved|RESERVED)\s+on\s*:?\s*([^\n]+)"], "line", 0.95),
            "pronounced_on": _k("dates", [r"(?:Pronounced|PRONOUNCED)\s+on\s*:?\s*([^\n]+)"], "line", 0.95),
        },
        "coram": {"judge": _k("coram", [r"CORAM\s*:?\s*\n+\s*(?:THE\s+)?HON[’'`]?BLE[^\n]+"], "block", 0.95)},
        "parties": {
            "petitioner": _k("parties", [r"\.\.\s*Petitioners?"], "block", 0.9),
            "respondent": _k("parties", [r"\.\.\s*Respondents?"], "block", 0.9),
            "versus": _k("parties", [r"^\s*Vs\.?\s*$"], "line", 0.95),
        },
        "counsel": {
            "for_petitioner": _k("counsel", [r"For\s+(?:the\s+)?Petitioners?"], "block", 0.9),
            "for_respondent": _k("counsel", [r"For\s+(?:the\s+)?Respondents?"], "block", 0.9),
        },
        "relief": {"prayer": _k("relief", [r"PRAYER\s*:", r"PRAYER\b"], "span", 0.95)},
        "facts": {
            "start": _k("facts", [r"^\s*ORDER\s*[:\-]\s*", r"^\s*ORDER\s*$",
                                    r"^\s*J\s*U\s*D\s*G\s*M\s*E\s*N\s*T\s*$"], "line", 0.85),
            "end": _k("facts", [r"I\s+have\s+heard", r"Heard\s+(?:the\s+)?(?:learned|ld\.)"], "line", 0.7),
        },
        "issues": {"issues": _k("issues", [r"(?:Whether|WHETHER)\b", r"point[s]?\s+for\s+consideration"],
                                "span", 0.65)},
        "reasoning": {"from": _k("reasoning", [r"I\s+have\s+heard", r"Heard\s+(?:the\s+)?(?:learned|ld\.)"],
                                 "line", 0.7)},
        "operative": {"conclusion": _k("operative", [r"In\s+the\s+result", r"hence,?\s+(?:the\s+)?(?:petition|bail)"] ,
                                       "span", 0.8)},
        "signature": {"judge_sign": _k("signature", [r"^\s*JUDGE\s*$", r"[A-Z][A-Za-z\.\s]+,?\s*J\.\s*$"],
                                       "line", 0.9)},
        "noise": dict(COMMON_NOISE_KEYS),
        "statute_style": {"sections": _k("statute_style", [r"\bSections?\s+\d+[^\n]{0,80}"], "line", 0.8)},
    },

    # ── Madurai Bench, "( Criminal Jurisdiction )" order sheet ─────────────
    "KEY-MHC-MB-CRIM": {
        "identity": {
            "case_no": _k("identity", [r"(?m)^\s*((?:CRL\s*OP|Crl\.?O\.?P|CRL\s*MP|CRL\s*A|WP\s*Crl)"
                                       r"[\s\.]*\(?MD\)?[^\n]{0,50}?of\s+\d{4})"], "line", 0.95),
            "page_clock": _k("identity", [r"^\s*\d{1,2}/\d{1,2}\s*$"], "line", 0.9,
                             "registry page clock '1/6'"),
        },
        "forum": {
            "court_line": _k("forum", [r"BEFORE\s+THE\s+MADURAI\s+BENCH\s+OF\s+MADRAS\s+HIGH\s+COURT"],
                             "line", 0.98),
            "jurisdiction": _k("forum", [r"\(\s*Criminal\s+Jurisdiction\s*\)"], "line", 0.98),
        },
        "dates": {
            "decision_date": _k("dates", [r"Date\s*:\s*(\d{1,2}[./]\d{1,2}[./]\d{4})"], "line", 0.95),
            "reserved_on": _k("dates", [r"RESERVED\s+ON\s*:\s*([^\n]+)"], "line", 0.95),
            "pronounced_on": _k("dates", [r"PRONOUNCED\s+ON\s*:\s*([^\n]+)"], "line", 0.95),
        },
        "coram": {
            "judge": _k("coram", [r"PRESENT\s*\n+\s*(?:The\s+)?Hon[`’'b]?le\s+[^\n]+"], "block", 0.95),
        },
        "parties": {
            "petitioner": _k("parties", [r"\.\.\s*Petitioners?\s*/", r"\.\.\s*Petitioners?"], "block", 0.9),
            "respondent": _k("parties", [r"\.\.\s*Respondents?\s*/", r"\.\.\s*Respondents?"], "block", 0.9),
            "versus": _k("parties", [r"^\s*Vs\.?\s*$"], "line", 0.95),
            "accused_tag": _k("parties", [r"Accused\s*\d"], "line", 0.75),
        },
        "counsel": {
            "for_petitioner": _k("counsel", [r"For\s+Petitioners?\s*:"], "block", 0.9),
            "for_respondent": _k("counsel", [r"For\s+Respondents?\s*:"], "block", 0.9),
        },
        "relief": {"prayer": _k("relief", [r"PRAYER\s*:?-?", r"PETITION\s+FOR\s+BAIL"], "span", 0.95)},
        "facts": {
            "start": _k("facts", [r"^\s*ORDER\s*[:\-]\s*", r"The\s+Court\s+made\s+the\s+following\s+order",
                                    r"^\s*ORDER\s*$", r"^\s*The\s+petitioners?\b"], "line", 0.85),
            "end": _k("facts", [r"^\s*ORDER\s*$", r"Considering\s+the", r"Having\s+considered",
                                r"On\s+the\s+other\s+hand"], "line", 0.7),
        },
        "issues": {"issues": _k("issues", [r"point[s]?\s+for\s+consideration", r"(?:Whether|WHETHER)\b"],
                                "span", 0.6)},
        "reasoning": {"from": _k("reasoning", [r"Having\s+(?:heard|considered)", r"Considering\s+the"], "line", 0.7)},
        "operative": {"conclusion": _k("operative", [r"In\s+the\s+result", r"hence,?\s+this\s+(?:petition|criminal)"],
                                       "span", 0.8)},
        "signature": {
            "judge_sign": _k("signature", [r"[A-Z][A-Z\.\s]+,?\s*J\s*$", r"^\s*JUDGE\s*$"], "line", 0.85),
        },
        "noise": dict({**COMMON_NOISE_KEYS,
                       "page_clock_slash": _k("noise", [r"^\s*\d{1,2}/\d{1,2}\s*$"], "line", 1.0)}),
        "statute_style": {
            "sections": _k("statute_style", [r"\bSections?\s+\d+[^\n]{0,80}(?:B\.?N\.?S\.?S?|NDPS|Act)"],
                           "line", 0.8),
            "bail_provision": _k("statute_style", [r"Section\s+4(?:3[789]|8[0-9])\s+(?:of\s+)?(?:BNSS|Cr\.?P\.?C)"],
                                 "line", 0.85),
        },
    },

    # ── Chhattisgarh ───────────────────────────────────────────────────────
    "KEY-CGHC": {
        "identity": {
            "neutral_citation": _k("identity", [r"(\d{4}\s*:\s*CGHC\s*:\s*\d+)"], "line", 0.97),
            "cnr": _k("identity", [r"^\s*([A-Z]{4}\d{12})\s*$"], "line", 0.9),
            "case_no": _k("identity", [r"(?m)^\s*((?:WPS|WPC|WP|CRL\s*A|CRL\s*OP|CRA|MCRC)"
                                       r"\s*No\.?\s*\d+\s*of\s*\d{4})"], "line", 0.95),
            "batch": _k("identity", [r"(?m)^\s*((?:WPS|WPC|WP)\s*No\.?\s*\d+\s*of\s*\d{4})\s*$"], "line", 0.9,
                        "companion matters appear as further captions"),
        },
        "forum": {
            "court_line": _k("forum", [r"HIGH\s+COURT\s+OF\s+CHHATTISGARH(?:\s+AT\s+BILASPUR)?"], "line", 0.98),
            "reportability": _k("forum", [r"^\s*(N?AFR)\s*$"], "line", 0.9),
        },
        "dates": {
            "reserved_on": _k("dates", [r"Order\s+Reserved\s+on\s*:?\s*([^\n]+)"], "line", 0.95),
            "decision_date": _k("dates", [r"Order\s+passed\s+on\s*:?\s*([^\n]+)",
                                          r"^\s*(\d{1,2}/\d{1,2}/\d{4})\s*$"], "line", 0.95),
        },
        "coram": {
            "judge": _k("coram", [r"Hon[’'`]?ble\s+(?:Shri|Smt\.?|Dr\.?)?\s*Justice\s+[^\n]+"], "line", 0.95),
            "judge_sign_name": _k("coram", [r"\(([A-Z][A-Za-z\.\s]+)\)\s*\n\s*Judge"], "line", 0.9),
        },
        "parties": {
            "petitioner": _k("parties", [r"---\s*Petitioners?\)", r"\.\.\.\s*Petitioners?"], "block", 0.92),
            "respondent": _k("parties", [r"---\s*Respondents?\)", r"\.\.\.\s*Respondents?"], "block", 0.92),
            "versus": _k("parties", [r"^\s*versus\s*$", r"^\s*Versus\s*$"], "line", 0.95),
        },
        "counsel": {
            "for_petitioner": _k("counsel", [r"For\s+Petitioners?\s*\n?\s*:"], "block", 0.9),
            "for_respondent": _k("counsel", [r"For\s+Respondent(?:s)?(?:/State)?\s*\n?\s*:"], "block", 0.9),
        },
        "relief": {
            "prayer": _k("relief", [r"relief\(s\)\s*:?-?", r"pray(?:ed|er)\s+for\s+(?:the\s+)?following"], "span", 0.92),
        },
        "facts": {
            "start": _k("facts", [r"^\s*Order\s+on\s+Board\s*$", r"^\s*1\s*[\.\)]\s"],
                        "line", 0.85),
            "end": _k("facts", [r"^\s*\d+\s*[\.\)]\s*(?:I\s+have\s+heard|Having\s+heard|Heard\s+learned)",
                                r"I\s+have\s+heard\s+learned", r"^\s*Submission"], "line", 0.7),
            "explicit_heading": _k("facts", [r"(?i)^\s*(?:Brief\s+Facts?|Facts?\s+of\s+the\s+Case|Factual\s+Matrix)[^\n]*$"],
                                   "line", 0.95),
        },
        "issues": {"issues": _k("issues", [r"substantial\s+question", r"framed\s+the\s+following", r"§" ], "span", 0.6)},
        "reasoning": {"from": _k("reasoning", [r"I\s+have\s+heard\s+learned", r"Having\s+heard"], "line", 0.75)},
        "operative": {"conclusion": _k("operative", [r"With\s+the\s+(?:aforesaid|above)\s+(?:observations|directions)",
                                                     r"stands?\s+(?:allowed|dismissed|disposed)"], "span", 0.85)},
        "signature": {
            "judge_sign": _k("signature", [r"Sd/-", r"^\s*Judge\s*$"], "line", 0.9),
        },
        "noise": dict({**COMMON_NOISE_KEYS,
                       "bare_page_number": _k("noise", [r"^\s*\d{1,3}\s*$"], "line", 1.0),
                       "court_staff_names": _k("noise", [r"^\s*(?:Shayna|Vishakha|[A-Z][a-z]+\s*/\s*[A-Z][a-z]+)\s*$"],
                                               "line", 0.6, "stenographer/typist names below the signature")}),
        "statute_style": {
            "sections": _k("statute_style", [r"\bSection[s]?\s+\d+[^\n]{0,80}"], "line", 0.8),
            "rules": _k("statute_style", [r"\bRule[s]?\s+\d+"], "line", 0.8),
        },
    },

    # ── Patna ──────────────────────────────────────────────────────────────
    "KEY-PATNA": {
        "identity": {
            "case_no": _k("identity", [r"(?m)^\s*((?:Civil|Criminal)\s+(?:Writ\s+Jurisdiction|Appeal|Revision)"
                                       r"[^\n]{0,40}?(?:Case\s+)?No\.?\s*\d+\s*of\s*\d{4})"], "line", 0.97),
            "running_header": _k("identity", [r"Patna\s+High\s+Court\s+\w+\s+No\.?\s*\d+\s+of\s+\d{4}\s+dt\.?\s*[\d\-]+"],
                                 "line", 0.95),
            "page_clock": _k("identity", [r"^\s*(\d+/\d+)\s*$"], "line", 0.9),
        },
        "forum": {
            "court_line": _k("forum", [r"IN\s+THE\s+HIGH\s+COURT\s+OF\s+JUDICATURE\s+AT\s+PATNA"], "line", 0.98),
            "coram": _k("forum", [r"CORAM\s*:", r"HON[’'`]?BLE\s+(?:THE\s+)?(?:ACTING\s+)?CHIEF\s+JUSTICE",
                                  r"HON[’'`]?BLE\s+MR\.?\s+JUSTICE"], "line", 0.9),
        },
        "dates": {
            "decision_date": _k("dates", [r"dt\.?\s*(\d{1,2}-\d{1,2}-\d{4})",
                                          r"Dated\s*:?\s*(\d{1,2}[-./]\d{1,2}[-./]\d{4})"], "line", 0.95),
        },
        "coram": {
            "judge": _k("coram", [r"HON[’'`]?BLE\s+(?:MR\.?|MS\.?|DR\.?)?\s*JUSTICE\s+[^\n]+"], "line", 0.92),
            "cj": _k("coram", [r"HON[’'`]?BLE\s+THE\s+(?:ACTING\s+)?CHIEF\s+JUSTICE"], "line", 0.9),
        },
        "parties": {
            "petitioner": _k("parties", [r"\.\.\.\s+\.\.\.\s+Petitioner", r"Petitioner/s"], "block", 0.92),
            "respondent": _k("parties", [r"\.\.\.\s+\.\.\.\s+Respondent", r"Respondent/s"], "block", 0.92),
            "versus": _k("parties", [r"^\s*Versus\s*$"], "line", 0.95),
        },
        "counsel": {
            "appearance": _k("counsel", [r"^\s*Appearance\s*:"], "block", 0.95),
            "for_petitioner": _k("counsel", [r"For\s+the\s+Petitioner/s"], "block", 0.9),
            "for_respondent": _k("counsel", [r"For\s+the\s+Respondent/s"], "block", 0.9),
        },
        "relief": {
            "prayer": _k("relief", [r"(?i)^\s*(?:Prayer|Relief)[^\n]*$", r"^\s*\(i\)\s"], "span", 0.9),
        },
        "facts": {
            "explicit_heading": _k("facts", [r"(?i)^\s*(?:Brief\s+Facts?(?:\s+Of\s+(?:The\s+)?Case)?|Facts?\s+of\s+the\s+Case|Factual\s+Background)[^\n]*$"],
                                   "line", 0.97),
            "start": _k("facts", [r"(?i)^\s*Brief\s+Facts", r"^\s*3\s*[\.\)]\s"], "line", 0.8),
            "end": _k("facts", [r"(?i)^\s*(?:Submission|Argument|Consideration|Discussion|Analysis)",
                                r"^\s*\d+\s*[\.\)]\s*It\s+is\s+submitted"], "line", 0.75),
        },
        "issues": {
            "issues": _k("issues", [r"(?i)^\s*(?:Points?\s+for\s+consideration|Consideration\s+and\s+analysis)",
                                    r"(?i)following\s+questions?"], "span", 0.8),
        },
        "reasoning": {
            "from": _k("reasoning", [r"(?i)^\s*(?:Consideration|Discussion|Analysis)", r"(?i)Having\s+heard"],
                       "line", 0.75),
        },
        "operative": {
            "conclusion": _k("operative", [r"With\s+the\s+(?:aforementioned|aforesaid)\s+observations",
                                           r"stands?\s+(?:disposed|allowed|dismissed)"], "span", 0.85),
        },
        "signature": {
            "judge_sign": _k("signature", [r"^\s*(?:Chief\s+)?Justice\s*$", r"^\s*JUDGE\s*$",
                                           r"^\s*\(.*\)\s*$"], "line", 0.85),
        },
        "noise": dict({**COMMON_NOISE_KEYS,
                       "banner_equals": _k("noise", [r"^\s*={10,}\s*$"], "line", 1.0),
                       "patna_running_header": _k("noise", [r"^\s*Patna\s+High\s+Court\s+\w+\s+No\..*$"], "line", 1.0)}),
        "statute_style": {
            "articles": _k("statute_style", [r"\bArticles?\s+\d+(?:\s*,\s*\d+)*"], "line", 0.9),
            "sections": _k("statute_style", [r"\bSection[s]?\s+\d+[^\n]{0,60}"], "line", 0.75),
            "resolution_refs": _k("statute_style", [r"memo\s+no\.?\s*\d+", r"Annexure-?\s*\d+"], "line", 0.8),
        },
    },

    # ── Punjab & Haryana ───────────────────────────────────────────────────
    "KEY-PHHC": {
        "identity": {
            "case_no": _k("identity", [r"(?m)^\s*((?:CWP|CRA|CRM|RSA|CRR|CUSAP|CIVIL\s+WRIT)[-\s]?"
                                       r"\d+[-\s]?of?[-\s]?\d{4}[^\n]{0,15})"], "line", 0.9),
            "case_no_alt": _k("identity", [r"(CWP-?\d+-?\d{4}(?:\s*\(O&M\))?)"], "line", 0.95),
        },
        "forum": {
            "court_line": _k("forum", [r"HIGH\s+COURT\s+OF\s+PUNJAB\s+AN\s?D\s+HARYANA(?:\s+AT\s+CHANDIGARH)?"],
                             "line", 0.95),
            "coram": _k("forum", [r"CORAM\s*:\s*(?:HON[’'`]?N?'?BLE\s+)?(?:MR\.?|MS\.?|DR\.?)?\s*JUSTICE[^\n]*"],
                        "line", 0.92),
        },
        "dates": {
            "decision_date": _k("dates", [r"Date\s+of\s+Decision\s*:?-?\s*(\d{1,2}[./]\d{1,2}[./]\d{4})"], "line", 0.97),
        },
        "coram": {
            "judge": _k("coram", [r"(?:HON[’'`]?N?'?BLE|N'BLE)\s+(?:MR\.?|MS\.?|DR\.?)?\s*JUSTICE\s+([A-Z\.\s]+)"],
                        "line", 0.92),
            "judge_short": _k("coram", [r"^([A-Z][A-Z\s]{3,40}),\s*J\.\s*$"], "line", 0.88),
        },
        "parties": {
            "petitioner": _k("parties", [r"…\s*Petitioners?", r"\.\.\.\s*Petitioners?"], "block", 0.9),
            "respondent": _k("parties", [r"\.\.\.\s*Respondents?", r"…\s*Respondents?"], "block", 0.9),
            "versus": _k("parties", [r"^\s*Versus\s*$"], "line", 0.95),
        },
        "counsel": {
            "present_block": _k("counsel", [r"^\s*Present\s*:-", r"^\s*Present\s*:"], "block", 0.92),
        },
        "relief": {
            "prayer": _k("relief", [r"(?i)prayer\s+for", r"(?i)filed\s+(?:this|the)\s+(?:civil\s+)?writ\s+petition"],
                         "span", 0.85),
        },
        "facts": {
            "start": _k("facts", [r"^\s*[A-Z][A-Z\s]{2,40},\s*J\.\s*$", r"^\s*\d+\s*[\.\)]\s"], "line", 0.85),
            "end": _k("facts", [r"(?i)^\s*(?:I\s+have\s+heard|Learned\s+counsel|Arguments?|Discussion)",
                                r"(?i)perused\s+the"], "line", 0.72),
        },
        "issues": {"issues": _k("issues", [r"(?i)question[s]?\s+of\s+law", r"(?i)whether\b"], "span", 0.6)},
        "reasoning": {"from": _k("reasoning", [r"(?i)I\s+have\s+heard", r"(?i)Having\s+heard"], "line", 0.75)},
        "operative": {
            "conclusion": _k("operative", [r"(?i)petition\s+stands?\s+(?:dismissed|allowed|disposed)",
                                           r"(?i)accordingly,?\s+the\s+(?:present\s+)?writ\s+petition"],
                             "span", 0.85),
        },
        "signature": {
            "judge_sign": _k("signature", [r"\(\s*[A-Z][A-Za-z\.\s]+\s*\)\s*\n\s*JUDGE", r"^\s*JUDGE\s*$"], "line", 0.88),
            "attestation": _k("signature", [r"I\s+attest\s+to\s+the\s+accuracy\s+and", r"integrity\s+of\s+this\s+document"],
                              "line", 0.95),
        },
        "noise": dict({**COMMON_NOISE_KEYS,
                       "star_rule": _k("noise", [r"^\s*\*{4,}\s*$"], "line", 1.0),
                       "case_short_header": _k("noise", [r"^\s*CWP-?\d+-?\d{4}\s*(?:\(O&M\))?\s*$"], "line", 0.9),
                       "dsc_stamp": _k("noise", [r"^\s*\d{4}\.\d{2}\.\d{2}\s+\d{2}:\d{2}\s*$"], "line", 0.9)}),
        "statute_style": {
            "articles": _k("statute_style", [r"\bArticles?\s+226\b", r"\bArticles?\s+\d+(?:\s*,\s*\d+)*"], "line", 0.9),
            "rules": _k("statute_style", [r"\bRules?\s+\d+"], "line", 0.8),
        },
    },

    # ── Supreme Court ──────────────────────────────────────────────────────
    "KEY-SC": {
        "identity": {
            "case_no": _k("identity", [r"(?m)^\s*((?:Civil|Criminal)\s+Appeal\s+No\.?\s*\d+\s+of\s+\d{4})"], "line", 0.95),
            "slp": _k("identity", [r"SLP\s*\((?:\w+)\)\s*No\.?\s*\d+\s+of\s+\d{4}"], "line", 0.9),
            "citation": _k("identity", [r"\(\d{4}\)\s*\d+\s*SCC\s*\d+"], "line", 0.85),
        },
        "forum": {
            "court_line": _k("forum", [r"IN\s+THE\s+SUPREME\s+COURT\s+OF\s+INDIA"], "line", 0.98),
            "jurisdiction": _k("forum", [r"(?:CIVIL|CRIMINAL)\s+APPELLATE\s+JURISDICTION"], "line", 0.95),
        },
        "dates": {
            "decision_date": _k("dates", [r"(?:Date\s*:?\s*)?(\d{1,2}[./-]\d{1,2}[./-]\d{4})\s*$"], "line", 0.7),
        },
        "coram": {
            "judge": _k("coram", [r"HON[’'`]?BLE\s+(?:MR\.?|MS\.?|DR\.?)?\s*JUSTICE\s+[^\n]+"], "line", 0.92),
        },
        "parties": {
            "petitioner": _k("parties", [r"\.\.\.\s*Appellant", r"\.\.\.\s*Petitioner"], "block", 0.9),
            "respondent": _k("parties", [r"\.\.\.\s*Respondent"], "block", 0.9),
            "versus": _k("parties", [r"^\s*Versus\s*$", r"^\s*Vs\.?\s*$"], "line", 0.9),
        },
        "counsel": {"appearance": _k("counsel", [r"For\s+the\s+(?:Appellant|Petitioner)"], "block", 0.9)},
        "relief": {"prayer": _k("relief", [r"(?i)leave\s+granted", r"(?i)prayer"], "span", 0.75)},
        "facts": {
            "start": _k("facts", [r"^\s*J\s*U\s*D\s*G\s*M\s*E\s*N\s*T\s*$"], "line", 0.9),
            "end": _k("facts", [r"(?i)I\s+have\s+heard", r"(?i)^\s*\d+\s*[\.\)]\s*Having\s+heard"], "line", 0.7),
        },
        "issues": {"issues": _k("issues", [r"(?i)question[s]?\s+(?:of\s+law|that\s+arise)", r"(?i)whether\b"],
                                "span", 0.7)},
        "reasoning": {"from": _k("reasoning", [r"(?i)Having\s+heard", r"(?i)I\s+have\s+heard"], "line", 0.75)},
        "operative": {"conclusion": _k("operative", [r"(?i)appeal\s+is\s+(?:allowed|dismissed|disposed)",
                                                     r"(?i)In\s+the\s+result"], "span", 0.85)},
        "signature": {"judge_sign": _k("signature", [r"^\s*JUDGE\s*$", r"\([A-Z][A-Za-z\.\s]+\)"], "line", 0.85)},
        "noise": dict(COMMON_NOISE_KEYS),
        "statute_style": {"sections": _k("statute_style", [r"\bSection[s]?\s+\d+"], "line", 0.8)},
    },

    # ── Generic fallback ───────────────────────────────────────────────────
    "KEY-GENERIC": {
        "identity": {
            "case_no": _k("identity", [r"(?im)^\s*([A-Z][A-Za-z\.\s\(\)&]{2,30}No\.?\s*\d+[\s\w\-\/&]{0,30}of\s+\d{4})"],
                          "line", 0.7),
            "cnr": _k("identity", [r"CNR\s*:?\s*\{?([A-Z]{4}\d{12})\}?"], "line", 0.9),
        },
        "forum": {
            "court_line": _k("forum", [r"(?:IN\s+THE|BEFORE\s+THE)?\s*HIGH\s+COURT\s+OF[^\n]+"], "line", 0.8),
        },
        "dates": {
            "decision_date": _k("dates", [r"(?:DATED|Date|Pronounced\s+on|Order\s+passed\s+on)\s*:?-?\s*"
                                          r"(\d{1,2}[-./]\d{1,2}[-./]\d{4})"], "line", 0.85),
        },
        "coram": {"judge": _k("coram", [r"(?:CORAM|PRESENT|BEFORE)\s*:?\s*\n?[^\n]*JUSTICE[^\n]+"], "block", 0.8)},
        "parties": {
            "petitioner": _k("parties", [r"\.\.\.?\s*Petitioner", r"Petitioner/s"], "block", 0.8),
            "respondent": _k("parties", [r"\.\.\.?\s*Respondent", r"Respondent/s"], "block", 0.8),
            "versus": _k("parties", [r"^\s*(?:Vs\.?|Versus)\s*$"], "line", 0.9),
        },
        "counsel": {"for_petitioner": _k("counsel", [r"For\s+the\s+Petitioners?"], "block", 0.8)},
        "relief": {"prayer": _k("relief", [r"PRAYER", r"(?i)prayer"], "span", 0.85)},
        "facts": {
            "start": _k("facts", [r"^\s*(?:ORDER|J\s*U\s*D\s*G\s*M\s*E\s*N\s*T)\s*$"], "line", 0.75),
            "end": _k("facts", [r"(?i)I\s+have\s+heard", r"(?i)Having\s+heard"], "line", 0.7),
        },
        "issues": {"issues": _k("issues", [r"(?i)whether\b"], "span", 0.6)},
        "reasoning": {"from": _k("reasoning", [r"(?i)I\s+have\s+heard", r"(?i)Having\s+heard"], "line", 0.7)},
        "operative": {"conclusion": _k("operative", [r"(?i)In\s+the\s+result", r"(?i)petition\s+is\s+(?:allowed|dismissed)"],
                                       "span", 0.8)},
        "signature": {"judge_sign": _k("signature", [r"^\s*JUDGE\s*$"], "line", 0.8)},
        "noise": dict(COMMON_NOISE_KEYS),
        "statute_style": {"sections": _k("statute_style", [r"\bSection[s]?\s+\d+"], "line", 0.75)},
    },
}


# The Madurai Bench prints the same reserved-judgment furniture as the Principal
# Seat (RESERVED ON / PRONOUNCED ON, prayer units, J. signature); the two
# profiles differ only in the caption, which the profile carries.  Sharing one
# key set keeps the anchors in a single place.
KEY_SETS["KEY-MHC-MB-RESERVED"] = KEY_SETS["KEY-MHC-PS-RESERVED"]

# ---------------------------------------------------------------------------
# 3b. Shared key set for the wider Indian High Court corpus
# ---------------------------------------------------------------------------
# The expanded corpus (596 unique documents) spans 20+ registries.  Bespoke key
# sets per registry would be mostly duplication, so a single superset key set
# captures the anchors that Indian High Court templates share, and each registry
# profile merges in its own small extras key set on top.

KEY_SETS["KEY-HC-COMMON"] = {
    "identity": {
        "case_no": _k("identity", [
            r"(?im)^\s*((?:CRL|CRL\.|C\.?R\.?M|W\.?P|WP|WA|CWP|CMPMO|CRP|RSA|FAO|CMA|CS|OS|ARB|"
            r"ABLAPL|MAC|A\.?\s?B\.?\s?A|BA|OP|OPC|MFA|ITA|CRA|CRM|RERA|SA|TA)[\s\.\(\)]*"
            r"[A-Z\.\(\)\/\s]{0,40}?(?:No\.?|NO\.?)\s*[\d\s\-\/]{1,18}?(?:of|OF)\s*\d{4})",
            r"(?im)^\s*([A-Z][A-Za-z\.\s\(\)\/\-]{2,50}(?:No\.?|NO\.?)\s*[\d]{1,8}\s*(?:of|OF|/)\s*\d{4})",
        ], "line", 0.9),
        "case_no_colon": _k("identity", [r"(?im)^\s*Case\s*(?:No\.?|:-)\s*:?\s*([^\n]{3,80})"], "line", 0.92,
                            "Allahabad 'Case :- …' / Gauhati 'Case No. : …'"),
        "case_no_slash": _k("identity", [r"(?im)^\s*([A-Z][A-Za-z\.\(\)\s]{1,30}?No\.?\s*[\d]{1,6}\s*/\s*\d{4})"],
                            "line", 0.85),
        "cnr": _k("identity", [r"CNR\s*(?:No\.?)?\s*:?\s*\{?([A-Z]{2,4}\d{8,})\}?"], "line", 0.95),
        "neutral_citation": _k("identity", [
            r"\(?\s*(\d{4}\s*:\s*[A-Z]{2,6}[A-Z\-]*\s*(?:-[A-Z]{2,4})?\s*:\s*\d+(?:\s*-\s*[A-Z]{1,3})?)\s*\)?"
        ], "line", 0.95),
        "registry_code": _k("identity", [r"\b([A-Z]{2,4}HC\d{10,})\b"], "line", 0.9),
        "citation_field": _k("identity", [r"Citation\s*:\s*([\d]{4}:[A-Z]{2,6}:\d+)"], "line", 0.95),
        "court_no": _k("identity", [r"(?im)^\s*Court\s+No\.?\s*-?\s*(\d+)"], "line", 0.85),
        "serial_no": _k("identity", [r"(?im)^\s*Serial\s+No\.?\s*([\d\.]+)"], "line", 0.8),
        "year_field": _k("identity", [r"CASE\s+NO\s*:.*?\(YEAR\s*:\s*(\d{4})\)"], "line", 0.9),
    },
    "forum": {
        "court_line": _k("forum", [
            r"(?im)^\s*.*(?:IN\s+THE\s+|BEFORE\s+THE\s+)?(?:HIGH\s+COURT|SUPREME\s+COURT|COURT\s+OF\s+JUDICATURE)[^\n]*$"
        ], "line", 0.9),
        "bench": _k("forum", [r"(?im)^\s*(?:AT\s+[A-Z][A-Z\s]{2,25}|[A-Z\s]*BENCH(?:\s+AT\s+[A-Z\s]+)?)\s*$"],
                    "line", 0.8),
        "jurisdiction": _k("forum", [
            r"\(\s*(?:Special\s+Original|Criminal|Civil|Original|Appellate|Extraordinary)\s+Jurisdiction\s*\)",
            r"(?:JUDICIAL\s+)?APPELLATE\s+JURISDICTION",
        ], "line", 0.85),
        "reportability": _k("forum", [r"(?im)^\s*(N?A\.?F\.?R\.?|REPORTABLE|NON-REPORTABLE)\s*$"], "line", 0.85),
    },
    "dates": {
        "decision_date": _k("dates", [
            r"DATED\s+THIS\s+THE\s+(\d{1,2}(?:ST|ND|RD|TH)?\s+DAY\s+OF\s+[A-Z]+,?\s*\d{4})",
            r"(?:Date\s+of\s+[Dd]ecision|Decided\s+on|Date\s+of\s+[Pp]ronouncement|Delivered\s+on|"
            r"Pronounced\s+on|Order\s+Date|ORDER\s+DATED|Date\s+of\s+Decision)\s*:?-?\s*([^\n]{6,40})",
            r"(?im)^\s*(\d{1,2}\s+[A-Z][a-z]+\s*,?\s*\d{4})\s*$",
            r"(?im)^\s*DATE\s*:\s*([A-Z][a-z]+\s+\d{1,2},?\s*\d{4})",
        ], "line", 0.92),
        "reserved_on": _k("dates", [r"Reserved\s+on\s*:?-?\s*([^\n]{4,30})"], "line", 0.9),
        "pronounced_on": _k("dates", [r"(?:Pronounced|Delivered|Decided)\s+on\s*:?-?\s*([^\n]{4,30})"], "line", 0.9),
        "uploaded_on": _k("dates", [r"Uploaded\s+on\s*:?-?\s*([^\n]{4,30})"], "line", 0.85),
    },
    "coram": {
        "judge": _k("coram", [
            r"(?:THE\s+)?HON(?:['\u2019`]?BLE|\.BLE|OURABLE)?\s+(?:MR\.?|MS\.?|MRS\.?|DR\.?|SRI|SMT\.?)?\s*"
            r"(?:AND\s+)?JUSTICE\s+([^\n]{3,60})",
            r"THE\s+HONOURABLE\s+(?:SRI|SMT|MR|MS)\.?\s+JUSTICE\s+([^\n]{3,60})",
        ], "line", 0.92),
        "coram_inline": _k("coram", [r"CORAM\s*:\s*([A-Z][A-Z\.,\s&]{5,220})"], "line", 0.9,
                           "brief cards list the bench comma-separated on one line"),
        "coram_block": _k("coram", [r"(?im)^\s*(?:CORAM|PRESENT|BEFORE)\s*:?\s*$"], "line", 0.85),
        "chief_justice": _k("coram", [r"(?:HON[’'`]?BLE|THE)\s+(?:THE\s+)?(?:ACTING\s+)?CHIEF\s+JUSTICE[^\n]*"],
                            "line", 0.85),
        "signature_name": _k("coram", [r"([A-Z][A-Z\.\s]{3,40}),?\s*J\.\s*$"], "line", 0.85),
    },
    "parties": {
        "petitioner": _k("parties", [
            r"(?:\.{2,}|\u2026|\.{2,}\.)\s*(?:Appellants?|Petitioners?|Applicants?)\b",
            r"(?im)^\s*(?:Applicant|Petitioner)\s*:-",
            r"(?im)^\s*Through\s*:",
        ], "block", 0.88),
        "respondent": _k("parties", [
            r"(?:\.{2,}|\u2026)\s*(?:Respondents?|Opposite\s+Party|Complainants?)\b",
            r"(?im)^\s*(?:Opposite\s+Party|Respondent)\s*:-",
        ], "block", 0.88),
        "versus": _k("parties", [r"(?im)^\s*(?:Vs\.?|V/s\.?|VERSUS|Versus|-Vs-|v/s|V/s)\s*$"], "line", 0.95),
        "party_line": _k("parties", [r"(?im)^\s*(?:Applicant\s*:-|Opposite\s+Party\s*:-)\s*(.+)$"], "line", 0.9),
    },
    "counsel": {
        "counsel_for": _k("counsel", [
            r"Counsel\s+for\s+(?:Applicant|Opposite\s+Party|Petitioner|Respondent|Appellant)",
            r"For\s+(?:the\s+)?(?:Petitioners?|Respondents?|Appellants?|Applicants?)",
            r"Through\s*:?\s*-?\s*(?:Mr|Ms|Mrs|Sri|Smt)",
            r"Represented\s+by\s+Adv",
        ], "block", 0.9),
    },
    "relief": {
        "prayer": _k("relief", [r"PRAY(?:ER)?\s*:?-?", r"(?i)prays?\s+that", r"relief\(s\)"], "span", 0.88),
    },
    "facts": {
        "explicit_heading": _k("facts", [
            r"(?i)^\s*(?:Brief\s+Facts?(?:\s+Of\s+(?:The\s+)?Case)?|Facts?\s+of\s+the\s+Case|"
            r"Factual\s+(?:Matrix|Background)|JUDGMENT\s*&\s*REASONING|JUDICIAL\s+HEADNOTE)[^\n]*$"
        ], "line", 0.95),
        "start": _k("facts", [
            r"(?im)^\s*(?:ORDER|JUDGMENT|J\s*U\s*D\s*G\s*M\s*E\s*N\s*T)\s*[:\-]?\s*$",
            r"In\s+Re\s*:?\s*An?\s+application",
            r"(?im)^\s*1\s*[\.\)]\s",
        ], "line", 0.82),
        "end": _k("facts", [
            r"I\s+have\s+heard", r"Having\s+heard", r"Heard\s+(?:the\s+)?(?:learned|ld\.)",
            r"(?i)^\s*(?:Submission|Consideration|Discussion|Analysis)",
        ], "line", 0.75),
    },
    "issues": {
        "issues": _k("issues", [r"(?i)whether\b", r"point[s]?\s+for\s+consideration", r"(?i)question[s]?\s+of\s+law"],
                     "span", 0.65),
    },
    "reasoning": {
        "from": _k("reasoning", [r"I\s+have\s+heard", r"Having\s+heard", r"(?i)^\s*(?:Consideration|Discussion|Analysis)"],
                   "line", 0.72),
    },
    "operative": {
        "conclusion": _k("operative", [
            r"(?i)In\s+the\s+result", r"(?i)With\s+the\s+(?:aforesaid|above|aforementioned)\s+observations",
            r"(?i)(?:petition|application|appeal)\s+(?:is|stands?)\s+(?:allowed|dismissed|disposed)",
            r"(?i)^\s*ORDER\s*:\s*(?:Decided|Allowed|Dismissed)",
        ], "span", 0.85),
    },
    "signature": {
        "judge_sign": _k("signature", [r"(?m)^\s*JUDGE\s*$", r"(?m)^\s*\(?[A-Z][A-Za-z\.\s]+\)?\s*$"], "line", 0.75),
        "sd_sign": _k("signature", [r"Sd/-"], "line", 0.85),
    },
    "noise": dict({**COMMON_NOISE_KEYS,
                   "page_of_n_nospace": _k("noise", [r"(?im)^\s*Page\s*No\.?#?\s*\d+\s*/\s*\d+\s*$"], "line", 1.0),
                   "n_of_m_plain": _k("noise", [r"(?im)^\s*\d+\s*of\s*\d+\s*$"], "line", 1.0),
                   "doc_header": _k("noise", [r"(?im)^\s*[\w\-\.]+\.docx?\s*$"], "line", 0.9),
                   "registry_code_line": _k("noise", [r"(?m)^\s*[A-Z]{2,4}HC\d{10,}\s*$"], "line", 0.95),
                   "cause_list_noise": _k("noise", [r"(?im)^\s*(?:Serial\s+No\.?|Supp\.?\s+List|Regular\s+List|"
                                                    r"Court\s+No\.?\s*-?\s*\d+|Item\s+No\.?\s*[\d\.]+)\s*$"],
                                          "line", 0.9),
                   }),
    "statute_style": {
        "sections": _k("statute_style", [r"\bSections?\s+\d+[^\n]{0,70}"], "line", 0.8),
        "articles": _k("statute_style", [r"\bArticles?\s+\d+"], "line", 0.85),
        "acts_referred": _k("statute_style", [r"Acts?\s+Referred"], "line", 0.9),
    },
}

# ── Extras merged on top of KEY-HC-COMMON, per registry family ──────────────
KEY_SETS["KEY-EXTRA-BRIEF-CARD"] = {
    "identity": {
        "case_no": _k("identity", [r"CASE\s+NO\s*:\s*([^\n\()]{4,90})"], "line", 0.95),
        "citation_field": _k("identity", [r"Citation\s*:\s*([\d]{4}:[A-Z]{2,6}:\d+)"], "line", 0.95),
    },
    "coram": {"coram_inline": _k("coram", [r"CORAM\s*:\s*([A-Z][A-Z\.,\s&]{5,220})"], "line", 0.95)},
    "facts": {
        "explicit_heading": _k("facts", [r"(?i)^\s*(?:JUDICIAL\s+HEADNOTE\s*&?\s*SUMMARY|RATIO\s+DECIDENDI)[^\n]*$"],
                               "line", 0.97),
        "end": _k("facts", [r"(?i)^\s*(?:JUDGMENT\s*&\s*REASONING|OPERATIVE\s+ORDER|RATIO\s+DECIDENDI)"], "line", 0.9),
    },
    "operative": {"conclusion": _k("operative", [r"(?i)^\s*ORDER\s*:\s*([A-Za-z ]+)",
                                                 r"(?i)^\s*OPERATIVE\s+ORDER"], "span", 0.92)},
    "parties": {"versus": _k("parties", [r"(?im)^\s*(?:Versus|Vs\.?)\s*$"], "line", 0.95)},
    "noise": {"lexguard_footer": _k("noise", [r"LexGuard\s+Immutable[^\n]*"], "line", 1.0)},
}

KEY_SETS["KEY-EXTRA-ALLAHABAD"] = {
    "identity": {
        "case_no_colon": _k("identity", [r"(?im)^\s*Case\s*:-\s*([^\n]{3,90})"], "line", 0.97),
        "neutral_citation": _k("identity", [r"Neutral\s+Citation\s+No\.?\s*-?\s*([\d]{4}:[A-Z\-]{2,12}:\d+)",
                                            r"(?<![\d:])(\d{4}:AHC[\-A-Z]*:\d+)"], "line", 0.95),
    },
    "parties": {
        "petitioner": _k("parties", [r"(?im)^\s*Applicant\s*:-"], "block", 0.95),
        "respondent": _k("parties", [r"(?im)^\s*Opposite\s+Party\s*:-"], "block", 0.95),
    },
    "counsel": {"counsel_for": _k("counsel", [r"Counsel\s+for\s+(?:Applicant|Opposite\s+Party)\s*:-"], "block", 0.95)},
    "dates": {"decision_date": _k("dates", [r"Order\s+Date\s*:-?\s*([\d\.\/]+)",
                                            r"(?:Reserved|Delivered)\s+on\s+([\d\.\/]+)"], "line", 0.9)},
    "signature": {"judge_sign": _k("signature", [r"HON[’'`]?BLE\s+[A-Z][A-Za-z\.\s]+,\s*J\."], "line", 0.9)},
}

KEY_SETS["KEY-EXTRA-GAUHATI"] = {
    "identity": {
        "case_no_colon": _k("identity", [r"(?im)^\s*Case\s+No\.?\s*:\s*([^\n]{3,60})"], "line", 0.97),
        "registry_code": _k("identity", [r"\b(GAHC\d{10,})\b"], "line", 0.92),
        "neutral_citation": _k("identity", [r"(\d{4}:GAU[\-A-Z]*:\d+)"], "line", 0.9),
    },
    "forum": {"bench": _k("forum", [r"(?im)^\s*([A-Z][A-Z\s]{2,20}BENCH)\s*$"], "line", 0.9)},
    "parties": {
        "petitioner": _k("parties", [r"(?im)^\s*\d*\.?\s*([A-Z][A-Z\s\.&\-]{3,80})\s*$",
                                     r"(?im)^\s*(?:Petitioners?|Applicants?)\s*$"], "block", 0.75),
    },
    "counsel": {"counsel_for": _k("counsel", [r"(?im)^\s*For\s+(?:the\s+)?(?:Petitioners?|Respondents?|Appellants?)"],
                                  "block", 0.88)},
    "noise": {"page_no_hash": _k("noise", [r"(?im)^\s*Page\s+No\.?#?\s*\d+/\d+\s*$"], "line", 1.0)},
}

KEY_SETS["KEY-EXTRA-CALCUTTA"] = {
    "identity": {
        "case_no": _k("identity", [r"(?im)^\s*((?:WPA|WP|CRR|CRAN|CRM|CRA|FMA|FAT|CUSTA|ITA|MFA|CPAN|CAN)\s*"
                                    r"\d{1,6}\s*(?:of|OF)\s*\d{4})",
                                    r"(?im)^\s*([A-Z]{2,6}\s*\(?[A-Z]*\)?\s*\d{1,6}\s+OF\s+\d{4})"], "line", 0.9),
        "court_no": _k("identity", [r"(?im)^\s*(?:CT\.?|Court)\s*No\.?\s*-?\s*(\d+)", r"(?im)^\s*\[\s*(\d{2,4})\s*\]"],
                       "line", 0.8),
    },
    "forum": {
        "court_line": _k("forum", [r"(?i)^\s*(?:In\s+The\s+)?High\s+Court\s+at\s+Calcutta", r"(?i)^\s*Calcutta\s+High\s+Court",
                                   r"(?i)Circuit\s+Bench\s+at\s+[A-Z][a-z]+"], "line", 0.95),
    },
    "parties": {
        "versus": _k("parties", [r"(?im)^\s*-?\s*(?:Vs|VS|-Vs-)\.?\s*-?\s*$"], "line", 0.9),
        "petitioner": _k("parties", [r"(?im)^\s*Between\s*:?\s*$", r"(?im)^\s*(?:Petitioner|Appellant)s?\s*$"], "block", 0.8),
    },
}

KEY_SETS["KEY-EXTRA-TELANGANA"] = {
    "dates": {"decision_date": _k("dates", [r"(?im)^\s*[A-Z]+DAY,\s+THE\s+[A-Z\s]+\d{4}\s*$"], "line", 0.9)},
    "coram": {"judge": _k("coram", [r"THE\s+HONOURABLE\s+(?:SRI|SMT|DR)\.?\s+JUSTICE\s+([^\n]{3,60})"], "line", 0.95)},
    "identity": {"case_no": _k("identity", [r"(?im)^\s*((?:WRIT\s+PETITION|CRIMINAL\s+APPEAL|C\.?C\.?|W\.?P\.?|"
                                            r"CMA|CRL\.?A|C\.R\.P\.?)\s*No\.?\s*:?\s*\d+\s*of\s*\d{4})"], "line", 0.92),
                 "registry_code": _k("identity", [r"\b([A-Z]{2,4}HC\d{10,})\b"], "line", 0.9)},
}

KEY_SETS["KEY-EXTRA-JK"] = {
    "counsel": {"counsel_for": _k("counsel", [r"(?im)^\s*Through\s*:?-?\s*(.+)$"], "line", 0.92)},
    "parties": {"versus": _k("parties", [r"(?im)^\s*(?:v/s|V/s|Versus|Vs\.?)\s*$"], "line", 0.95),
                "petitioner": _k("parties", [r"(?im)^\s*Through\s*:", r"(?:\.{2,})\s*(?:Appellant|Petitioner)"], "block", 0.85)},
    "dates": {"uploaded_on": _k("dates", [r"Uploaded\s+on\s*:?-?\s*([\d\.\/]+)"], "line", 0.9)},
}

KEY_SETS["KEY-EXTRA-ORISSA"] = {
    "identity": {"case_no": _k("identity", [r"(?im)^\s*([A-Z]{2,8}\s*(?:\(\w+\))?\s*No\.?\s*\d+\s*of\s*\d{4})"],
                                "line", 0.92),
                 "cnr": _k("identity", [r"CNR\s*No\.?\s*:?\s*(ODHC\d{10,})"], "line", 0.95)},
    "counsel": {"counsel_for": _k("counsel", [r"Represented\s+by\s+Adv\.?\s*-?\s*(.+)$"], "line", 0.92)},
    "parties": {"petitioner": _k("parties", [r"(?im)^\.{3,}\s*$", r"(?im)^\s*(?:Petitioner|Opp\.Party|Opposite\s+Party)\s*$"],
                                  "block", 0.8)},
}

KEY_SETS["KEY-EXTRA-MEGHALAYA"] = {
    "identity": {"serial_no": _k("identity", [r"(?im)^\s*Serial\s+No\.?\s*([\d\.]+)"], "line", 0.9),
                 "case_no": _k("identity", [r"(?im)^\s*((?:MC\[?W?P?\(?C\)?\]?|WP\(C\)|MC\(WPC\))[^\n]{0,30}?No\.?\s*[\d]+\s*of\s*\d{4})"],
                                "line", 0.92)},
    "dates": {"decision_date": _k("dates", [r"Date\s+of\s+(?:Decision|Pronouncement)\s*:?\s*([\d\.\/]+)"], "line", 0.95)},
}

KEY_SETS["KEY-EXTRA-KARNATAKA"] = {
    "dates": {"decision_date": _k("dates", [r"DATED\s+THIS\s+THE\s+(\d{1,2}(?:ST|ND|RD|TH)?\s+DAY\s+OF\s+[A-Z]+,?\s*\d{4})"],
                                   "line", 0.97)},
    "coram": {"judge": _k("coram", [r"THE\s+HON(?:'|\u2019)?BLE\s+(?:MR|MS|MRS|DR)\.?\s*JUSTICE\s+([^\n]{3,60})"], "line", 0.95)},
    "identity": {"case_no": _k("identity", [r"(?im)^\s*((?:WP|WA|W\.?P\.?|MFA|RFA|RSA|CRP|CCC|CWP|COMAP|Misc\.?\s?W)\s*"
                                             r"No\.?\s*[\d]+\s*of\s*\d{4})"], "line", 0.9)},
}

KEY_SETS["KEY-EXTRA-MADRAS-INRE"] = {
    "identity": {
        "case_no": _k("identity", [r"(?im)^\s*((?:C\.?R\.?M\.?|CRL\.?\s?[A-Z]{1,3}|Crl\.?[A-Z\.]{0,4})\s*\(?[A-Z]{0,3}\)?\s*"
                                    r"\d+\s+OF\s+\d{4})"], "line", 0.92),
        "court_no": _k("identity", [r"(?im)^\s*Court\s+No\.?\s*-?\s*(\d+)"], "line", 0.85),
        "serial_no": _k("identity", [r"(?im)^\s*Sl\.?\s*no\.?\s*([\d]+)"], "line", 0.8),
    },
    "forum": {"court_line": _k("forum", [r"(?i)Madras\s+High\s+Court|HIGH\s+COURT\s+OF\s+MADRAS"], "line", 0.9)},
    "facts": {"start": _k("facts", [r"In\s+Re\s*:?\s*An?\s+application"], "line", 0.9)},
}

KEY_SETS["KEY-EXTRA-BOMBAY"] = {
    "identity": {
        "case_no": _k("identity", [r"(?im)^\s*((?:CRIMINAL\s+)?(?:WRIT\s+PETITION|CR\.?\s?REVISION\s+APPLICATION|"
                                    r"CRIMINAL\s+APPEAL|WRIT\s+PETITION|APPEAL|APPLICATION|WP|CRL|CRA|REVN)"
                                    r"[^\n]{0,40}?NO\.?\s*[\d\s\-\/]{1,18}?OF\s*\d{4})"], "line", 0.92),
        "doc_header": _k("identity", [r"(?im)^\s*([\w\-\.]+\.docx?|[\d]+/\d+\s+\S+\.doc)\s*$"], "line", 0.6),
    },
    "forum": {"bench": _k("forum", [r"(?im)^\s*CIRCUIT\s+BENCH\s+AT\s+([A-Z\s]+)$"], "line", 0.9)},
    "coram": {"coram_inline": _k("coram", [r"CORAM\s*:\s*([A-Z][A-Za-z\.\s,]+?),?\s*J\."], "line", 0.95)},
    "dates": {"decision_date": _k("dates", [r"(?im)^\s*DATE\s*:\s*(.+)$"], "line", 0.92)},
    "parties": {"petitioner": _k("parties", [r"(?:\.{2,})\s*Petitioners?\s*$"], "block", 0.88)},
    "noise": {"n_of_m_plain": _k("noise", [r"(?im)^\s*\d+\s+of\s+\d+\s*$"], "line", 1.0)},
}


# ---------------------------------------------------------------------------
# 3c. Court registry → auto-generated drafting profiles
# ---------------------------------------------------------------------------
# Each entry adds a caption signal and a profile built on the shared key set plus
# that registry's extras.  Adding a court is one row, not a new module.
COURT_REGISTRY: List[Dict[str, Any]] = [
    {"key": "BOMBAY", "id": "BOMBAY-HC", "pattern": r"HIGH\s+COURT\s+OF\s+(?:JUDICATURE\s+AT\s+)?BOMBAY",
     "court": "Bombay High Court", "seat": "Principal Seat, Mumbai",
     "style": "JUDICATURE AT BOMBAY caption, '.doc' working header, optional CIRCUIT BENCH, "
              "'CORAM : NAME, J.' inline, 'DATE :' line, '…Applicant', 'V/s.'",
     "supporting": [("bombay_doc_header", 1.5), ("bombay_coram_date", 2.0), ("cnr_field", 0.8)],
     "extras": ["KEY-EXTRA-BOMBAY"], "strategy": "coram_order"},
    {"key": "DELHI", "id": "DELHI-HC", "pattern": r"HIGH\s+COURT\s+OF\s+DELHI",
     "court": "Delhi High Court", "seat": "New Delhi",
     "style": "HIGH COURT OF DELHI caption, '$~' reportability codes, "
              "'Reserved on / Pronounced on / Uploaded on' date trio",
     "supporting": [("reserved_pronounced", 1.0), ("pronounced_on", 0.8), ("cnr_field", 0.6)],
     "extras": [], "strategy": "reserved_judgment"},
    {"key": "CALCUTTA", "id": "CALCUTTA-HC", "pattern": r"HIGH\s+COURT\s+(?:AT|OF)\s+CALCUTTA|Calcutta\s+High\s+Court",
     "court": "Calcutta High Court", "seat": "Principal Seat, Kolkata",
     "style": "Cause-list head ('CT. NO. 07', '(Vacation Bench)', '(Allowed)'), "
              "'In The High Court at Calcutta', 'Between:', '-Vs-', circuit benches",
     "supporting": [("calcutta_between", 2.0), ("court_no_line", 0.8)], "extras": ["KEY-EXTRA-CALCUTTA"],
     "strategy": "order_sheet"},
    {"key": "GAUHATI", "id": "GAUHATI-HC", "pattern": r"GAUHATI\s+HIGH\s+COURT",
     "court": "Gauhati High Court", "seat": "Guwahati (with benches at Kohima, Aizawl, Itanagar)",
     "style": "THE GAUHATI HIGH COURT + '(HIGH COURT OF ASSAM, NAGALAND, MIZORAM AND ARUNACHAL PRADESH)', "
              "'Page No.# n/m', 'GAHC…' registry code, 'Case No. : <type>/<n>/<year>', ALL-CAPS parties",
     "supporting": [("gauhati_case_no", 2.0), ("registry_code", 1.2), ("submitted_brief_sections", 0.3)],
     "extras": ["KEY-EXTRA-GAUHATI"], "strategy": "numbered_paras"},
    {"key": "GUJARAT", "id": "GUJARAT-HC", "pattern": r"HIGH\s+COURT\s+OF\s+GUJARAT",
     "court": "Gujarat High Court", "seat": "Ahmedabad",
     "style": "'IN THE HIGH COURT OF GUJARAT AT AHMEDABAD', 'R/CR.MA/<n>/<year>', "
              "'ORDER DATED: dd/mm/yyyy', '(GJHC…)' registry code",
     "supporting": [("registry_code", 1.2), ("cnr_field", 0.6), ("appellate_jurisdiction", 0.5)],
     "extras": [], "strategy": "order_sheet"},
    {"key": "ORISSA", "id": "ORISSA-HC", "pattern": r"HIGH\s+COURT\s+OF\s+ORISSA|HIGH\s+COURT\s+OF\s+ODISHA",
     "court": "Orissa High Court", "seat": "Cuttack",
     "style": "'Page 1 of n.' head, 'ABLAPL No.<n> of <year>', 'CNR No. ODHC…', "
              "'..... Petitioner', 'Represented by Adv. -'",
     "supporting": [("orissa_adv", 2.5), ("cnr_field", 1.0)], "extras": ["KEY-EXTRA-ORISSA"],
     "strategy": "order_sheet"},
    {"key": "ALLAHABAD", "id": "ALLAHABAD-HC", "pattern": r"HIGH\s+COURT\s+OF\s+JUDICATURE\s+AT\s+ALLAHABAD",
     "court": "Allahabad High Court", "seat": "Allahabad / Lucknow Bench",
     "style": "'Court No. - n', 'Case :- <type> No. - <n> of <year>', 'Applicant :-', 'Opposite Party :-', "
              "'Counsel for … :-', 'Neutral Citation No. - YYYY:AHC…', 'Order Date :-'",
     "supporting": [("allahabad_case_line", 3.0), ("court_no_line", 0.8), ("cnr_field", 0.5)],
     "extras": ["KEY-EXTRA-ALLAHABAD"], "strategy": "headed_facts"},
    {"key": "TELANGANA", "id": "TELANGANA-HC", "pattern": r"HIGH[,\s]*COURT\s+FOR\s+THE\s+STATE\s+OF\s+TELANGANA",
     "court": "Telangana High Court", "seat": "Hyderabad",
     "style": "'IN THE HIGH COURT FOR THE STATE OF TELANGANA AT HYDERABAD', "
              "'(Special Original Jurisdiction)', 'TUESDAY, THE SEVENTH DAY OF APRIL TWO THOUSAND AND TWENTY SIX', "
              "'PRESENT / THE HONOURABLE SRI JUSTICE …'",
     "supporting": [("telangana_soj", 1.5), ("dated_this_the", 1.0), ("registry_code", 1.0)],
     "extras": ["KEY-EXTRA-TELANGANA"], "strategy": "reserved_judgment"},
    {"key": "ANDHRA", "id": "ANDHRA-HC", "pattern": r"HIGH\s+COURT\s+OF\s+ANDHRA\s+PRADESH",
     "court": "Andhra Pradesh High Court", "seat": "Amaravati",
     "style": "'APHC…' registry code, '(Special Original Jurisdiction)', 'AT AMARAVATI', "
              "'THE HONOURABLE SRI JUSTICE …'",
     "supporting": [("telangana_soj", 1.5), ("registry_code", 1.2), ("dated_this_the", 0.8)],
     "extras": ["KEY-EXTRA-TELANGANA"], "strategy": "reserved_judgment"},
    {"key": "RAJASTHAN", "id": "RAJASTHAN-HC", "pattern": r"HIGH\s+COURT\s+OF\s+JUDICATURE\s+FOR\s+RAJASTHAN",
     "court": "Rajasthan High Court", "seat": "Jodhpur / Jaipur Bench",
     "style": "'[YYYY:RJ-JP:n]' bracketed neutral citation, 'BENCH AT JAIPUR', "
              "'S.B. Criminal Miscellaneous Bail Application No.', 'CNR: RJHC… | URN: …'",
     "supporting": [("cnr_field", 1.2), ("neutral_cg", 0.5)], "extras": [], "strategy": "coram_order"},
    {"key": "KARNATAKA", "id": "KARNATAKA-HC", "pattern": r"HIGH\s+COURT\s+OF\s+KARNATAKA",
     "court": "Karnataka High Court", "seat": "Bengaluru",
     "style": "'- 1 -' head, 'WP No. … C/W WP No. …', 'IN THE HIGH COURT OF KARNATAKA AT BENGALURU', "
              "'DATED THIS THE 14TH DAY OF OCTOBER, 2026', 'PRESENT' + 'THE HON'BLE MR. JUSTICE …'",
     "supporting": [("dated_this_the", 2.0), ("present_word", 0.8)], "extras": ["KEY-EXTRA-KARNATAKA"],
     "strategy": "reserved_judgment"},
    {"key": "JK", "id": "JK-LADAKH-HC", "pattern": r"HIGH\s+COURT\s+OF\s+JAMMU\s*(?:&|AND)\s*KASHMIR",
     "court": "High Court of Jammu & Kashmir and Ladakh", "seat": "Jammu / Srinagar",
     "style": "'HIGH COURT OF JAMMU & KASHMIR AND LADAKH AT JAMMU', 'Uploaded on:', "
              "'Through :- <counsel>', '...Petitioner(s)', 'v/s'",
     "supporting": [("jk_through", 2.0)], "extras": ["KEY-EXTRA-JK"], "strategy": "coram_order"},
    {"key": "MEGHALAYA", "id": "MEGHALAYA-HC", "pattern": r"HIGH\s+COURT\s+OF\s+MEGHALAYA",
     "court": "Meghalaya High Court", "seat": "Shillong",
     "style": "cause-list head ('Serial No.', 'Regular List' / 'Supp. List'), "
              "'HIGH COURT OF MEGHALAYA AT SHILLONG', 'Date of Decision:'",
     "supporting": [("meghalaya_serial", 1.5)], "extras": ["KEY-EXTRA-MEGHALAYA"], "strategy": "coram_order"},
    {"key": "HIMACHAL", "id": "HIMACHAL-HC", "pattern": r"HIGH\s+COURT\s+OF\s+HIMACHAL\s+PRADESH",
     "court": "Himachal Pradesh High Court", "seat": "Shimla",
     "style": "'( 2026:HHC:40909 )' bracketed citation, 'Reserved on:' + 'Date of decision:', "
              "'Date of uploading on website:'",
     "supporting": [("reserved_pronounced", 1.2), ("pronounced_on", 0.8)], "extras": [], "strategy": "reserved_judgment"},
    {"key": "JHARKHAND", "id": "JHARKHAND-HC", "pattern": r"HIGH\s+COURT\s+OF\s+JHARKHAND",
     "court": "Jharkhand High Court", "seat": "Ranchi",
     "style": "'2026:JHHC:31060-DB' neutral citation line, 'IN THE HIGH COURT OF JHARKHAND AT RANCHI', "
              "'A. B. A. No.', '--- Opposite Party'",
     "supporting": [("neutral_cg", 1.0), ("cnr_field", 0.5)], "extras": [], "strategy": "coram_order"},
    {"key": "KERALA", "id": "KERALA-HC", "pattern": r"HIGH\s+COURT\s+OF\s+KERALA",
     "court": "Kerala High Court", "seat": "Ernakulam",
     "style": "'OP(C) NO. …', 'PRESENT' + 'THE HONOURABLE MR.JUSTICE …', "
              "dual-era date ('18TH DAY OF NOVEMBER 2022 / 27TH KARTHIKA, 1944')",
     "supporting": [("present_word", 1.0)], "extras": ["KEY-EXTRA-KARNATAKA"], "strategy": "reserved_judgment"},
    {"key": "TRIPURA", "id": "TRIPURA-HC", "pattern": r"HIGH\s+COURT\s+OF\s+TRIPURA",
     "court": "Tripura High Court", "seat": "Agartala",
     "style": "'TRHC…' registry code, '2026:THC:767' neutral citation, 'HIGH COURT OF TRIPURA AGARTALA', "
              "'… APPELLANT-OPPOSITE PARTY(S)', 'VERSUS'",
     "supporting": [("registry_code", 1.2), ("cnr_field", 0.5)], "extras": [], "strategy": "coram_order"},
    {"key": "UTTARAKHAND", "id": "UTTARAKHAND-HC", "pattern": r"HIGH\s+COURT\s+OF\s+UTTARAKHAND",
     "court": "Uttarakhand High Court", "seat": "Nainital",
     "style": "'UKHC…' registry code, 'Reserved on' + 'Delivered on', 'HIGH COURT OF UTTARAKHAND AT NAINITAL'",
     "supporting": [("registry_code", 1.0), ("reserved_pronounced", 1.0)], "extras": [], "strategy": "reserved_judgment"},
    {"key": "MP", "id": "MADHYA-PRADESH-HC", "pattern": r"HIGH\s+COURT\s+OF\s+MADHYA\s+PRADESH",
     "court": "Madhya Pradesh High Court", "seat": "Jabalpur / Indore / Gwalior",
     "style": "'HIGH COURT OF MADHYA PRADESH' benches, 'MCRC' / 'WP' prefixes, 'Justice …' coram",
     "supporting": [("cnr_field", 0.5)], "extras": [], "strategy": "coram_order"},
    {"key": "MADRAS-INRE", "id": "MADRAS-DAILY-ORDER", "pattern": r"(?:Madras\s+High\s+Court|HIGH\s+COURT\s+OF\s+MADRAS)",
     "court": "Madras High Court", "seat": "Principal Seat, Chennai",
     "style": "Daily cause-list order: 'Court No. n' / 'Sl. no. n' head, 'C.R.M. (M) <n> OF <year>', "
              "'In Re : An application for bail under Section 483 …', '(Allowed)'",
     "supporting": [("in_re_bail", 2.5), ("court_no_line", 0.8)], "extras": ["KEY-EXTRA-MADRAS-INRE"],
     "strategy": "order_sheet"},
]

for _entry in COURT_REGISTRY:
    _signal_id = "court_" + _entry["key"].lower().replace("-", "_")
    SIGNALS[_signal_id] = {
        "pattern": _entry["pattern"], "scope": "header", "weight": 3.0,
        "label": _entry["court"] + " caption",
    }
    PROFILES.append({
        "id": _entry["id"],
        "label": f"{_entry['court']} — {_entry['seat']}",
        "court": _entry["court"],
        "seat": _entry["seat"],
        "drafting_style": _entry["style"],
        "required": [_signal_id],
        "supporting": _entry["supporting"] + [("layout:serif", 0.3)],
        "negative": [],
        "min_score": 0.45,
        "key_set": ["KEY-HC-COMMON"] + _entry["extras"],
        "facts_strategy": _entry["strategy"],
    })

# ── Court naming for format-driven documents ───────────────────────────────
# Brief cards and cause-list orders carry a *format* but the court name lives
# only in the caption text (or in the case-number prefix).  This map turns that
# caption text into court + seat so the Case row is still attributed correctly.
COURT_NAME_MAP: List[Dict[str, str]] = [
    {"pattern": r"SUPREME\s+COURT\s+OF\s+INDIA", "court": "Supreme Court of India", "seat": "New Delhi"},
    {"pattern": r"HIGH\s+COURT\s+OF\s+DELHI", "court": "Delhi High Court", "seat": "New Delhi"},
    {"pattern": r"HIGH[,\s]*COURT\s+(?:OF\s+JUDICATURE\s+)?AT\s+ALLAHABAD|ALLAHABAD\s+HIGH\s+COURT",
     "court": "Allahabad High Court", "seat": "Allahabad / Lucknow Bench"},
    {"pattern": r"HIGH\s+COURT\s+OF\s+JUDICATURE\s+AT\s+BOMBAY|HIGH\s+COURT\s+OF\s+BOMBAY",
     "court": "Bombay High Court", "seat": "Mumbai / benches at Nagpur, Aurangabad, Goa"},
    {"pattern": r"HIGH\s+COURT\s+OF\s+GUJARAT", "court": "Gujarat High Court", "seat": "Ahmedabad"},
    {"pattern": r"HIGH\s+COURT\s+OF\s+KERALA", "court": "Kerala High Court", "seat": "Ernakulam"},
    {"pattern": r"HIGH\s+COURT\s+OF\s+KARNATAKA", "court": "Karnataka High Court", "seat": "Bengaluru"},
    {"pattern": r"HIGH\s+COURT\s+OF\s+MADRAS|MADRAS\s+HIGH\s+COURT", "court": "Madras High Court",
     "seat": "Principal Seat, Chennai"},
    {"pattern": r"MADURAI\s+BENCH", "court": "Madras High Court", "seat": "Madurai Bench"},
    {"pattern": r"(?:HIGH\s+COURT\s+(?:AT|OF)\s+CALCUTTA)|CALCUTTA\s+HIGH\s+COURT", "court": "Calcutta High Court",
     "seat": "Kolkata"},
    {"pattern": r"HIGH\s+COURT\s+OF\s+(?:JUDICATURE\s+FOR\s+)?RAJASTHAN", "court": "Rajasthan High Court",
     "seat": "Jodhpur / Jaipur Bench"},
    {"pattern": r"HIGH\s+COURT\s+OF\s+ORISSA|HIGH\s+COURT\s+OF\s+ODISHA", "court": "Orissa High Court", "seat": "Cuttack"},
    {"pattern": r"HIGH\s+COURT\s+OF\s+MADHYA\s+PRADESH", "court": "Madhya Pradesh High Court", "seat": "Jabalpur"},
    {"pattern": r"HIGH\s+COURT\s+OF\s+MEGHALAYA", "court": "Meghalaya High Court", "seat": "Shillong"},
    {"pattern": r"HIGH\s+COURT\s+OF\s+TRIPURA", "court": "Tripura High Court", "seat": "Agartala"},
    {"pattern": r"NATIONAL\s+COMPANY\s+LAW", "court": "National Company Law Tribunal", "seat": ""},
    {"pattern": r"GAUHATI\s+HIGH\s+COURT", "court": "Gauhati High Court", "seat": "Guwahati"},
    # case-number prefixes are a reliable fallback for cause-list orders
    {"pattern": r"\b(?:WPA|WP\d{2,5}|CRM\s*\(A\)|CRR|CRAN|CUSTA)\b", "court": "Calcutta High Court", "seat": "Kolkata"},
    {"pattern": r"\bC\.R\.M\.?\s*\(?M", "court": "Madras High Court", "seat": "Principal Seat, Chennai"},
    {"pattern": r"\bAHC[\-A-Z]*\b", "court": "Allahabad High Court", "seat": "Allahabad / Lucknow Bench"},
    {"pattern": r"\bAPHC\d+", "court": "Andhra Pradesh High Court", "seat": "Amaravati"},
    {"pattern": r"\bTRHC\d+", "court": "Tripura High Court", "seat": "Agartala"},
    {"pattern": r"\bGAHC\d+", "court": "Gauhati High Court", "seat": "Guwahati"},
    {"pattern": r"\bUKHC\d+", "court": "Uttarakhand High Court", "seat": "Nainital"},
    {"pattern": r"\bBHC\d+", "court": "Bombay High Court", "seat": "Mumbai"},
]


# Registry-code prefix -> court.  Office-notes sheets and short order slips
# frequently print only "UKHC010091362026" / "APHC010456352026" and never the
# court name in words, so the code is the only attribution available.
REGISTRY_COURT: Dict[str, Tuple[str, str]] = {
    "APHC": ("Andhra Pradesh High Court", "Amaravati"),
    "UKHC": ("Uttarakhand High Court", "Nainital"),
    "UHC": ("Uttarakhand High Court", "Nainital"),
    "TRHC": ("Tripura High Court", "Agartala"),
    "GAHC": ("Gauhati High Court", "Guwahati"),
    "GJHC": ("Gujarat High Court", "Ahmedabad"),
    "ODHC": ("Orissa High Court", "Cuttack"),
    "RJHC": ("Rajasthan High Court", "Jodhpur / Jaipur Bench"),
    "TSHC": ("Telangana High Court", "Hyderabad"),
    "HCAP": ("Andhra Pradesh High Court", "Amaravati"),
    "JHHC": ("Jharkhand High Court", "Ranchi"),
    "KHC": ("Karnataka High Court", "Bengaluru"),
    "MPHC": ("Madhya Pradesh High Court", "Jabalpur"),
    "CGHC": ("Chhattisgarh High Court", "Bilaspur"),
    "PHHC": ("Punjab & Haryana High Court", "Chandigarh"),
    "BHC": ("Bombay High Court", "Mumbai"),
    "DLHC": ("Delhi High Court", "New Delhi"),
    "MHHC": ("Madras High Court", "Principal Seat, Chennai"),
    "PTHC": ("Patna High Court", "Patna"),
    "HHC": ("Himachal Pradesh High Court", "Shimla"),
    "MEGHC": ("Meghalaya High Court", "Shillong"),
}


def _court_from_caption(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Best-effort court + seat for documents that carry a format, not a caption."""
    head = text[:4000]
    for entry in COURT_NAME_MAP:
        if re.search(entry["pattern"], head, re.IGNORECASE | re.MULTILINE):
            return entry["court"], entry["seat"] or None
    code = re.search(r"\b([A-Z]{2,5})HC\d{10,}\b", head)
    if code:
        found = REGISTRY_COURT.get(code.group(1) + "HC") or REGISTRY_COURT.get(code.group(1))
        if found:
            return found[0], found[1] or None
    return None, None


# ── Format-based profile: one-page case-brief cards (headnote/ratio/operative)
PROFILES.insert(0, {
    "id": "BRIEF-CARD",
    "label": "Case-brief card — headnote / ratio / operative headings",
    "court": "",   # derived from the caption text; brief cards print any court
    "seat": "",
    "drafting_style": "One-page brief: '<COURT> / APPELLATE JURISDICTION / CASE NO: … (YEAR: …) / CORAM: <bench>, "
                      "comma-separated / ... Appellant(s) / Petitioner(s) / Versus / Acts Referred / "
                      "JUDICIAL HEADNOTE & SUMMARY / RATIO DECIDENDI / JUDGMENT & REASONING / OPERATIVE ORDER'",
    "required": ["brief_card"],
    "supporting": [("appellate_jurisdiction", 1.2), ("submitted_brief_sections", 1.5), ("cnr_field", 0.4)],
    "negative": [],
    "min_score": 0.5,
    "key_set": ["KEY-HC-COMMON", "KEY-EXTRA-BRIEF-CARD"],
    "facts_strategy": "headed_facts",
    "derive_court_from_caption": True,
})

# ── Format-based profile: certified copy of a daily cause-list order ────────
# Calcutta writes 'Ct. No. 7 / (Vacation Bench) / (Allowed) / WPA 24114 of 2026'
# and Madras writes 'Court No.8 / S/L 34 / CRM (M) 2834 of 2026 / In Re : An
# application for bail …' — neither repeats the court name in the header.
PROFILES.insert(1, {
    "id": "DAILY-CAUSE-ORDER",
    "label": "Certified daily order sheet — cause-list head + 'In Re :' criminal motion",
    "court": "",   # cause-list heads omit the court; set only when the caption is unambiguous
    "seat": "",
    "drafting_style": "Certified copy head ('Court No. 7' / 'Sl. No. 07' / '(Vacation Bench)' / '(Allowed)'), "
                      "case number as 'WPA 24114 of 2026' or 'C.R.M. (M) 2463 OF 2026', body opening "
                      "'In Re : An application for bail under Section 483 …'",
    "required": ["in_re_bail"],
    "supporting": [("court_no_line", 1.0), ("registry_code", 0.5)],
    "negative": [],
    "min_score": 0.5,
    "key_set": ["KEY-HC-COMMON", "KEY-EXTRA-MADRAS-INRE"],
    "facts_strategy": "order_sheet",
    "derive_court_from_caption": True,
})

# ── Format-based profile: Calcutta cause-list order ('Between:' / '-Vs-') ───
PROFILES.insert(1, {
    "id": "CALCUTTA-CAUSELIST",
    "label": "Calcutta HC cause-list order — 'Ct. No.' head, 'Between:' / '-Vs-' caption",
    "court": "Calcutta High Court",
    "seat": "Kolkata",
    "drafting_style": "Cause-list head ('22.10.2026', '274', 'Ct.-7', '(NMD/D.Hira)'), case number "
                      "'WPA 24114 of 2026', caption joined by '-Vs-' / 'Between:'",
    "required": ["calcutta_between"],
    "supporting": [("court_no_line", 1.0)],
    "negative": [],
    "min_score": 0.5,
    "key_set": ["KEY-HC-COMMON", "KEY-EXTRA-CALCUTTA"],
    "facts_strategy": "order_sheet",
    "derive_court_from_caption": True,
})

# ── Format-based profile: Allahabad/UP 'Case :-' docket (no court caption) ──
PROFILES.insert(1, {
    "id": "ALLAHABAD-CASELINE",
    "label": "Allahabad HC docket — 'Case :-' / 'Applicant :-' / 'Opposite Party :-' (court name omitted)",
    "court": "Allahabad High Court",
    "seat": "Allahabad / Lucknow Bench",
    "drafting_style": "Pure docket: 'Court No. - 26', 'Case :- APPLICATION U/S 482 No. - …', "
                      "'Applicant :-', 'Opposite Party :-', 'Counsel for … :-', 'Hon'ble … J.', "
                      "'Order Date :-' — the court name itself is not printed",
    "required": ["allahabad_case_line"],
    "supporting": [("court_no_line", 0.8), ("cnr_field", 0.4)],
    "negative": [("court_allahabad", 0.5)],
    "min_score": 0.5,
    "key_set": ["KEY-HC-COMMON", "KEY-EXTRA-ALLAHABAD"],
    "facts_strategy": "headed_facts",
})

# ── Format-based profile: Bombay neutral-citation slip ('2026:BHC-GOA:…') ──
PROFILES.insert(1, {
    "id": "BOMBAY-NEUTRAL-CITATION",
    "label": "Bombay HC neutral-citation slip — 'YYYY:BHC-<BENCH>:<n>' + 'WP <n>-<year>'",
    "court": "Bombay High Court",
    "seat": "Mumbai / Goa, Nagpur, Aurangabad benches",
    "drafting_style": "Running header 'WP 207-2026 / Page 1 of 10 / 19th October, 2026', neutral citation "
                      "'2026:BHC-GOA:2108' printed at the top of every page",
    "required": ["bombay_neutral_citation"],
    "supporting": [("court_bombay", 1.0), ("bombay_doc_header", 0.5)],
    "negative": [],
    "min_score": 0.45,
    "key_set": ["KEY-HC-COMMON", "KEY-EXTRA-BOMBAY"],
    "facts_strategy": "coram_order",
})

# ── Format-based profile: Madras review-order slip ('R.V.W. … of …') ────────
PROFILES.insert(1, {
    "id": "MADRAS-REVIEW-SLIP",
    "label": "Madras HC review slip — 'R.V.W. <n> of <year>' with 'CAN' application",
    "court": "Madras High Court",
    "seat": "Principal Seat, Chennai",
    "drafting_style": "Cause-list slip 'Court No. 13 / Item No. 1. / R.V.W. 369 of 2024 / With / CAN 1 of 2024 / "
                      "In the matter of …'",
    "required": ["madras_rvw"],
    "supporting": [("court_no_line", 0.8), ("court_madras_inre", 0.5)],
    "negative": [],
    "min_score": 0.45,
    "key_set": ["KEY-HC-COMMON", "KEY-EXTRA-MADRAS-INRE"],
    "facts_strategy": "order_sheet",
})

# ── Format-based profile: registry office-notes sheet (code, no caption) ───
PROFILES.insert(1, {
    "id": "OFFICE-NOTES",
    "label": "Registry office-notes sheet — 'SL. No. / Date or directions / COURT'S OR JUDGE'S ORDERS'",
    "court": "",
    "seat": "",
    "drafting_style": "Columnar registry sheet ('SL. No.', 'Date or directions and COURT'S OR JUDGE'S ORDERS', "
                      "'Registrar's order with Signatures'), case number 'CRLR/405/2026', parties marked "
                      "'--Revisionist' / '--Respondents', no printed court caption",
    "required": ["office_notes"],
    "supporting": [("registry_code", 1.5), ("court_no_line", 0.5)],
    "negative": [],
    "min_score": 0.45,
    "key_set": ["KEY-HC-COMMON"],
    "facts_strategy": "order_sheet",
    "derive_court_from_caption": True,
})

# ── Format-based profile: digest / law-report reprint ──────────────────────
PROFILES.insert(1, {
    "id": "LAW-REPORT-REPRINT",
    "label": "Digest/law-report reprint — 'Equivalent citations:' + '<party> vs <party> on <date>'",
    "court": "",
    "seat": "",
    "drafting_style": "Reprinted report text: '<appellant> vs <respondent> on 24 February 1800', "
                      "'Equivalent citations: (1897)7MLJ227', 'JUDGMENT' heading, no live court caption",
    "required": ["law_report_reprint"],
    "supporting": [("brief_card", 0.8)],
    "negative": [],
    "min_score": 0.45,
    "key_set": ["KEY-HC-COMMON"],
    "facts_strategy": "headed_facts",
    "derive_court_from_caption": True,
})

# ── Format-based profile: Madras short order slip ('WMP … in W.P. …') ───────
PROFILES.insert(1, {
    "id": "MADRAS-SHORT-ORDER",
    "label": "Madras HC short order slip — 'WMP. No. … in W.P. No. …', 'Ordered.'",
    "court": "Madras High Court",
    "seat": "Principal Seat, Chennai",
    "drafting_style": "One-page slip: 'WMP. No.48807 of 2026 in W.P. No.43496 of 2026', judge name as "
                      "'V. LAKSHMINARAYANAN,J.', disposition word 'Ordered.', date '23.10.2026'",
    "required": ["madras_short_order"],
    "supporting": [("court_madras_inre", 1.0)],
    "negative": [],
    "min_score": 0.45,
    "key_set": ["KEY-HC-COMMON", "KEY-EXTRA-MADRAS-INRE"],
    "facts_strategy": "order_sheet",
})

# ── Non-judgment guard: keep project/notes PDFs out of the case corpus ──────
PROFILES.insert(0, {
    "id": "NON-JUDGMENT",
    "label": "Not a court document (project notes / specification)",
    "court": "",
    "seat": "",
    "drafting_style": "No judicial caption, no case number, no coram — e.g. a project brief or design document "
                      "that was filed into the case store by mistake",
    "required": ["not_a_judgment"],
    "supporting": [],
    "negative": [("in_re_bail", 1.0), ("allahabad_case_line", 1.0), ("brief_card", 1.0)],
    "min_score": 0.5,
    "key_set": ["KEY-GENERIC"],
    "facts_strategy": "none",
})


def _merge_key_sets(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge two key sets without losing anchors.

    Same key id in the same category -> anchors are unioned (order preserved) and
    the confidence becomes the maximum of the two.  This is what lets a court
    profile compose a shared key set with a small registry-specific extras set.
    """
    merged: Dict[str, Any] = {
        category: {k: {**v, "anchors": list(v.get("anchors", []))} for k, v in keys.items()}
        for category, keys in base.items()
    }
    for category, keys in extra.items():
        target = merged.setdefault(category, {})
        for key_id, spec in keys.items():
            if key_id in target:
                existing = target[key_id]
                for anchor in spec["anchors"]:
                    if anchor not in existing["anchors"]:
                        existing["anchors"].append(anchor)
                existing["confidence"] = max(existing["confidence"], spec["confidence"])
                if spec.get("note") and not existing.get("note"):
                    existing["note"] = spec["note"]
            else:
                target[key_id] = {**spec, "anchors": list(spec.get("anchors", []))}
    return merged


# ---------------------------------------------------------------------------
# 4. Layout fingerprinting and text recovery
# ---------------------------------------------------------------------------

@dataclass
class LayoutFingerprint:
    page_count: int = 0
    page_width: float = 0.0
    page_height: float = 0.0
    geometry_class: str = "unknown"
    char_count: int = 0
    chars_per_page: float = 0.0
    image_count: int = 0
    dominant_font: str = ""
    dominant_font_size: float = 0.0
    distinct_fonts: int = 0
    mono_ratio: float = 0.0
    serif_ratio: float = 0.0
    clipped_block_ratio: float = 0.0
    repaired_page_ratio: float = 0.0
    columnar_page_ratio: float = 0.0
    short_line_ratio: float = 0.0
    watermark_url: Optional[str] = None
    page_clock_style: Optional[str] = None
    repeated_header_lines: List[str] = field(default_factory=list)
    has_text_layer: bool = True
    needs_geometric_repair: bool = False
    layout_signals: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_SERIF_TOKENS = ("times", "serif", "georgia", "garamond", "book antiqua", "cambria", "thorndale")
_MONO_TOKENS = ("courier", "mono", "consolas", "menlo", "lucida console")


def _line_rows(words: List[Tuple[float, float, float, float, str]], y_tol: float = 3.0):
    """Group extracted words into visual lines by baseline proximity."""
    rows: List[List[Tuple[float, float, float, float, str]]] = []
    for w in sorted(words, key=lambda w: (round(w[1], 1), w[0])):
        if rows and abs(w[1] - rows[-1][-1][1]) <= y_tol:
            rows[-1].append(w)
        else:
            rows.append([w])
    return [sorted(r, key=lambda w: w[0]) for r in rows]


def _max_overlap_join(left: str, right: str) -> Tuple[str, bool]:
    """Join two fragments overlapping in x by their maximum string overlap."""
    if not left:
        return right, True
    if not right:
        return left, True
    best = 0
    for k in range(min(len(left), len(right)), 0, -1):
        if left[-k:].lower() == right[:k].lower():
            best = k
            break
    if best:
        return left + right[best:], True
    return f"{left} {right}", False


def _repair_doubled_draw(page) -> str:
    """
    Rebuild lines from pages whose text is drawn as overlapping/clipped runs.

    Punjab & Haryana PDFs in the corpus render every line twice with a 1-2pt
    offset and split words across clips, so plain extraction yields
    ``IN T + THE + HIGH ... + AN + ND``. Sorting words by (y, x) and merging
    fragments by *bounding-box overlap* (duplicate draw) or by *character
    overlap* (split word) restores ``IN THE HIGH COURT ... AND`` without
    inventing characters that no draw contained.

    Decision table per neighbouring fragment pair on the same visual line:
      * x-overlap >= 35% of the narrower box -> same glyphs drawn twice -> merge
        by longest common suffix/prefix (never duplicate characters)
      * gap <= 1.2pt and no space glyph -> the word was split by the clip ->
        merge without a space
      * otherwise -> keep the literal space
    """
    words = [(w[0], w[1], w[2], w[3], w[4]) for w in page.get_text("words")]
    out: List[str] = []
    for row in _line_rows(words):
        line = ""
        prev = None
        for (x0, _y0, x1, _y1, text) in row:
            if not text:
                continue
            if not line or prev is None:
                line = text
                prev = (x0, x1)
                continue
            p_x0, p_x1 = prev
            narrower = max(min(x1 - x0, p_x1 - p_x0), 1e-6)
            x_overlap = min(x1, p_x1) - max(x0, p_x0)
            gap = x0 - p_x1
            if x_overlap / narrower >= 0.35:
                line, _ = _max_overlap_join(line, text)
            elif gap <= 1.2 and not line.endswith(" "):
                joined, overlapped = _max_overlap_join(line, text)
                line = joined if overlapped else (line + text)
            else:
                line = f"{line} {text}"
            prev = (min(p_x0, x0), max(p_x1, x1))
        if line.strip():
            out.append(re.sub(r" +", " ", line.strip()))
    return "\n".join(out)


def _text_quality_score(text: str) -> float:
    """Average printable characters per non-empty line — a clipping detector."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return 0.0
    return sum(len(l) for l in lines) / len(lines)


def _has_double_drawn_runs(words: Sequence[Sequence[Any]]) -> bool:
    """
    Detect a genuinely double-drawn text layer from word geometry.

    A normal single-column page may contain many *narrow* blocks (centred
    captions, party names, page clocks) without being broken.  The reliable
    signal is instead a run of neighbouring words on the same baseline whose
    bounding boxes overlap substantially: the same glyphs were painted twice
    at a small offset, or a word was split across two clipping paths.

    The gate is deliberately conservative: isolated overlaps (signatures,
    stamps, table rules) are not enough.  We require several overlapping pairs
    across at least two visual rows, with a meaningful share of near-coincident
    or character-overlapping fragments.
    """
    if len(words) < 12:
        return False
    overlap_pairs = 0
    overlap_rows = 0
    strong_pairs = 0
    for row in _line_rows(list(words)):
        row_pairs = 0
        for left, right in zip(row, row[1:]):
            narrower = max(min(left[2] - left[0], right[2] - right[0]), 1e-6)
            x_overlap = min(left[2], right[2]) - max(left[0], right[0])
            ratio = x_overlap / narrower
            if ratio < 0.35:
                continue
            row_pairs += 1
            overlap_pairs += 1
            ltext, rtext = left[4].lower(), right[4].lower()
            if ratio >= 0.8 or ltext == rtext or _max_overlap_join(left[4], right[4])[1]:
                strong_pairs += 1
        if row_pairs:
            overlap_rows += 1
    return (
        overlap_pairs >= 6
        and overlap_rows >= 2
        and strong_pairs >= 3
        and overlap_pairs / max(len(words), 1) >= 0.02
    )


def _looks_like_sharded_raw(raw: str) -> bool:
    """
    True when a clipped-looking page is actually a shard/blank-line text layer,
    not a clean page that merely contains a table or many narrow caption blocks.

    Double-drawn P&H/Bombay exports fragment one visual line into many short
    draws separated by blank lines.  Tables also create narrow blocks, but they
    do not produce the same blank-line + short-fragment signature.
    """
    lines = raw.split("\n")
    if not lines:
        return False
    nonempty = [line for line in lines if line.strip()]
    if not nonempty:
        return False
    blank_ratio = sum(1 for line in lines if not line.strip()) / len(lines)
    short_ratio = sum(1 for line in nonempty if len(line.strip()) < 25) / len(nonempty)
    return blank_ratio >= 0.30 and short_ratio >= 0.50 and _text_quality_score(raw) <= 24.0


def _choose_page_text(page) -> Tuple[str, bool]:
    """
    Pick verbatim text or the geometrically repaired text.

    Repair is *suspicion-gated*: it is only attempted when a page has severe
    clipping (``clipped / len(blocks) >= 0.25``) or genuine double-drawn
    overlapping runs.  Suspicion alone is not acceptance.  A double-drawn layer
    is kept when line continuity improves; a merely clipped-looking page must
    also look like a sharded text layer and show a large continuity gain
    (>= 1.4x).  Clean single-column judgments and table-heavy pages therefore
    remain verbatim instead of being re-flowed by the repairer.
    """
    raw = page.get_text()
    page_dict = page.get_text("dict")
    blocks = [b for b in page_dict["blocks"] if b["type"] == 0]
    if not blocks:
        return raw, False
    clipped = sum(1 for b in blocks if (b["bbox"][2] - b["bbox"][0]) < page.rect.width * 0.42)
    severe_clipping = (clipped / len(blocks)) >= 0.25
    double_drawn = _has_double_drawn_runs(page.get_text("words"))
    if not (severe_clipping or double_drawn or not raw.strip()):
        return raw, False

    repaired = _repair_doubled_draw(page)
    if not repaired.strip():
        return raw, False
    raw_score, rep_score = _text_quality_score(raw), _text_quality_score(repaired)
    keeps_content = len(repaired.strip()) >= 0.25 * len(raw.strip())
    if not keeps_content:
        return raw, False
    if not raw.strip():
        return repaired, True
    if double_drawn and rep_score >= max(raw_score * 1.05, raw_score + 1.0):
        return repaired, True
    if (severe_clipping and _looks_like_sharded_raw(raw)
            and rep_score >= max(raw_score * 1.4, raw_score + 8.0)):
        return repaired, True
    return raw, False


def _post_process_page_text(text: str, page) -> Tuple[str, bool]:
    """
    Apply the structural repairs that do not depend on the text layer being
    broken: collapse duplicated line shards, then rebuild genuine two-column
    pages column-by-column.
    """
    repaired = False
    deduped = _dedupe_lines(text)
    # only call it a repair when the line structure actually changed (trailing
    # whitespace churn must not flag every document as "repaired")
    if (len(deduped.split("\n")) != len(text.split("\n"))
            and len(deduped.strip()) >= 0.55 * len(text.strip())):
        text, repaired = deduped, True
    # only rebuild pages that are *genuinely* two-column: a single-column page
    # with a few narrow blocks (centred 'CORAM', page numbers) would otherwise be
    # re-ordered and lose its caption.
    columnar = _columnar_page_text(page) if _detect_columnar(page) else None
    if columnar and _text_quality_score(columnar) >= _text_quality_score(text):
        text, repaired = columnar, True
    return text, repaired


def _detect_columnar(page) -> bool:
    """True when the page has >=2 real text blocks sharing a baseline band but
    occupying disjoint x-ranges (a genuine newspaper-style column layout)."""
    blocks = [b for b in page.get_text("dict")["blocks"]
              if b["type"] == 0 and (b["bbox"][2] - b["bbox"][0]) > 80
              and (b["bbox"][3] - b["bbox"][1]) > 40]
    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            a, b = blocks[i]["bbox"], blocks[j]["bbox"]
            y_overlap = min(a[3], b[3]) - max(a[1], b[1])
            min_h = min(a[3] - a[1], b[3] - b[1])
            x_disjoint = a[2] <= b[0] + 2 or b[2] <= a[0] + 2
            if min_h > 0 and y_overlap > 0.5 * min_h and x_disjoint:
                return True
    return False


def _dedupe_lines(text: str) -> str:
    """
    Collapse the "shifted duplicate draw" shard chain into single lines.

    Some registry exports draw every line twice at a small x/y offset, so a
    geometry-splitting extractor emits a growing chain of shards::

        IN / IN THE / THE HIGH / HIGH COURT / COURT OF / OF JUDICATURE / AT BOMBAY

    Each line begins with the previous line's last word.  A run is merged only
    when it has at least four shards, or a shorter run has a multi-word
    suffix/prefix overlap; a two- or three-line prose coincidence is left alone.
    Nothing outside a genuine run is touched, so real content is not reordered
    or dropped.  Duplicate tail words ("… AT BOMBAY" then "BOMBAY") are absorbed.
    """
    lines = text.split("\n")
    out: List[str] = []
    i, total = 0, len(lines)

    while i < total:
        current = lines[i].strip()
        if not current:
            out.append("")
            i += 1
            continue

        chain = [current]
        j = i + 1
        while j < total:
            nxt = lines[j].strip()
            if not nxt:
                break
            last_word = chain[-1].split()[-1].strip(".,;:").lower()
            first_word = nxt.split()[0].strip(".,;:").lower()
            if first_word == last_word:
                chain.append(nxt)          # continuation of the same draw
                j += 1
                continue
            break

        if len(chain) >= 3:
            # A single repeated word across three ordinary prose lines is not a
            # shifted duplicate draw.  Accept either a longer shard chain (the
            # Bombay ``IN / IN THE / THE HIGH / HIGH COURT ...`` caption) or a
            # multi-word suffix/prefix overlap between neighbours.
            overlaps: List[int] = []
            for left, right in zip(chain, chain[1:]):
                lw = [w.strip(".,;:").lower() for w in left.split()]
                rw = [w.strip(".,;:").lower() for w in right.split()]
                k = 0
                while k < min(len(lw), len(rw)) and lw[-k - 1] == rw[k]:
                    k += 1
                overlaps.append(k)
            genuine_shard_chain = len(chain) >= 4 or max(overlaps, default=0) >= 2
            if genuine_shard_chain:
                merged = chain[0]
                for piece in chain[1:]:
                    words = piece.split()
                    merged = f"{merged} {' '.join(words[1:])}".strip()
                out.append(merged)
                i = j
            else:
                out.append(current)
                i += 1
        else:
            out.append(current)
            i += 1

    return "\n".join(out)


def _columnar_page_text(page) -> Optional[str]:
    """
    Rebuild a genuine two-column page (Patna-style judgments) by reading each
    column top-to-bottom instead of interleaving the two streams line by line.

    Returns None when the page does not look like a real two-column layout, so
    single-column pages are never touched.
    """
    blocks = [b for b in page.get_text("dict")["blocks"]
              if b["type"] == 0 and (b["bbox"][2] - b["bbox"][0]) > 80]
    if len(blocks) < 2:
        return None
    mid = page.rect.width / 2

    def column_of(block) -> str:
        x0, _y0, x1, _y1 = block["bbox"]
        if x1 <= mid + 6:
            return "L"
        if x0 >= mid - 6:
            return "R"
        return "W"      # spans the gutter (headings, full-width lines)

    left = [b for b in blocks if column_of(b) == "L"]
    right = [b for b in blocks if column_of(b) == "R"]
    wide = [b for b in blocks if column_of(b) == "W"]
    if len(left) < 2 or len(right) < 2:
        return None

    # both columns must actually run side by side over a meaningful vertical span
    left_span = max(b["bbox"][3] for b in left) - min(b["bbox"][1] for b in left)
    right_span = max(b["bbox"][3] for b in right) - min(b["bbox"][1] for b in right)
    if min(left_span, right_span) < page.rect.height * 0.15:
        return None

    def text_of(block) -> str:
        return "\n".join(
            " ".join(span["text"] for span in line["spans"]).strip()
            for line in block.get("lines", [])
        ).strip()

    parts: List[str] = []
    for block in sorted(wide, key=lambda b: b["bbox"][1]):
        body = text_of(block)
        if body:
            parts.append(body)
    for column in (left, right):
        for block in sorted(column, key=lambda b: b["bbox"][1]):
            body = text_of(block)
            if body:
                parts.append(body)
    rebuilt = "\n".join(parts).strip()
    return rebuilt if len(rebuilt) > 200 else None


def _repeated_edge_lines(pages: List[List[str]], edge: int = 2, min_share: float = 0.5) -> List[str]:
    counter: Counter = Counter()
    counted = 0
    for lines in pages:
        if not lines:
            continue
        counted += 1
        seen = set()
        for line in lines[:edge] + lines[-edge:]:
            s = line.strip()
            if 2 < len(s) < 120:
                seen.add(s)
        counter.update(seen)
    if not counted:
        return []
    return [line for line, n in counter.most_common() if n / counted >= min_share][:8]


def extract_pdf_text(path: str) -> Tuple[str, "LayoutFingerprint", Dict[str, Any]]:
    """
    Extract document text with layout awareness.

    Returns ``(text, fingerprint, page_texts)``.  ``page_texts`` is included so
    callers (the extraction service) can build first-page / last-page windows
    without reopening the file.

    The extractor is deliberately defensive: if PyMuPDF is unavailable it falls
    back to pdfplumber, and if the text layer is empty the fingerprint is flagged
    ``has_text_layer=False`` so ingestion can route the file to OCR.
    """
    fingerprint = LayoutFingerprint()
    page_texts: List[str] = []

    try:
        import pymupdf  # type: ignore
    except Exception:  # pragma: no cover - import guard
        pymupdf = None

    if pymupdf is not None:
        doc = pymupdf.open(path)
        fingerprint.page_count = doc.page_count
        rect = doc[0].rect
        fingerprint.page_width, fingerprint.page_height = float(rect.width), float(rect.height)

        fonts: Counter = Counter()
        sizes: Counter = Counter()
        clipped_blocks = 0
        total_blocks = 0
        columnar_pages = 0
        scanned_pages: List[List[str]] = []

        repaired_pages = 0
        for page in doc:
            text, was_repaired = _choose_page_text(page)
            text, post_repaired = _post_process_page_text(text, page)
            if was_repaired or post_repaired:
                repaired_pages += 1
            page_texts.append(text)

            if fingerprint.page_width == 0:
                fingerprint.page_width, fingerprint.page_height = float(page.rect.width), float(page.rect.height)

            page_dict = page.get_text("dict")
            for block in page_dict["blocks"]:
                if block["type"] == 1:
                    fingerprint.image_count += 1
                    continue
                total_blocks += 1
                if (block["bbox"][2] - block["bbox"][0]) < page.rect.width * 0.42:
                    clipped_blocks += 1
                for line in block.get("lines", []):
                    for span in line["spans"]:
                        fonts[span["font"]] += len(span["text"])
                        sizes[round(span["size"], 1)] += len(span["text"])

            if _detect_columnar(page):
                columnar_pages += 1
            scanned_pages.append([l for l in text.split("\n")])

        doc.close()

        total_font_chars = sum(fonts.values()) or 1
        mono_chars = sum(n for f, n in fonts.items() if any(t in f.lower() for t in _MONO_TOKENS))
        serif_chars = sum(n for f, n in fonts.items() if any(t in f.lower() for t in _SERIF_TOKENS))
        fingerprint.mono_ratio = round(mono_chars / total_font_chars, 3)
        fingerprint.serif_ratio = round(serif_chars / total_font_chars, 3)
        fingerprint.distinct_fonts = len(fonts)
        if fonts:
            fingerprint.dominant_font = fonts.most_common(1)[0][0]
        if sizes:
            fingerprint.dominant_font_size = sizes.most_common(1)[0][0]
        fingerprint.clipped_block_ratio = round(clipped_blocks / total_blocks, 3) if total_blocks else 0.0
        fingerprint.columnar_page_ratio = round(columnar_pages / max(fingerprint.page_count, 1), 3)
        fingerprint.repaired_page_ratio = round(repaired_pages / max(fingerprint.page_count, 1), 3)
        fingerprint.repeated_header_lines = _repeated_edge_lines(scanned_pages)
    else:  # pragma: no cover - pdfplumber fallback
        import pdfplumber

        with pdfplumber.open(path) as pdf:
            fingerprint.page_count = len(pdf.pages)
            for page in pdf.pages:
                page_texts.append((page.extract_text() or "").strip())

    text = "\n\n".join(page_texts)
    fingerprint.char_count = len(text)
    fingerprint.chars_per_page = round(len(text) / max(fingerprint.page_count, 1), 1)
    fingerprint.has_text_layer = fingerprint.chars_per_page >= 120

    # Geometry class
    w, h = fingerprint.page_width, fingerprint.page_height
    if abs(w - 595) < 12 and abs(h - 842) < 15:
        fingerprint.geometry_class = "A4"
    elif w >= 600 and h >= 950:
        fingerprint.geometry_class = "legal"
    elif fingerprint.page_count:
        fingerprint.geometry_class = "custom"

    wm = re.search(r"https?://(?:www\.)?[a-z0-9\.\-]+\.(?:gov\.in|nic\.in|judis)[^\s\"]*", text, re.I)
    if wm:
        fingerprint.watermark_url = wm.group(0)

    if re.search(r"(?m)^\s*Page\s*\d+\s+of\s+\d+\s*$", text):
        fingerprint.page_clock_style = "Page N of M"
    elif re.search(r"(?m)^\s*\d{1,3}/\d{1,3}\s*$", text):
        fingerprint.page_clock_style = "N/M"
    elif re.search(r"(?m)^\s*\d{1,3}\s*$", text):
        fingerprint.page_clock_style = "bare integer"

    lines = [l for l in text.split("\n") if l.strip()]
    if lines:
        fingerprint.short_line_ratio = round(
            sum(1 for l in lines if len(l.strip()) < 25) / len(lines), 3
        )

    fingerprint.needs_geometric_repair = fingerprint.repaired_page_ratio >= 0.3

    sigs: List[str] = []
    if fingerprint.mono_ratio >= 0.5:
        sigs.append("layout:mono_font")
    if fingerprint.serif_ratio >= 0.5:
        sigs.append("layout:serif")
    if fingerprint.geometry_class == "legal":
        sigs.append("layout:legal_page")
    if fingerprint.geometry_class == "A4":
        sigs.append("layout:a4_page")
    if not fingerprint.has_text_layer:
        sigs.append("layout:no_text_layer")
    if fingerprint.needs_geometric_repair:
        sigs.append("layout:clipped_blocks")
    if fingerprint.columnar_page_ratio > 0.3:
        sigs.append("layout:columnar")
    if fingerprint.watermark_url:
        sigs.append("layout:watermark")
    fingerprint.layout_signals = sigs

    return text, fingerprint, {"pages": page_texts}


# ---------------------------------------------------------------------------
# 5. Detection
# ---------------------------------------------------------------------------

@dataclass
class Detection:
    profile_id: str
    label: str
    court: str
    seat: str
    drafting_style: str
    confidence: float
    score: float
    runner_up: Optional[str]
    runner_up_score: float
    matched_signals: List[str]
    strong_signals: List[str]
    layout_signals: List[str]
    key_set_id: str
    facts_strategy: str
    text_quality: str
    key_set_ids: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _signal_hits(text_windows: Dict[str, str]) -> Dict[str, bool]:
    hits: Dict[str, bool] = {}
    for sid, spec in SIGNALS.items():
        window = text_windows.get(spec["scope"], text_windows.get("full", ""))
        hits[sid] = bool(re.search(spec["pattern"], window, re.IGNORECASE | re.MULTILINE))
    return hits


class CasePatternService:
    """Stateless pattern recognition + key-set driven section mapping."""

    #: minimum normalised score required to accept anything other than fallback
    ACCEPT_THRESHOLD = 0.4
    # a single required court-caption signal is enough on its own
    ACCEPT_MIN_NET = 1.00

    # ------------------------------------------------------------------ detect
    @classmethod
    def detect(
        cls,
        text: str,
        layout: Optional[LayoutFingerprint] = None,
        page_texts: Optional[List[str]] = None,
    ) -> Detection:
        pages = page_texts or [text]
        header = "\n\n".join(pages[:3])[:12000]
        tail = "\n\n".join(pages[-3:])[-12000:]
        windows = {"header": header, "full": text, "tail": tail}
        hits = _signal_hits(windows)
        layout_sigs = set(layout.layout_signals) if layout else set()

        scores: List[Tuple[float, float, Dict[str, Any]]] = []
        for profile in PROFILES:
            if profile["required"] and not all(hits.get(s) for s in profile["required"]):
                continue
            matched: List[str] = list(profile["required"])
            score = sum(SIGNALS[s]["weight"] for s in profile["required"] if hits.get(s))
            for sid, weight in profile["supporting"]:
                if sid.startswith("layout:"):
                    if sid in layout_sigs:
                        score += weight
                        matched.append(sid)
                elif hits.get(sid):
                    score += weight
                    matched.append(sid)
            penalty = 0.0
            for sid, weight in profile["negative"]:
                if sid.startswith("layout:"):
                    if sid in layout_sigs:
                        penalty += weight
                elif hits.get(sid):
                    penalty += weight
            net = max(score - penalty, 0.0)
            max_possible = (
                sum(SIGNALS[s]["weight"] for s in profile["required"]) + 0.0
                + sum(w for _, w in profile["supporting"])
                + 1e-9
            )
            normalized = net / max_possible if max_possible else 0.0
            scores.append((normalized, net, {**profile, "matched": matched}))

        # The generic fallback is a safety net, never a competitor: rank only
        # concrete profiles by absolute weighted evidence (normalised score is
        # the tie-break), then fall back if nothing clears the threshold.
        generic = next(p for p in PROFILES if p["id"] == "GENERIC-HC")
        candidates = [t for t in scores if t[2]["id"] != "GENERIC-HC"]
        candidates.sort(key=lambda t: (t[1], t[0]), reverse=True)

        # Accept either a well-rounded profile (normalised score) or a document
        # whose *required* court-caption signal alone fired: registry exports of
        # office notes often carry only the court name plus a case number, and
        # leaving those to the generic fallback loses the court attribution.
        accepted = bool(candidates) and (
            candidates[0][0] >= cls.ACCEPT_THRESHOLD or candidates[0][1] >= cls.ACCEPT_MIN_NET)
        if not accepted:
            chosen, normalized, net, matched = generic, 0.0, 0.0, []
            runner = candidates[0][2]["id"] if candidates else None
            runner_score = round(candidates[0][1], 2) if candidates else 0.0
        else:
            normalized, net, chosen = candidates[0]
            matched = chosen["matched"]
            runner = candidates[1][2]["id"] if len(candidates) > 1 else None
            runner_score = round(candidates[1][1], 2) if len(candidates) > 1 else 0.0

        strong = [s for s in matched if s in SIGNALS and SIGNALS[s]["weight"] >= 1.2]
        quality = "good"
        if layout and not layout.has_text_layer:
            quality = "ocr_required"
        elif layout and layout.needs_geometric_repair:
            quality = "repaired"

        spec = chosen["key_set"]
        key_set_ids = tuple(spec) if isinstance(spec, (list, tuple)) else (spec,)

        court, seat = chosen["court"], chosen["seat"]
        if chosen.get("derive_court_from_caption"):
            inferred_court, inferred_seat = _court_from_caption(windows["header"])
            if inferred_court:
                court = inferred_court
                seat = inferred_seat or seat

        return Detection(
            profile_id=chosen["id"],
            label=chosen["label"],
            court=court,
            seat=seat,
            drafting_style=chosen["drafting_style"],
            confidence=round(normalized, 3),
            score=round(net, 2),
            runner_up=runner,
            runner_up_score=runner_score,
            matched_signals=sorted(set(matched)),
            strong_signals=strong,
            layout_signals=sorted(layout_sigs),
            key_set_id=key_set_ids[0],
            key_set_ids=key_set_ids,
            facts_strategy=chosen["facts_strategy"],
            text_quality=quality,
        )

    # -------------------------------------------------------------- key sets
    @classmethod
    def key_set_for(cls, profile_id: str) -> Dict[str, Any]:
        """
        Resolve a profile's key set.

        ``key_set`` may be a single id or an ordered list — later sets extend the
        earlier ones (anchors are unioned, highest confidence wins), so a court
        profile reads as ``["KEY-HC-COMMON", "KEY-EXTRA-<COURT>"]``.
        """
        profile = next((p for p in PROFILES if p["id"] == profile_id), None)
        if not profile:
            return KEY_SETS["KEY-GENERIC"]
        spec = profile.get("key_set")
        ids = spec if isinstance(spec, (list, tuple)) else [spec]
        merged: Dict[str, Any] = {}
        for set_id in ids:
            merged = _merge_key_sets(merged, KEY_SETS.get(set_id, {}))
        return merged or KEY_SETS["KEY-GENERIC"]

    @classmethod
    def shortlist_keys(cls, text: str, detection: Detection) -> Dict[str, List[Dict[str, Any]]]:
        """
        Run every key in the detected key set and report which keys hit.

        This is the "shortlisting" step: it tells the operator, per category,
        which anchors are present in this file and with what weight.  Downstream
        extraction only relies on keys that actually hit.
        """
        keyset = cls.key_set_for(detection.profile_id)
        caption = text[:2500]
        report: Dict[str, List[Dict[str, Any]]] = {}
        for category, keys in keyset.items():
            hits: List[Dict[str, Any]] = []
            for key_id, spec in keys.items():
                candidates: List[Tuple[str, Any, bool]] = []
                for anchor in spec["anchors"]:
                    m = re.search(anchor, caption, re.IGNORECASE | re.MULTILINE)
                    if m:
                        candidates.append((anchor, m, True))
                        break
                if not candidates:
                    for anchor in spec["anchors"]:
                        m = re.search(anchor, text, re.IGNORECASE | re.MULTILINE)
                        if m:
                            candidates.append((anchor, m, False))
                            break
                for anchor, m, in_caption in candidates:
                    if m:
                        hits.append({
                            "key": key_id,
                            "anchor": anchor,
                            "confidence": spec["confidence"],
                            "window": spec["window"],
                            "match": re.sub(r"\s+", " ", m.group(0)).strip()[:160],
                            "group": ((m.group(1) or "")[:120] if m.groups() else None),
                            "in_caption": in_caption,
                        })
                        break
            if hits:
                report[category] = hits
        return report

    # ------------------------------------------------------------ text hygiene
    @classmethod
    def clean_text(cls, text: str, layout: Optional[LayoutFingerprint] = None,
                   detection: Optional[Detection] = None) -> str:
        """Strip registry furniture (footers, page clocks, rules, repeated heads)."""
        noise_patterns = [
            r"https?://www\.mhc\.tn\.gov\.in/judis",
            r"(?m)^\s*Page\s*\d+\s+of\s+\d+\s*$",
            r"(?m)^\s*\d{1,3}\s*/\s*\d{1,3}\s*$",
            r"(?m)^\s*[_\-\*]{5,}\s*$",
            r"(?m)^\s*={8,}\s*$",
            r"(?m)^\s*\*{4,}\s*$",
            r"(?m)^\s*---\s*PAGE\s*\d+\s*---\s*$",
        ]
        cleaned = text
        for pattern in noise_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

        # Running headers repeat on every page — including the first, where they
        # are the case number itself.  Strip repeats but always keep the first
        # occurrence so the caption still yields the case identity.
        if layout and layout.repeated_header_lines:
            for line in layout.repeated_header_lines:
                pattern = re.compile(r"(?m)^[ \t]*" + re.escape(line.strip()) + r"[ \t]*$")
                seen = {"count": 0}

                def _keep_first(match, _seen=seen):
                    _seen["count"] += 1
                    return match.group(0) if _seen["count"] == 1 else ""

                cleaned = pattern.sub(_keep_first, cleaned)

        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    # ---------------------------------------------------------------- sections
    @classmethod
    def _find_span(cls, text: str, start_anchors: Sequence[str], end_anchors: Sequence[str],
                   search_from: int = 0, max_len: int = 12000) -> Optional[Tuple[int, int, str]]:
        start_match = None
        for anchor in start_anchors:
            for m in re.finditer(anchor, text[search_from:], re.IGNORECASE | re.MULTILINE):
                start_match = (search_from + m.start(), search_from + m.end(), anchor)
                break
            if start_match:
                break
        if not start_match:
            return None
        body_start = start_match[1]
        end = min(len(text), body_start + max_len)
        for anchor in end_anchors:
            m = re.search(anchor, text[body_start:end], re.IGNORECASE | re.MULTILINE)
            if m:
                end = body_start + m.start()
                break
        return body_start, end, start_match[2]

    #: per-unit caps so a missing end anchor cannot swallow the whole judgment
    UNIT_CAPS = {
        "relief": 4000, "facts": 9000, "issues": 4000,
        "reasoning": 7000, "operative": 2500, "signature": 1500,
    }
    UNIT_ORDER = ("relief", "facts", "issues", "reasoning", "operative", "signature")

    @classmethod
    def map_sections(cls, text: str, detection: Detection) -> Dict[str, Any]:
        """
        Slice the document into the rhetorical units declared by the key set.

        Each unit is closed by (a) an explicit end anchor from the key set,
        (b) the start anchor of the next unit, or (c) the unit's length cap —
        whichever comes first.  This keeps a missing anchor from turning a prayer
        into a 12,000-character block.

        Returns ``{unit: {"text","start","end","anchor","length","confidence"}}``
        plus an ordered ``units`` list.
        """
        keyset = cls.key_set_for(detection.profile_id)
        out: Dict[str, Any] = {"units": []}

        # collect start anchors per unit
        starts: Dict[str, List[str]] = {}
        for unit in cls.UNIT_ORDER:
            group = keyset.get(unit) or {}
            anchors: List[str] = []
            if unit == "facts":
                anchors = (group.get("explicit_heading", {}).get("anchors", [])
                           + group.get("start", {}).get("anchors", []))
            else:
                for spec in group.values():
                    anchors.extend(spec["anchors"])
            if anchors:
                starts[unit] = anchors

        # natural terminators
        terminator = list(keyset.get("signature", {}).values())
        terminator_anchors = [a for spec in terminator for a in spec["anchors"]]
        reasoning_anchors = [a for spec in (keyset.get("reasoning") or {}).values() for a in spec["anchors"]]
        operative_anchors = [a for spec in (keyset.get("operative") or {}).values() for a in spec["anchors"]]

        for unit in cls.UNIT_ORDER:
            anchors = starts.get(unit)
            if not anchors:
                continue
            cap = cls.UNIT_CAPS.get(unit, 5000)
            end_anchors: List[str] = []
            if unit == "facts":
                end_anchors = ((keyset.get("facts") or {}).get("end", {}).get("anchors", [])
                               + reasoning_anchors)
            elif unit == "relief":
                end_anchors = ([r"For\s+(?:the\s+)?(?:Petitioners?|Respondents?|Appellants?)",
                                r"^\s*(?:ORDER|J\s*U\s*D\s*G\s*M\s*E\s*N\s*T)\s*[:\-]?\s*$"]
                               + reasoning_anchors)
            elif unit == "issues":
                end_anchors = reasoning_anchors + operative_anchors
            elif unit == "reasoning":
                end_anchors = operative_anchors
            else:
                end_anchors = terminator_anchors
            span = cls._find_span(text, anchors, end_anchors, max_len=cap)
            if not span:
                continue
            start, stop, anchor = span
            snippet = text[start:stop].strip()
            if len(snippet) < 40:
                continue
            out[unit] = {
                "text": snippet,
                "start": start,
                "end": stop,
                "anchor": anchor,
                "length": len(snippet),
                "capped": (stop - start) >= cap - 1,
                "confidence": round(min(0.95, 0.55 + 0.05 * min(len(snippet) / 400, 8)), 3),
            }
            out["units"].append(unit)
        return out

    # ------------------------------------------------------------ fact mapping
    @classmethod
    def _paragraphs(cls, text: str) -> List[Dict[str, Any]]:
        """Split body text into numbered/unnumbered paragraphs with offsets."""
        paras: List[Dict[str, Any]] = []
        # a paragraph marker is a number + '.' / ')' followed by whitespace or an
        # end of line — this deliberately rejects date fragments such as "11.1984"
        pattern = re.compile(r"(?m)^[ \t]*(?P<num>\d{1,3})[\.\)](?:[ \t]+(?!\d)|\s*$)")
        matches = list(pattern.finditer(text))
        if not matches:
            blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
            offset = 0
            for i, block in enumerate(blocks):
                idx = text.find(block, offset)
                paras.append({"ordinal": i + 1, "label": None, "text": block,
                              "start": idx, "end": idx + len(block), "length": len(block)})
                offset = idx + len(block)
            return paras
        for i, m in enumerate(matches):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = re.sub(r"\s+", " ", text[start:end]).strip()
            if body:
                paras.append({"ordinal": i + 1, "label": m.group("num"), "text": body,
                              "start": start, "end": end, "length": len(body)})
        return paras

    _DATE_RE = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{4}\b")
    _CRIME_RE = re.compile(r"\b(?:Crime|Cr|FIR|F\.I\.R|C\.C|C\.C\.No|R\.C)\.?\s*No\.?\s*[\d/]+", re.I)
    _PLACE_RE = re.compile(r"\b(?:District|Distt|Taluk|Tehsil|Police\s+Station|P\.S\.|Village|"
                           r"Post|P\.O\.|Ward|Nagar|Chennai|Madurai|Bilaspur|Patna)\b", re.I)
    _LEGAL_ANALYSIS_RE = re.compile(r"\b(?:held\s+that|it\s+is\s+settled|reported\s+in|SCC|"
                                    r"relied\s+on|ratio|precedent|catena\s+of\s+cases|"
                                    r"judgment\s+of\s+the\s+Hon|law\s+laid\s+down)\b", re.I)
    _ISSUE_RE = re.compile(r"\b(?:whether|question\s+that\s+arises|point[s]?\s+for\s+consideration|"
                           r"it\s+is\s+contended|submissions?)\b", re.I)
    _PRAYER_RE = re.compile(r"\b(?:prays?|prayer|may\s+be\s+pleased|seeking\s+(?:the\s+)?(?:relief|direction))\b", re.I)

    @classmethod
    def _fact_score(cls, paragraph: str) -> Dict[str, float]:
        """Score how factual (as opposed to argumentative) a paragraph is."""
        text = paragraph
        dates = len(cls._DATE_RE.findall(text))
        crime = len(cls._CRIME_RE.findall(text))
        places = len(cls._PLACE_RE.findall(text))
        analysis = len(cls._LEGAL_ANALYSIS_RE.findall(text))
        issues = len(cls._ISSUE_RE.findall(text))
        prayer = len(cls._PRAYER_RE.findall(text))
        narrative = len(re.findall(
            r"\b(?:on|at|about)\s+\d{1,2}[.:]\d{2}\s*(?:hours|hrs)|"
            r"\b(?:arrested|seized|filed|issued|allotted|appointed|joined|died|executed|"
            r"surrender(?:ed)?|remanded|registered|passed|sanctioned|transferred)\b", text, re.I))
        score = (1.2 * min(dates, 4) + 1.6 * min(crime, 3) + 0.5 * min(places, 5)
                 + 0.35 * min(narrative, 10) - 0.8 * min(analysis, 6) - 0.6 * min(issues, 4)
                 - 0.9 * min(prayer, 3))
        return {
            "dates": dates, "crime_refs": crime, "places": places, "analysis": analysis,
            "issues": issues, "prayer": prayer, "narrative_verbs": narrative,
            "score": round(score, 2),
        }

    #: hard ceiling on the extracted factual matrix (~3 pages of judgment prose)
    FACT_CAP = 4500

    _COUNSEL_TURN_RE = re.compile(
        r"^\s*(?:\d+\s*[\.\)]\s*)?(?:The\s+)?(?:learned|ld\.)\s+"
        r"(?:counsel|Public\s+Prosecutor|Additional\s+Public\s+Prosecutor|APP|A\.P\.P\.|"
        r"Government\s+Advocate|Panel\s+Lawyer|DAG)",
        re.IGNORECASE,
    )

    @classmethod
    def _trim_region(cls, text: str, start: int, end: int, cap: int) -> Tuple[int, int]:
        """Shrink a region to <= cap characters, cutting on a paragraph/sentence edge."""
        if end - start <= cap:
            return start, end
        window = text[start:start + cap]
        cut = max(window.rfind("\n\n"), window.rfind(". "))
        if cut < cap * 0.5:
            cut = cap
        return start, start + cut

    @classmethod
    def _candidate_regions(cls, text: str, keyset: Dict[str, Any],
                           paragraphs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """All plausible factual-matrix regions, each tagged with provenance."""
        facts_spec = keyset.get("facts", {})
        end_anchors = list(facts_spec.get("end", {}).get("anchors", []))
        candidates: List[Dict[str, Any]] = []

        def add(start_anchor: str, anchors: List[str], anchored: bool, strategy: str) -> None:
            span = cls._find_span(text, anchors, end_anchors, max_len=cls.FACT_CAP * 2)
            if not span:
                return
            start, stop, matched = span
            start, stop = cls._trim_region(text, start, stop, cls.FACT_CAP)
            candidates.append({
                "start": start, "end": stop, "anchor": matched,
                "anchored": anchored, "strategy": strategy,
            })

        # 1. explicit registry heading ("Brief Facts Of Case", "Facts of the Case")
        if "explicit_heading" in facts_spec:
            add("explicit_heading", facts_spec["explicit_heading"]["anchors"], True, "explicit_heading")
        # 2. profile start anchors (ORDER / JUDGMENT / first numbered para)
        if "start" in facts_spec:
            add("start", facts_spec["start"]["anchors"], True, "anchored_span")

        # 3. rolling paragraph runs — works when a registry prints no heading at all
        if paragraphs:
            for i, para in enumerate(paragraphs[:12]):
                if para["length"] < 120:
                    continue
                run_start, run_end = para["start"], para["end"]
                for nxt in paragraphs[i + 1:i + 12]:
                    if run_end and nxt["start"] - run_end > 600:
                        break
                    if cls._COUNSEL_TURN_RE.search(nxt["text"]):
                        break
                    if cls._fact_score(nxt["text"])["score"] < -1.0:
                        break
                    if nxt["end"] - run_start > cls.FACT_CAP:
                        break
                    run_end = nxt["end"]
                candidates.append({
                    "start": run_start, "end": run_end,
                    "anchor": "paragraph_run", "anchored": False,
                    "strategy": "paragraph_scan",
                })

        # 4. post-caption body start — for reserved judgments that print no
        #    JUDGMENT heading (e.g. Madras order-in-original files): the body
        #    begins at the first narrative paragraph after the caption's last
        #    prayer/counsel unit.  Search a caption window, not the whole body,
        #    so an operative "prayer is allowed" near the end cannot suppress
        #    the fallback.
        caption_window = text[:10000]
        caption_anchors = [a for spec in (keyset.get("relief") or {}).values() for a in spec["anchors"]]
        caption_anchors += [a for spec in (keyset.get("counsel") or {}).values() for a in spec["anchors"]]
        last_caption_anchor = 0
        for anchor in caption_anchors:
            for match in re.finditer(anchor, caption_window, re.IGNORECASE | re.MULTILINE):
                last_caption_anchor = max(last_caption_anchor, match.end())
        if not last_caption_anchor:
            for match in re.finditer(
                r"(?im)^\s*(?:\.{2,}|…|-{2,})\s*(?:Petitioners?|Respondents?|Applicants?|Appellants?)\b",
                caption_window,
            ):
                last_caption_anchor = max(last_caption_anchor, match.end())
        if last_caption_anchor:
            for idx, para in enumerate(paragraphs):
                if para["start"] <= last_caption_anchor:
                    continue
                if cls._fact_score(para["text"])["score"] < 1.5:
                    continue
                run_end = para["end"]
                for nxt in paragraphs[idx + 1:idx + 12]:
                    if nxt["start"] - run_end > 600 or cls._COUNSEL_TURN_RE.search(nxt["text"]):
                        break
                    if nxt["end"] - para["start"] > cls.FACT_CAP:
                        break
                    run_end = nxt["end"]
                candidates.append({
                    "start": para["start"], "end": run_end,
                    "anchor": "post_caption_body", "anchored": False,
                    "strategy": "post_caption_body",
                })
                break
        return candidates

    @classmethod
    def _region_score(cls, region: str, anchored: bool, strategy: str = "") -> float:
        sig = cls._fact_score(region)
        score = sig["score"]
        score += 3.0 if anchored else 0.0
        if strategy == "explicit_heading":
            # a registry that names the section is the strongest possible signal
            score += 3.0
        length = len(region)
        if 700 <= length <= cls.FACT_CAP:
            score += 2.5
        elif length < 200:
            score -= 5.0
        if re.search(r"(?:SCC|reported\s+in|held\s+that|it\s+is\s+settled)\b", region, re.I):
            score -= 2.0
        score += min(sig["dates"], 6) * 0.4
        # caption furniture is the classic false start: party addresses,
        # "... Petitioners" designators and counsel lines are not case facts
        if re.search(r"\.\.\.?\s*(?:Petitioners?|Respondents?|Applicants?|Appellants?)", region, re.I):
            score -= 6.0
        if re.search(r"For\s+(?:the\s+)?(?:Petitioners?|Respondents?|Applicants?)\s*:", region, re.I):
            score -= 2.0
        return round(score, 2)

    @classmethod
    def extract_case_facts(cls, text: str, detection: Detection,
                           sections: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Extract the factual matrix ("case facts") for the detected profile.

        Candidate-and-score design (rather than a single fragile regex):

        1. **Explicit heading candidate** — registries that name the section
           ("Brief Facts Of Case" on Patna files, "Facts of the case" elsewhere).
        2. **Profile anchor candidate** — the profile's start anchors (ORDER /
           JUDGMENT heading, first numbered paragraph) bounded by its end
           anchors (counsel turns, "I have heard", issue framing).
        3. **Rolling paragraph-run candidates** — for templates that print no
           section headings at all (most Madras orders), every plausible run of
           contiguous narrative paragraphs is proposed.
        4. **Post-caption body candidate** — for reserved judgments with no
           ``JUDGMENT`` heading, the first factual paragraph after the last
           prayer unit is proposed as the body start.

        Every candidate is scored on factuality (dates, crime numbers, places,
        police stations, action verbs) minus legal-argument markers, then
        trimmed to a paragraph edge.  The winner plus its provenance is returned
        alongside a compact fact sheet.
        """
        sections = sections or cls.map_sections(text, detection)
        keyset = cls.key_set_for(detection.profile_id)
        paragraphs = cls._paragraphs(text)

        candidates = cls._candidate_regions(text, keyset, paragraphs)
        if not candidates:
            return {
                "facts": None, "facts_strategy": detection.facts_strategy,
                "facts_anchor": None, "facts_paragraphs": [],
                "fact_sheet": cls._fact_sheet(""), "confidence": 0.0,
                "candidates_considered": 0,
            }

        scored = []
        for cand in candidates:
            region = text[cand["start"]:cand["end"]]
            if len(region.strip()) < 120:
                continue
            scored.append((cls._region_score(region, cand["anchored"], cand["strategy"]), cand, region))
        if not scored:
            return {
                "facts": None, "facts_strategy": detection.facts_strategy,
                "facts_anchor": None, "facts_paragraphs": [],
                "fact_sheet": cls._fact_sheet(""), "confidence": 0.0,
                "candidates_considered": len(candidates),
            }
        scored.sort(key=lambda t: t[0], reverse=True)
        best_score, best, best_region = scored[0]

        facts_text = re.sub(r"[ \t]+", " ", best_region).strip()
        facts_text = re.sub(r"\n{3,}", "\n\n", facts_text)
        fact_sheet = cls._fact_sheet(facts_text)
        # Police stations are often printed only in the respondent caption
        # ("Inspector of Police, X Police Station"), outside the factual matrix.
        # Restrict the fallback to the caption window: scanning the whole body
        # would pull station names out of cited precedents into this case.
        caption = re.sub(r"\s+", " ", text[:6000])
        station_seen = {s.casefold() for s in fact_sheet["police_stations"]}
        for station in cls._police_stations(caption):
            if station.casefold() not in station_seen:
                station_seen.add(station.casefold())
                fact_sheet["police_stations"].append(station)
        fact_sheet["police_stations"] = fact_sheet["police_stations"][:8]

        confidence = 0.45
        if best["anchored"]:
            confidence += 0.3
        if best["strategy"] == "explicit_heading":
            confidence += 0.15
        if fact_sheet["dates"]:
            confidence += 0.06
        if fact_sheet["crime_numbers"] or fact_sheet["offences"]:
            confidence += 0.06
        if fact_sheet.get("police_stations"):
            confidence += 0.03
        if 400 <= len(facts_text) <= cls.FACT_CAP:
            confidence += 0.05
        # a clear margin over the runner-up means the choice is stable
        if len(scored) > 1 and best_score - scored[1][0] >= 3:
            confidence += 0.03

        span_paragraphs = [
            {"ordinal": p["ordinal"], "score": cls._fact_score(p["text"])["score"],
             "length": p["length"]}
            for p in paragraphs
            if p["start"] >= best["start"] and p["end"] <= best["end"]
        ]
        return {
            "facts": facts_text or None,
            "facts_strategy": best["strategy"],
            "facts_anchor": best["anchor"],
            "facts_paragraphs": span_paragraphs[:15],
            "fact_sheet": fact_sheet,
            "confidence": round(min(confidence, 0.95), 3),
            "candidates_considered": len(candidates),
            "region_score": best_score,
        }

    #: Fact-sheet dates include the numeric registry idiom and the textual
    #: idioms used in reserved judgments ("9th October, 2026", "OCTOBER 22, 2026").
    _MONTH_NAME = (
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    )
    _FACT_DATE_RE = re.compile(
        rf"\b(?:\d{{1,2}}[./-]\d{{1,2}}[./-]\d{{4}}|"
        rf"\d{{1,2}}(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?{_MONTH_NAME}\.?,?\s+\d{{4}}|"
        rf"{_MONTH_NAME}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}})\b",
        re.IGNORECASE,
    )
    _CRIME_FULL_RE = re.compile(
        r"\b(?:Crime|Cr\.?|F\.?I\.?R\.?|C\.?C\.?|R\.?C\.?|Charge\s+Sheet|Final\s+Report)"
        r"\s*(?:(?:bearing|registered\s+as|vide)\s+)?(?:No\.?|Number|#)\s*[:\-]?\s*"
        r"\d+(?:[./-]\d+)*(?:[A-Za-z]\d*)?(?:\s*(?:of|/)\s*\d{2,4})?",
        re.IGNORECASE,
    )
    _OFFENCE_ACT = (
        r"(?:I\.?P\.?C\.?|B\.?N\.?S\.?S\.?|B\.?N\.?S\.?|Cr\.?P\.?C\.?|C\.?P\.?C\.?|"
        r"NDPS|POCSO|SC/ST|[A-Z][A-Za-z\.\s&()\-]{2,70}?(?:Act|Code|Sanhita|Adhiniyam|Rules)"
        r"(?:\s*,?\s*\d{4})?)"
    )
    _OFFENCE_RE = re.compile(
        rf"\b(?:Sections?|Secs?\.?|U/S)\s+\d[\dA-Za-z()\-]*"
        rf"(?:\s*(?:,|and|&|/|read\s+with|r/w)\s*(?:Sections?|Secs?\.?)?\s*\d[\dA-Za-z()\-]*)*"
        rf"\s+(?:of\s+(?:the\s+)?)?{_OFFENCE_ACT}",
        re.IGNORECASE,
    )
    _PLACE_NAME_RE = re.compile(
        r"\b(?:District|Taluk|Tehsil|Village|Police\s+Station|P\.S\.)\s+(?:of\s+)?([A-Z][A-Za-z\.]{2,20})"
        r"|\b([A-Z][A-Za-z\.]{2,20})\s+(?:District|Taluk|Tehsil|Village)\b"
    )
    _PLACE_STOPWORDS = {
        "additional", "district", "sessions", "special", "judicial", "magistrate",
        "court", "principal", "senior", "junior", "civil", "criminal", "chief",
        "metropolitan", "sub", "assistant", "deputy", "learned", "trial",
    }
    #: Police-station names appear both before and after the designator:
    #: ``Mallanginar Police Station`` / ``Police Station Majalgaon`` / ``P.S. Kotwali``.
    _PS_NAME = r"[A-Z][A-Za-z0-9.&'\-]{1,30}(?:\s+[A-Z][A-Za-z0-9.&'\-]{1,30}){0,4}"
    _EVIDENCE_TAIL = r"(?:[^.\n]|\.(?![ \n]|$)){0,90}"
    _POLICE_STATION_SUFFIX_RE = re.compile(
        rf"\b({_PS_NAME})\s+(?:[Pp]olice\s+[Ss]tation|P\.?\s*S\.?)\b"
    )
    _POLICE_STATION_PREFIX_RE = re.compile(
        rf"\b(?:[Pp]olice\s+[Ss]tation|P\.?\s*S\.?)\s*[-:.]?\s*(?:of\s+)?({_PS_NAME})"
        r"(?=\s*(?:[,;.)]|\n|$|\b(?:District|Taluk|Tehsil|Village|Post|P\.O\.|Case|No|Crime|FIR|"
        r"C\.C|R\.C|Charge|and|for|under|on|in|registered|was|were|has|have|had)\b))"
    )
    _POLICE_STATION_STOPWORDS = {
        "the", "a", "an", "of", "at", "from", "to", "and", "or", "respondent",
        "petitioner", "accused", "complainant", "state", "inspector", "sub",
        "case", "crime", "fir", "no", "cc", "rc", "charge", "final", "report",
        "police", "station",
    }
    _POLICE_STATION_REJECT_RE = re.compile(
        r"\b(?:college|engineering|school|hospital|court|limited|ltd|private|university)\b",
        re.IGNORECASE,
    )
    _AMOUNT_RE = re.compile(r"(?<![A-Za-z])(?:Rs\.?|₹)\s?\d[\d,]*(?:\.\d+)?(?:\s*(?:lakh|crore))?(?:\s*/\-)?", re.IGNORECASE)
    # Status cues are deliberately explicit: "may be arrested" / "in the event
    # of arrest" are prospective bail arguments, not an arrest status.
    _CUSTODY_RE = re.compile(
        rf"(?:\b(?:released|enlarged|liberated)\s+(?:on|upon)\s+bail{_EVIDENCE_TAIL}"
        rf"|\b(?:not|never)\s+in\s+custody{_EVIDENCE_TAIL}"
        rf"|\b(?:in|into|under|remanded\s+to|sent\s+to|taken\s+into)\s+"
        rf"(?:judicial\s+|police\s+|illegal\s+|wrongful\s+)?custody(?:\s+(?:since|for|from|on|under){_EVIDENCE_TAIL})?"
        rf"|\b(?:judicial|police)\s+custody(?:\s+(?:since|for|from|on){_EVIDENCE_TAIL})?"
        rf"|\bcustody\s+(?:since|for){_EVIDENCE_TAIL}"
        rf"|\bunder\s+detention(?:\s+since)?{_EVIDENCE_TAIL})",
        re.IGNORECASE,
    )
    _ARREST_RE = re.compile(
        rf"(?:\b(?:was|were|is|are)\s+(?:(?:not|never)\s+)?(?:arrested|apprehended|detained){_EVIDENCE_TAIL}"
        rf"|\b(?:has|have|had)\s+(?:(?:not|never)\s+)?been\s+(?:arrested|apprehended|detained){_EVIDENCE_TAIL}"
        rf"|\b(?:not|never)\s+arrested{_EVIDENCE_TAIL}"
        rf"|\b(?:arrested|apprehended|detained)\s+(?:on|at|by|in\s+connection){_EVIDENCE_TAIL}"
        rf"|\bsurrendered\s+(?:before|on|at){_EVIDENCE_TAIL}"
        rf"|\btaken\s+into\s+custody{_EVIDENCE_TAIL})",
        re.IGNORECASE,
    )

    @classmethod
    def _police_stations(cls, facts_text: str) -> List[str]:
        """Deterministic police-station name capture (prefix and suffix forms)."""
        stations: List[str] = []
        seen: set[str] = set()
        for pattern in (cls._POLICE_STATION_SUFFIX_RE, cls._POLICE_STATION_PREFIX_RE):
            for match in pattern.finditer(facts_text):
                name = re.sub(r"\s+", " ", match.group(1)).strip(" .,;:-")
                name = re.sub(r"(?i)^(?:the|at|from|of|to)\s+", "", name).strip()
                if not name or len(name) < 3:
                    continue
                first = name.split()[0].lower().strip(".,;:-")
                if first in cls._POLICE_STATION_STOPWORDS:
                    continue
                if cls._POLICE_STATION_REJECT_RE.search(name):
                    continue
                key = name.casefold()
                if key not in seen:
                    seen.add(key)
                    stations.append(name)
        return stations[:8]

    @staticmethod
    def _last_evidence(pattern: re.Pattern, text: str) -> Optional[str]:
        """Return the last explicit status cue (narratives are chronological)."""
        matches = list(pattern.finditer(text))
        if not matches:
            return None
        return re.sub(r"\s+", " ", matches[-1].group(0)).strip()

    @staticmethod
    def _custody_status(evidence: Optional[str]) -> Optional[str]:
        if not evidence:
            return None
        low = evidence.lower()
        if re.search(r"\b(?:not|never)\s+in\s+custody\b", low):
            return "not_in_custody"
        if re.search(r"\b(?:released|enlarged|liberated)\s+(?:on|upon)\s+bail\b", low):
            return "released_on_bail"
        if "judicial custody" in low:
            return "judicial_custody"
        if "police custody" in low:
            return "police_custody"
        return "in_custody"

    @staticmethod
    def _arrest_status(evidence: Optional[str]) -> Optional[str]:
        if not evidence:
            return None
        low = evidence.lower()
        if re.search(r"\b(?:not|never)\s+(?:been\s+)?arrested\b", low):
            return "not_arrested"
        if "surrendered" in low:
            return "surrendered"
        if "apprehended" in low:
            return "apprehended"
        if "detained" in low or "taken into custody" in low:
            return "detained"
        return "arrested"

    @classmethod
    def _fact_sheet(cls, facts_text: str) -> Dict[str, Any]:
        """Structured slice of the factual matrix: dates, crime/FIR numbers,
        police stations, places, offences, custody/arrest status + evidence,
        and monetary amounts.  ``custody`` / ``arrest`` remain verbatim evidence
        strings for compatibility; the ``*_status`` fields are the normalized
        labels.  Unknown is represented by None, never by a guessed status."""
        if not facts_text:
            return {"dates": [], "crime_numbers": [], "police_stations": [],
                    "places": [], "offences": [], "custody": None,
                    "custody_status": None, "arrest": None,
                    "arrest_status": None, "amounts": []}
        flat = re.sub(r"\s+", " ", facts_text).strip()
        dates = list(dict.fromkeys(
            re.sub(r"\s+", " ", m.group(0)).strip() for m in cls._FACT_DATE_RE.finditer(flat)))[:12]
        crime_numbers = list(dict.fromkeys(
            re.sub(r"\s+", " ", m.group(0)).strip() for m in cls._CRIME_FULL_RE.finditer(flat)))[:8]
        police_stations = cls._police_stations(flat)
        places: List[str] = []
        for m in cls._PLACE_NAME_RE.finditer(flat):
            name = (m.group(1) or m.group(2) or "").strip(" .,")
            if name and name not in places and name.lower() not in cls._PLACE_STOPWORDS:
                places.append(name)
        offences = list(dict.fromkeys(
            re.sub(r"\s+", " ", m.group(0)).strip() for m in cls._OFFENCE_RE.finditer(flat)))[:8]
        custody = cls._last_evidence(cls._CUSTODY_RE, flat)
        arrest = cls._last_evidence(cls._ARREST_RE, flat)
        amounts = list(dict.fromkeys(
            re.sub(r"\s+", " ", m.group(0)).strip() for m in cls._AMOUNT_RE.finditer(flat)))[:5]
        return {
            "dates": dates,
            "crime_numbers": crime_numbers,
            "police_stations": police_stations,
            "places": places[:10],
            "offences": offences,
            "custody": custody,
            "custody_status": cls._custody_status(custody),
            "arrest": arrest,
            "arrest_status": cls._arrest_status(arrest),
            "amounts": amounts,
        }

    # ----------------------------------------------------- caption utilities
    _NAME_NOISE_RE = re.compile(
        r"(?:CORAM|PRESENT|HON[’'`]?BLE|HONOURABLE|JUSTICE|JUDGE|J\.\s*$|CNR|DATED|Date\b|"
        r"CAV|Reserved|Pronounced|Delivered|ORDER|JUDGMENT|BENCH|COURT|Petitioner|Respondent|"
        r"Applicant|Appellant|Accused|Complainant|Advocate|Counsel|State\b.*\brep\b)",
        re.IGNORECASE,
    )

    @classmethod
    def _clean_judge_name(cls, raw: Optional[str]) -> Optional[str]:
        """
        Turn a coram capture into a bare judge name.

        Anchors are line-based, so a capture can trail the next heading
        ("NIDHI GUPTA Present", "RITESH KUMAR CAV JUDGMENT Date").  Cut at the
        first structural marker and keep at most six name tokens.
        """
        if not raw:
            return None
        text = re.sub(r"\s+", " ", raw).strip()
        text = re.sub(r"(?i)^(?:the\s+)?(?:hon[’'`]?b?le|honourable)\s+", "", text)
        text = re.sub(r"(?i)^(?:mr\.?|ms\.?|mrs\.?|dr\.?|shri|smt\.?)\s*", "", text)
        text = re.sub(r"(?i)^justice\s+", "", text)
        cut = re.split(
            r"(?i)\b(?:present|coram|cav|reserved|pronounced|delivered|order|judgment|date|"
            r"cnr|bench|court|the\s+hon)\b", text)[0]
        tokens = [t for t in cut.replace(",", " ").split() if t]
        tokens = [t for t in tokens if re.fullmatch(r"[A-Za-z][A-Za-z\.\-']*", t)]
        if not tokens:
            return None
        name = " ".join(tokens[:6]).strip(" .,-")
        if len(name) < 3 or name.upper() in {"JUDGE", "COURT"}:
            return None
        return name

    _STOPWORD_NAMES = {
        "AND", "OR", "THE", "IN", "VS", "VERSUS", "WITH", "FOR", "TO", "OF", "ON",
        "CNR", "CRL", "WP", "WMP", "CONT", "CMP", "JUDGE", "COURT", "ORDER",
    }

    @classmethod
    def _looks_like_name(cls, line: str) -> bool:
        text = line.strip(" .,;-\t")
        if text.upper() in cls._STOPWORD_NAMES:
            return False
        if not (2 < len(text) <= 90):
            return False
        if re.match(r"(?i)^\s*(?:case|crime|petition|original)\b", text):
            return False
        if "@" in text and text.count(" ") > 6:
            return False
        if re.fullmatch(r"[\d\W]+", text):
            return False
        if text.startswith(("(", "[")):
            return False
        if cls._NAME_NOISE_RE.search(text) and not re.match(r"^[A-Z][a-z]+\.?\s+[A-Z]", text):
            return False
        letters = sum(ch.isalpha() for ch in text)
        return letters >= max(3, len(text) * 0.4)

    #: tokens that mark the point in a party line where the address begins
    _PARTY_TAIL_RE = re.compile(
        r"\s+(?:S/o|D/o|W/o|Son\s+of|Daughter\s+of|Wife\s+of|Aged\s+about|Aged|Resident|R/o|"
        r"Rep\.?\s+by|represented\s+by|through|Mob\.?|Pin|Post|Village)\b",
        re.IGNORECASE,
    )
    _ADDRESS_LINE_RE = re.compile(
        r"(?:^\s*No\.|\bPin\s*[-:]?\s*\d|\bMob\.?\s*[-:]?\s*\d|\bWard\s+No|\bP\.?O\.\b|"
        r"\bTahsil\b|\bTehsil\b|\bVillage\s+And\s+District\b|^\s*\d+\s*[-,]\s*\d|"
        r"\bDistrict\s+[A-Z].*\(C\.G\.\)|\b\d{6}\b)",
        re.IGNORECASE,
    )
    _CASE_NO_LIKE_RE = re.compile(
        r"\b(?:No\.?|Nos\.?)\s*[\d&\s]+of\s*\d{4}|^\s*(?:A|O\.A|W\.P|CRL|C\.M|CONT|WP|CWP|CWJC)\b",
        re.IGNORECASE,
    )

    @classmethod
    def _party_name_from_line(cls, line: str) -> Optional[str]:
        """Normalise one caption line into a bare party name (or None)."""
        text = re.sub(r"^[\s*\u2022]*(?:\d+\s*)?[-\u2013\.\)]\s*", "", line.strip())
        text = re.sub(r"(?i)\s*(?:\.{2,}|…)\s*(?:Petitioners?|Respondents?|Applicants?|Appellants?|"
                      r"Complainants?)(?:\s*/.*)?$", "", text)
        if not text or cls._ADDRESS_LINE_RE.search(text) or cls._CASE_NO_LIKE_RE.search(text):
            return None
        text = cls._PARTY_TAIL_RE.split(text)[0]
        text = re.sub(r"\s+", " ", text).strip(" .,;:-")
        if not cls._looks_like_name(text):
            return None
        return text[:120]

    @classmethod
    def extract_caption_parties(cls, text: str, detection: Detection) -> Dict[str, Optional[str]]:
        """
        Pull the first petitioner/respondent names straight out of the caption.

        Strategy: find the "versus" line, then walk **forwards** from the end of
        the caption furniture (case number / CNR / coram / date lines) towards
        it, accepting the first line that normalises to a party name.  This is
        what makes multi-line party blocks (Chhattisgarh "1 - Name S/o ... Aged
        about ... R/o ...") collapse to "Name" instead of an address fragment.

        Used when the generic Pass-1 regexes land on placeholders such as
        ``__________``, ``..Petitioner`` or a bare case number.
        """
        header = text[:6000]
        versus = re.search(r"(?im)^\s*(?:Vs\.?|Versus)\s*$", header)
        if not versus:
            return {"petitioner": None, "respondent": None}

        pre = header[:versus.start()]
        lines = pre.split("\n")

        # skip the registry furniture that precedes the first party
        furniture = re.compile(
            r"(?i)(?:\bCORAM\b|\bPRESENT\b|\bHON[’'`]?BLE\b|\bHONOURABLE\b|\bJUSTICE\b|"
            r"\bCNR\s*:|\bDATED\s*:|\bDate\s*:|\bRESERVED\s+ON\b|\bPRONOUNCED\s+ON\b|"
            r"\bOrder\s+(?:Reserved|passed)\b|\bDate\s+of\s+Decision\b|\bBENCH\b|"
            r"\bJUDICATURE\b|\bHIGH\s+COURT\b|^\s*N?AFR\s*$|^\s*=+|^\s*_+\s*$)"
        )
        start_index = 0
        for idx, line in enumerate(lines):
            if furniture.search(line) or cls._CASE_NO_LIKE_RE.search(line) and "No." in line:
                start_index = idx + 1

        petitioner = None
        previous = ""
        for line in lines[start_index:]:
            stripped = line.strip()
            # a short ALL-CAPS line directly under a JUDGE line is the wrapped
            # tail of the coram, not a party name
            coram_wrap = (
                previous
                and re.search(r"(?i)\bJUSTICE\b", previous)
                and len(stripped.split()) <= 2
                and stripped.isupper()
            )
            if not coram_wrap:
                candidate = cls._party_name_from_line(line)
                if candidate:
                    petitioner = candidate
                    break
            if stripped:
                previous = stripped

        respondent = None
        for line in header[versus.end():].split("\n"):
            candidate = cls._party_name_from_line(line)
            if candidate:
                respondent = candidate
                break

        return {"petitioner": petitioner, "respondent": respondent}

    # ------------------------------------------------------------- full report
    @classmethod
    def detect_from_text(cls, text: str, page_texts: Optional[List[str]] = None) -> Detection:
        """Detection for callers that already have text (no PDF geometry)."""
        return cls.detect(text, layout=None, page_texts=page_texts)

    @classmethod
    def analyse_pdf(cls, path: str, include_text: bool = False) -> Dict[str, Any]:
        """End-to-end report for a single PDF: layout + profile + keys + facts."""
        text, layout, meta = extract_pdf_text(path)
        detection = cls.detect(text, layout, meta["pages"])
        cleaned = cls.clean_text(text, layout, detection)
        key_hits = cls.shortlist_keys(cleaned, detection)
        sections = cls.map_sections(cleaned, detection)
        facts = cls.extract_case_facts(cleaned, detection, sections)
        report: Dict[str, Any] = {
            "file": os.path.basename(path),
            "size_bytes": os.path.getsize(path),
            "layout": layout.to_dict(),
            "profile": detection.to_dict(),
            "key_hits": key_hits,
            "key_coverage": cls._coverage(key_hits, detection),
            "sections": {k: {kk: vv for kk, vv in v.items() if kk != "text"}
                         for k, v in sections.items() if k != "units"},
            # A handful of corpus PDFs are cover pages only (caption + CNR, no
            # body).  Surface that instead of reporting a silent zero-fact result.
            "text_status": "insufficient_text" if len(text.strip()) < 600 else "ok",
            "text_chars": len(text.strip()),
            "facts": {
                "strategy": facts["facts_strategy"],
                "anchor": facts["facts_anchor"],
                "length": len(facts["facts"] or ""),
                "confidence": facts["confidence"],
                "fact_sheet": facts["fact_sheet"],
                "preview": (facts["facts"] or "")[:420],
            },
            "analysed_at": datetime.utcnow().isoformat() + "Z",
        }
        if include_text:
            report["text"] = cleaned
        return report

    @staticmethod
    def _coverage(key_hits: Dict[str, List[Dict[str, Any]]],
                  detection: Detection) -> Dict[str, Any]:
        keyset = CasePatternService.key_set_for(detection.profile_id)
        total = sum(len(v) for v in keyset.values())
        found = sum(len(v) for v in key_hits.values())
        by_cat = {cat: {"found": len(key_hits.get(cat, [])), "declared": len(keys)}
                  for cat, keys in keyset.items()}
        return {
            "found": found,
            "declared": total,
            "ratio": round(found / total, 3) if total else 0.0,
            "by_category": by_cat,
        }


# Module-level convenience wrappers -----------------------------------------
case_pattern_service = CasePatternService()


def detect_case_pattern(text: str, page_texts: Optional[List[str]] = None) -> Detection:
    return CasePatternService.detect_from_text(text, page_texts)


def profile_catalog() -> List[Dict[str, Any]]:
    """Profile registry as plain dicts (used by the analysis script / docs)."""
    return [
        {
            "id": p["id"], "label": p["label"], "court": p["court"], "seat": p["seat"],
            "drafting_style": p["drafting_style"], "required_signals": p["required"],
            "supporting_signals": p["supporting"], "negative_signals": p["negative"],
            "key_set": p["key_set"], "facts_strategy": p["facts_strategy"],
        }
        for p in PROFILES
    ]
