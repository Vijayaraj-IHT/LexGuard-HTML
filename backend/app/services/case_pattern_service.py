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


def _choose_page_text(page) -> Tuple[str, bool]:
    """
    Pick verbatim text or the geometrically repaired text, whichever reads
    better.  Repair is only attempted for suspicious pages and is only kept when
    it materially improves line continuity without losing content.
    """
    raw = page.get_text()
    page_dict = page.get_text("dict")
    blocks = [b for b in page_dict["blocks"] if b["type"] == 0]
    if not blocks:
        return raw, False
    clipped = sum(1 for b in blocks if (b["bbox"][2] - b["bbox"][0]) < page.rect.width * 0.42)
    suspicious = (clipped / len(blocks)) >= 0.15 or not raw.strip()
    if not suspicious:
        return raw, False

    repaired = _repair_doubled_draw(page)
    if not repaired.strip():
        return raw, False
    raw_score, rep_score = _text_quality_score(raw), _text_quality_score(repaired)
    keeps_content = len(repaired.strip()) >= 0.25 * len(raw.strip())
    if keeps_content and rep_score >= raw_score:
        return repaired, True
    return raw, False


def _detect_columnar(page) -> bool:
    """True when the page has >=2 text blocks sharing a baseline band but
    occupying disjoint x-ranges (a genuine newspaper-style column layout)."""
    blocks = [b for b in page.get_text("dict")["blocks"] if b["type"] == 0]
    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            a, b = blocks[i]["bbox"], blocks[j]["bbox"]
            y_overlap = min(a[3], b[3]) - max(a[1], b[1])
            min_h = min(a[3] - a[1], b[3] - b[1])
            x_disjoint = a[2] <= b[0] + 2 or b[2] <= a[0] + 2
            if min_h > 0 and y_overlap > 0.5 * min_h and x_disjoint:
                if (a[2] - a[0]) > 90 and (b[2] - b[0]) > 90:
                    return True
    return False


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
            if was_repaired:
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
    ACCEPT_THRESHOLD = 0.40

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

        if not candidates or candidates[0][0] < cls.ACCEPT_THRESHOLD:
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

        return Detection(
            profile_id=chosen["id"],
            label=chosen["label"],
            court=chosen["court"],
            seat=chosen["seat"],
            drafting_style=chosen["drafting_style"],
            confidence=round(normalized, 3),
            score=round(net, 2),
            runner_up=runner,
            runner_up_score=runner_score,
            matched_signals=sorted(set(matched)),
            strong_signals=strong,
            layout_signals=sorted(layout_sigs),
            key_set_id=chosen["key_set"],
            facts_strategy=chosen["facts_strategy"],
            text_quality=quality,
        )

    # -------------------------------------------------------------- key sets
    @classmethod
    def key_set_for(cls, profile_id: str) -> Dict[str, Any]:
        profile = next((p for p in PROFILES if p["id"] == profile_id), None)
        if not profile:
            return KEY_SETS["KEY-GENERIC"]
        return KEY_SETS.get(profile["key_set"], KEY_SETS["KEY-GENERIC"])

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
        #    begins at the first narrative paragraph after the last prayer unit.
        prayer_anchors = [a for spec in (keyset.get("relief") or {}).values() for a in spec["anchors"]]
        last_prayer = 0
        for anchor in prayer_anchors:
            for match in re.finditer(anchor, text, re.IGNORECASE | re.MULTILINE):
                last_prayer = max(last_prayer, match.end())
        if last_prayer:
            for para in paragraphs:
                if para["start"] <= last_prayer:
                    continue
                if cls._fact_score(para["text"])["score"] < 1.5:
                    continue
                run_end = para["end"]
                for nxt in paragraphs[para["ordinal"]:para["ordinal"] + 11]:
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

        Every candidate is scored on factuality (dates, crime numbers, places,
        action verbs) minus legal-argument markers, then trimmed to a paragraph
        edge.  The winner plus its provenance is returned alongside a compact
        fact sheet.
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

        confidence = 0.45
        if best["anchored"]:
            confidence += 0.3
        if best["strategy"] == "explicit_heading":
            confidence += 0.15
        if fact_sheet["dates"]:
            confidence += 0.06
        if fact_sheet["crime_numbers"] or fact_sheet["offences"]:
            confidence += 0.06
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

    _CRIME_FULL_RE = re.compile(
        r"\b(?:(?:Crime|F\.?I\.?R|FIR)\s*No\.?|C\.?C\.?\s*No\.?|"
        r"R\.?C\.?\s*No\.?|Charge\s+Sheet\s+No\.?)\s*[\d\.\/]+(?:\s*(?:of|/)\s*\d{2,4})?",
        re.IGNORECASE,
    )
    _OFFENCE_RE = re.compile(
        r"\b(?:Sections?|Secs?\.)\s+\d[\dA-Za-z\(\)\s,&]{0,60}?"
        r"(?:read\s+with\s+[\dA-Za-z\(\)\s,&]{0,60})?"
        r"(?:of\s+(?:the\s+)?[A-Z][A-Za-z\.\s,&()\-]{2,70}?"
        r"(?:Act|Code|Sanhita|Adhiniyam|Rules)(?:\s*,?\s*\d{4})?|of\s+the\s+Act)",
        re.IGNORECASE,
    )
    _PLACE_NAME_RE = re.compile(
        r"\b(?:District|Taluk|Tehsil|Village|Police\s+Station|P\.S\.)\s+(?:of\s+)?([A-Z][A-Za-z\.]{2,20})"
        r"|\b([A-Z][A-Za-z\.]{2,20})\s+(?:District|Taluk|Tehsil|Village)\b"
    )
    _AMOUNT_RE = re.compile(r"(?:Rs\.?|₹)\s?\d[\d,]*(?:\.\d+)?(?:\s*(?:lakh|crore))?(?:\s*/\-)?", re.IGNORECASE)

    @classmethod
    def _fact_sheet(cls, facts_text: str) -> Dict[str, Any]:
        """Structured slice of the factual matrix: dates, crime numbers, places,
        offences, custody/arrest statements and monetary amounts."""
        if not facts_text:
            return {"dates": [], "crime_numbers": [], "places": [], "offences": [],
                    "custody": None, "arrest": None, "amounts": []}
        dates = list(dict.fromkeys(cls._DATE_RE.findall(facts_text)))[:12]
        crime_numbers = list(dict.fromkeys(
            re.sub(r"\s+", " ", m.group(0)).strip() for m in cls._CRIME_FULL_RE.finditer(facts_text)))[:8]
        places: List[str] = []
        for m in cls._PLACE_NAME_RE.finditer(facts_text):
            name = (m.group(1) or m.group(2) or "").strip(" .,")
            if name and name not in places:
                places.append(name)
        offences = list(dict.fromkeys(
            re.sub(r"\s+", " ", m.group(0)).strip() for m in cls._OFFENCE_RE.finditer(facts_text)))[:8]
        custody = re.search(r"(?:in\s+custody\s+since|custody\s+for|under\s+detention\s+since|"
                            r"remanded\s+to\s+judicial\s+custody\s+on)[^.]{0,90}", facts_text, re.I)
        arrest = re.search(r"(?:arrested\s+on|surrendered\s+(?:before|on)|apprehended\s+on)[^.]{0,90}",
                           facts_text, re.I)
        amounts = list(dict.fromkeys(
            re.sub(r"\s+", " ", m.group(0)).strip() for m in cls._AMOUNT_RE.finditer(facts_text)))[:5]
        return {
            "dates": dates,
            "crime_numbers": crime_numbers,
            "places": places[:10],
            "offences": offences,
            "custody": re.sub(r"\s+", " ", custody.group(0)).strip() if custody else None,
            "arrest": re.sub(r"\s+", " ", arrest.group(0)).strip() if arrest else None,
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
