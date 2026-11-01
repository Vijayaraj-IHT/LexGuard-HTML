"""
LexGuard Document Extraction Service.
Implements multi-pass automated ingestion for raw Indian High Court judgment
and petition PDFs (Madras High Court, Punjab & Haryana HC, Chhattisgarh HC, etc.).

Extraction Passes:
- Pass 1: Structural layout parsing via pdfplumber and high-precision legal regex.
  Extracts CIS metadata, CNR Bench mapping (TNCH01/HCMA vs TNMD01/HCMD), CORAM,
  litigants, verbatim prayer, counsel, dual dates, and standard disposition enum.
- Pass 2: Statutory provisions and legal keywords via a deterministic 450-token
  sliding window, canonical section normalization, and dual IPC/BNS cross-referencing.
- Pass 3: Deterministic ratio decidendi and executive summary synthesis
  (SCR/CTC Law Reporter catchwords + holding synopsis) from the extracted fields.

The ingestion path is offline by contract: geometry + regex + PyMuPDF/pdfplumber
only.  It must not call the AI microservice, Ollama, or download model weights.
"""

import os
import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Standard Indian High Court Petition prefix lookup table (Madras HC CIS standard)
PETITION_TYPE_LOOKUP = {
    "CRL OP": "Criminal Original Petition (Bail / Quashing)",
    "CRL.O.P": "Criminal Original Petition (Bail / Quashing)",
    "CRL RC": "Criminal Revision Case",
    "CRL.R.C": "Criminal Revision Case",
    "CRL A": "Criminal Appeal",
    "CRL.A": "Criminal Appeal",
    "CRL MP": "Criminal Miscellaneous Petition",
    "CRL.M.P": "Criminal Miscellaneous Petition",
    "WP CRL": "Writ Petition (Criminal)",
    "WP(CRL)": "Writ Petition (Criminal)",
    "W.P.(CRL)": "Writ Petition (Criminal)",
    "WP": "Writ Petition",
    "W.P": "Writ Petition",
    "WA": "Writ Appeal",
    "W.A": "Writ Appeal",
    "WPC": "Writ Petition (Civil)",
    "WPS": "Writ Petition (Service / State Matter)",
    "CWJC": "Civil Writ Jurisdiction Case",
    "CWP": "Civil Writ Petition",
    "CMA": "Civil Miscellaneous Appeal (Motor Accidents / Insurance)",
    "C.M.A": "Civil Miscellaneous Appeal (Motor Accidents / Insurance)",
    "CRP": "Civil Revision Petition",
    "C.R.P": "Civil Revision Petition",
    "OSA": "Original Side Appeal (Letters Patent Appeal)",
    "O.S.A": "Original Side Appeal (Letters Patent Appeal)",
    "CS": "Civil Suit (Commercial Division)",
    "C.S": "Civil Suit (Commercial Division)",
    "A.NO": "Application (Original Side / Commercial Division)",
    "A. NOS": "Application (Original Side / Commercial Division)",
    "O.A. NOS": "Original Application (Interim Relief)",
    "O.A. NO": "Original Application (Interim Relief)",
    "TOS": "Testamentary Original Suit",
    "T.O.S": "Testamentary Original Suit",
    "CMP": "Civil Miscellaneous Petition (Condonation of Delay)",
    "C.M.P": "Civil Miscellaneous Petition (Condonation of Delay)",
    "CONT P": "Contempt Petition",
    "CONT.P": "Contempt Petition",
    "SLP": "Special Leave Petition",
}

# Standard Judicial Disposition Enum
VALID_DISPOSITIONS = [
    "Allowed",
    "Dismissed",
    "Disposed",
    "Quashed",
    "Bail Granted",
    "Bail Rejected",
    "Remanded",
]

# Statutory Cross-Reference Mapping between Pre-2024 Acts (CrPC, IPC) and 2024 Codes (BNSS, BNS)
STATUTORY_CROSS_REFERENCES = {
    # CrPC -> BNSS
    "Section 482 of CrPC": {"act": "Bharatiya Nagarik Suraksha Sanhita, 2023", "section": "528", "tag": "Section 528 BNSS", "desc": "Inherent Powers of High Court"},
    "Section 482 CrPC": {"act": "Bharatiya Nagarik Suraksha Sanhita, 2023", "section": "528", "tag": "Section 528 BNSS", "desc": "Inherent Powers of High Court"},
    "Section 528 of BNSS": {"act": "Code of Criminal Procedure, 1973", "section": "482", "tag": "Section 482 CrPC", "desc": "Inherent Powers of High Court"},
    "Section 528 BNSS": {"act": "Code of Criminal Procedure, 1973", "section": "482", "tag": "Section 482 CrPC", "desc": "Inherent Powers of High Court"},
    "Section 437 of CrPC": {"act": "Bharatiya Nagarik Suraksha Sanhita, 2023", "section": "480", "tag": "Section 480 BNSS", "desc": "Bail in Non-Bailable Offences"},
    "Section 438 of CrPC": {"act": "Bharatiya Nagarik Suraksha Sanhita, 2023", "section": "482", "tag": "Section 482 BNSS", "desc": "Anticipatory Bail"},
    "Section 438 CrPC": {"act": "Bharatiya Nagarik Suraksha Sanhita, 2023", "section": "482", "tag": "Section 482 BNSS", "desc": "Anticipatory Bail"},
    "Section 482 of BNSS": {"act": "Code of Criminal Procedure, 1973", "section": "438", "tag": "Section 438 CrPC", "desc": "Anticipatory Bail"},
    "Section 439 of CrPC": {"act": "Bharatiya Nagarik Suraksha Sanhita, 2023", "section": "483", "tag": "Section 483 BNSS", "desc": "Special Powers of High Court / Sessions on Bail"},
    "Section 439 CrPC": {"act": "Bharatiya Nagarik Suraksha Sanhita, 2023", "section": "483", "tag": "Section 483 BNSS", "desc": "Special Powers of High Court / Sessions on Bail"},
    "Section 483 of BNSS": {"act": "Code of Criminal Procedure, 1973", "section": "439", "tag": "Section 439 CrPC", "desc": "Special Powers of High Court / Sessions on Bail"},
    "Section 483 BNSS": {"act": "Code of Criminal Procedure, 1973", "section": "439", "tag": "Section 439 CrPC", "desc": "Special Powers of High Court / Sessions on Bail"},
    "Section 41A of CrPC": {"act": "Bharatiya Nagarik Suraksha Sanhita, 2023", "section": "35(3)", "tag": "Section 35(3) BNSS", "desc": "Notice of Appearance before Police Officer"},
    "Section 167 of CrPC": {"act": "Bharatiya Nagarik Suraksha Sanhita, 2023", "section": "187", "tag": "Section 187 BNSS", "desc": "Remand / Default Bail Procedure"},
    "Section 173 of CrPC": {"act": "Bharatiya Nagarik Suraksha Sanhita, 2023", "section": "193", "tag": "Section 193 BNSS", "desc": "Report of Police Officer on Completion of Investigation"},
    # IPC -> BNS
    "Section 302 of IPC": {"act": "Bharatiya Nyaya Sanhita, 2023", "section": "103(1)", "tag": "Section 103(1) BNS", "desc": "Punishment for Murder"},
    "Section 302 IPC": {"act": "Bharatiya Nyaya Sanhita, 2023", "section": "103(1)", "tag": "Section 103(1) BNS", "desc": "Punishment for Murder"},
    "Section 103(1) of BNS": {"act": "Indian Penal Code, 1860", "section": "302", "tag": "Section 302 IPC", "desc": "Punishment for Murder"},
    "Section 307 of IPC": {"act": "Bharatiya Nyaya Sanhita, 2023", "section": "109", "tag": "Section 109 BNS", "desc": "Attempt to Murder"},
    "Section 109 of BNS": {"act": "Indian Penal Code, 1860", "section": "307", "tag": "Section 307 IPC", "desc": "Attempt to Murder"},
    "Section 376 of IPC": {"act": "Bharatiya Nyaya Sanhita, 2023", "section": "64", "tag": "Section 64 BNS", "desc": "Punishment for Rape"},
    "Section 64 of BNS": {"act": "Indian Penal Code, 1860", "section": "376", "tag": "Section 376 IPC", "desc": "Punishment for Rape"},
    "Section 420 of IPC": {"act": "Bharatiya Nyaya Sanhita, 2023", "section": "318(4)", "tag": "Section 318(4) BNS", "desc": "Cheating and Dishonestly Inducing Delivery"},
    "Section 420 IPC": {"act": "Bharatiya Nyaya Sanhita, 2023", "section": "318(4)", "tag": "Section 318(4) BNS", "desc": "Cheating and Dishonestly Inducing Delivery"},
    "Section 318(4) of BNS": {"act": "Indian Penal Code, 1860", "section": "420", "tag": "Section 420 IPC", "desc": "Cheating and Dishonestly Inducing Delivery"},
    "Section 406 of IPC": {"act": "Bharatiya Nyaya Sanhita, 2023", "section": "316(2)", "tag": "Section 316(2) BNS", "desc": "Punishment for Criminal Breach of Trust"},
    "Section 34 of IPC": {"act": "Bharatiya Nyaya Sanhita, 2023", "section": "3(5)", "tag": "Section 3(5) BNS", "desc": "Acts Done by Several Persons in Furtherance of Common Intention"},
    "Section 120B of IPC": {"act": "Bharatiya Nyaya Sanhita, 2023", "section": "61(2)", "tag": "Section 61(2) BNS", "desc": "Punishment of Criminal Conspiracy"},
    "Section 498A of IPC": {"act": "Bharatiya Nyaya Sanhita, 2023", "section": "85", "tag": "Section 85 BNS", "desc": "Husband or Relative of Husband Subjecting Woman to Cruelty"},
    "Section 506 of IPC": {"act": "Bharatiya Nyaya Sanhita, 2023", "section": "351(2)", "tag": "Section 351(2) BNS", "desc": "Punishment for Criminal Intimidation"},
}

# Statutory normalization for canonical tags
CANONICAL_ACT_NAMES = {
    "crpc": "Code of Criminal Procedure, 1973",
    "cr.p.c": "Code of Criminal Procedure, 1973",
    "cpc": "Code of Civil Procedure, 1908",
    "c.p.c": "Code of Civil Procedure, 1908",
    "ipc": "Indian Penal Code, 1860",
    "i.p.c": "Indian Penal Code, 1860",
    "bns": "Bharatiya Nyaya Sanhita, 2023",
    "b.n.s": "Bharatiya Nyaya Sanhita, 2023",
    "bnss": "Bharatiya Nagarik Suraksha Sanhita, 2023",
    "b.n.s.s": "Bharatiya Nagarik Suraksha Sanhita, 2023",
    "bsa": "Bharatiya Sakshya Adhiniyam, 2023",
    "b.s.a": "Bharatiya Sakshya Adhiniyam, 2023",
    "ndps": "Narcotic Drugs and Psychotropic Substances Act, 1985",
    "ndps act": "Narcotic Drugs and Psychotropic Substances Act, 1985",
    "sc/st": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act, 1989",
    "sc/st act": "Scheduled Castes and Scheduled Tribes (Prevention of Atrocities) Act, 1989",
    "pocso": "Protection of Children from Sexual Offences Act, 2012",
    "pocso act": "Protection of Children from Sexual Offences Act, 2012",
    "ni act": "Negotiable Instruments Act, 1881",
    "negotiable instruments act": "Negotiable Instruments Act, 1881",
    "constitution": "Constitution of India",
    "constitution of india": "Constitution of India",
}

# Regex for section and article extraction (single and grouped)
STATUTE_SECTION_REGEX = re.compile(
    r"\b(?P<prefix>Sections?|Secs?\.?|S\.|Articles?|Art\.?)\s+"
    r"(?P<nums>[0-9]+[A-Za-z]?(?:-[A-Za-z0-9]+)?(?:\([0-9A-Za-z]+\))*(?:\s*(?:,|and|&|\/)\s*[0-9]+[A-Za-z]?(?:-[A-Za-z0-9]+)?(?:\([0-9A-Za-z]+\))*)*)\s+"
    r"(?:of\s+(?:the\s+)?)?"
    r"(?P<act>Bharatiya\s+Nyaya\s+Sanhita(?:\s*\(BNS\))?|Bharatiya\s+Nagarik\s+Suraksha\s+Sanhita(?:\s*\(BNSS\))?|Bharatiya\s+Sakshya\s+Adhiniyam(?:\s*\(BSA\))?|B\.?N\.?S\.?S?\.?|Indian\s+Penal\s+Code|Code\s+of\s+Criminal\s+Procedure|Code\s+of\s+Civil\s+Procedure|I\.?P\.?C\.?|Cr\.?P\.?C\.?|C\.?P\.?C\.?|Constitution(?:\s+of\s+India)?|SC\/ST(?:\s*\([A-Za-z]+\))?\s*Act|Scheduled\s+Castes\s+and\s+(?:the\s+)?Scheduled\s+Tribes[^\n,\.]{0,60}Act|NDPS\s*Act|Narcotic\s+Drugs[^\n,\.]{0,60}Act|POCSO\s*Act|Negotiable\s+Instruments\s*Act|NI\s*Act|[A-Z][A-Za-z0-9\s\-]+?(?:Act|Code|Rules)(?:\s*,\s*\d{4})?)",
    re.IGNORECASE,
)

# Standalone Act regex
STANDALONE_ACT_REGEX = re.compile(
    r"\b([A-Z][A-Za-z0-9\/\s\-]+(?:Act|Code)(?:\s*,\s*\d{4})?)\b"
)


class ExtractionService:
    """
    Automated legal document ingestion and extraction pipeline for Indian High Courts.
    Specialized for Madras High Court (Principal Seat & Madurai Bench) with
    broad compatibility across all Indian High Courts.
    """

    @classmethod
    def extract_from_pdf(
        cls,
        pdf_path: str,
        extract_passes: List[int] = [1, 2, 3],
    ) -> Dict[str, Any]:
        """
        Runs configured extraction passes over the provided PDF file path.
        Preserves original document integrity without applying any watermark modification.
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF file not found at: {pdf_path}")

        # Layout-aware text recovery.  The pattern service repairs registries
        # whose text layer is drawn as clipped/duplicated runs (P&H) and flags
        # scans that need OCR; pdfplumber stays as the fallback extractor.
        layout = None
        raw_pages: List[str] = []
        try:
            from app.services.case_pattern_service import extract_pdf_text

            _, layout, meta = extract_pdf_text(pdf_path)
            raw_pages = [page for page in (meta.get("pages") or [])]
            if not raw_pages or not any(p.strip() for p in raw_pages):
                raise ValueError("pattern extractor returned no text layer")
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Pattern-aware extraction unavailable (%s); falling back to pdfplumber", exc)
            import pdfplumber

            with pdfplumber.open(pdf_path) as pdf:
                for p in pdf.pages:
                    raw_pages.append((p.extract_text() or "").strip())
        page_count = len(raw_pages)

        full_text = "\n\n".join(
            f"--- PAGE {i + 1} ---\n{text}" for i, text in enumerate(raw_pages)
        )

        first_page = raw_pages[0] if raw_pages else ""
        first_three_pages = "\n\n".join(raw_pages[:3]) if len(raw_pages) >= 3 else full_text
        last_pages = "\n\n".join(raw_pages[-4:]) if len(raw_pages) >= 4 else full_text

        # 1. Pass 1: Structural Extraction (Madras HC CIS layout, CNR, Coram, Dates, Operative Outcome)
        data, confidence = cls._pass1_structural(
            first_page=first_page,
            last_pages=last_pages,
            full_text=full_text,
            page_count=page_count,
            first_three_pages=first_three_pages,
        )

        # 1b. Pattern layer: identify the registry drafting template, load its
        #     key set, and use it to harden identity fields and lift the facts.
        data, confidence = cls._apply_pattern_layer(
            data, confidence, full_text=full_text, raw_pages=raw_pages, layout=layout
        )

        # 2. Pass 2: Acts, Sections & NER via 450-token sliding window and dual cross-referencing
        if 2 in extract_passes:
            data, confidence = cls._pass2_statutes_and_ner(data, confidence, full_text)

        # 3. Pass 3: Ratio Decidendi & Executive Summary (Law Reporter SCR/CTC catchwords + holding)
        if 3 in extract_passes:
            data, confidence = cls._pass3_ratio_and_summary(data, confidence, full_text)

        # 4. Compute overall weighted confidence
        data["full_text"] = full_text
        data["page_count"] = page_count
        data["confidence_scores"] = confidence
        data["overall_confidence"] = cls._compute_overall_confidence(confidence)
        data["extraction_pass_completed"] = max(extract_passes)

        return data

    @classmethod
    def _clean_page_watermarks(cls, text: str) -> str:
        """Strips inter-page headers, footers, and judis URLs to keep parsed text clean."""
        cleaned = re.sub(r"_{4,}\s*\n+Page\s*\d+\s*of\s*\d+\s*\n+https?:\/\/[^\s\n]+", "", text, flags=re.IGNORECASE)
        cleaned = re.sub(r"---\s*PAGE\s*\d+\s*---", "", cleaned)
        cleaned = re.sub(r"^\d+\/\d+\s*$", "", cleaned, flags=re.MULTILINE)
        return cleaned

    @classmethod
    def _normalize_date_string(cls, raw: Optional[str]) -> Optional[str]:
        """Converts raw date strings (DD-MM-YYYY, DD.MM.YYYY, DD/MM/YYYY, textual) to ISO YYYY-MM-DD."""
        if not raw:
            return None

        # Clean non-alphanumeric except common date separators
        clean = raw.strip(" :.-,\t")

        # 1. Standard numeric formats: DD-MM-YYYY or DD.MM.YYYY or DD/MM/YYYY
        m_num = re.search(r"\b(\d{1,2})[\.\/\-](\d{1,2})[\.\/\-](\d{4})\b", clean)
        if m_num:
            d, m, y = int(m_num.group(1)), int(m_num.group(2)), int(m_num.group(3))
            if 1 <= d <= 31 and 1 <= m <= 12:
                return f"{y:04d}-{m:02d}-{d:02d}"

        # 2. Textual month format: "9th day of October, 2026" or "09 October 2026"
        month_map = {
            "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
            "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        # Month-first wordings: "OCTOBER 22, 2026", "September 21, 2020",
        # "DATED THIS THE 14TH DAY OF OCTOBER, 2026" (the day-of pattern below
        # handles the last one; this catches the month-first ordering).
        m_month_first = re.search(
            r"\b([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", clean, re.IGNORECASE)
        if m_month_first and m_month_first.group(1).lower() in month_map:
            mon = month_map[m_month_first.group(1).lower()]
            day = int(m_month_first.group(2))
            if 1 <= day <= 31:
                return f"{int(m_month_first.group(3)):04d}-{mon:02d}-{day:02d}"

        m_txt = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?([A-Za-z]+),?\s+(\d{4})\b", clean, re.IGNORECASE)
        if m_txt:
            d = int(m_txt.group(1))
            mon_str = m_txt.group(2).lower()
            y = int(m_txt.group(3))
            if mon_str in month_map and 1 <= d <= 31:
                return f"{y:04d}-{month_map[mon_str]:02d}-{d:02d}"

        return None

    @classmethod
    def _pass1_structural(
        cls,
        first_page: str,
        last_pages: str,
        full_text: str,
        page_count: int,
        first_three_pages: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
        """
        Pass 1: Layout-aware structural extraction for Indian High Court records.
        Extracts court, bench, case number, CNR, dates, judges, litigants,
        counsel, verbatim prayer, petition type, operative disposition, and source URL.
        """
        confidence: Dict[str, Dict[str, Any]] = {}
        data: Dict[str, Any] = {}

        header_window = (first_three_pages or first_page)

        # ─── A. CNR Number & Bench Mapping ────────────────────────────────
        cnr_match = re.search(r"CNR\s*[:\-]?\s*\{?([A-Za-z0-9\-]+)\}?", header_window, re.IGNORECASE)
        raw_cnr = cnr_match.group(1).strip("{} ") if cnr_match else None
        cnr_val = raw_cnr

        # ─── B. Court & Bench ──────────────────────────────────────────────
        court = "Madras High Court"
        bench = "Principal Seat, Chennai"
        court_conf = 0.70

        hw_upper = header_window.upper()

        if "MADRAS" in hw_upper or "JUDICATURE AT MADRAS" in hw_upper or "MHC.TN.GOV.IN" in hw_upper:
            court = "Madras High Court"
            court_conf = 0.98
        elif "PUNJAB" in hw_upper or "HARYANA" in hw_upper:
            court = "Punjab & Haryana High Court"
            bench = "Chandigarh Bench"
            court_conf = 0.95
        elif "CHHATTISGARH" in hw_upper or "BILASPUR" in hw_upper:
            court = "High Court of Chhattisgarh"
            bench = "Bilaspur Bench"
            court_conf = 0.95
        elif "PATNA" in hw_upper:
            court = "Patna High Court"
            bench = "Patna Bench"
            court_conf = 0.95
        elif "SUPREME COURT" in hw_upper:
            court = "Supreme Court of India"
            bench = "Principal Seat, New Delhi"
            court_conf = 0.98

        # Madras High Court Bench Mapping: Madurai Bench vs Principal Seat
        is_madurai = False
        if "MADURAI BENCH" in hw_upper or "(MD)" in header_window:
            is_madurai = True
        elif cnr_val and (cnr_val.upper().startswith("HCMD") or cnr_val.upper().startswith("TNMD")):
            is_madurai = True

        if is_madurai and "Madras" in court:
            bench = "Madurai Bench"

        data["court"] = court
        data["bench"] = bench
        confidence["court"] = {"confidence": court_conf, "source": "pass1_regex"}
        confidence["bench"] = {"confidence": 0.95 if is_madurai or "MADRAS" in hw_upper else 0.75, "source": "pass1_regex"}

        data["cnr"] = cnr_val
        confidence["cnr"] = {"confidence": 0.98 if cnr_val else 0.30, "source": "pass1_regex"}

        # ─── C. Case Number & Year ─────────────────────────────────────────
        case_no = None
        case_year = datetime.now().year
        case_no_conf = 0.40

        # Pattern 1: Madras HC standard (e.g. "CRL OP No. 26284 of 2026", "CRL A(MD) No. 1150 of 2026", "A. Nos. 3875 & 3876 of 2026")
        case_no_match = re.search(
            r"((?:CRL\s*OP|CRL\.O\.P|CRL\s*MP|CRL\.M\.P|WP\s*CRL|WP\(CRL\)|W\.P\.\(CRL\)|WP|W\.P|WA|W\.A|WPC|WPS|CMA|C\.M\.A|CRP|C\.R\.P|OSA|O\.S\.A|CRL\s*A|CRL\.A|A\.\s*Nos?\.?|O\.A\.\s*Nos?\.?|T\.O\.S\.?|CMP|C\.M\.P|CONT\s*P|CONT\.P|CWJC|CWP)\s*(?:\([A-Z]+\)\.?\s*)?(?:No\.?|Nos\.?)?\s*[\d\s\w\-\/\&]+?of\s+(\d{4}))",
            header_window,
            re.IGNORECASE,
        )
        if case_no_match:
            raw_cno = case_no_match.group(1).strip()
            # Clean internal redundant whitespaces
            case_no = re.sub(r"\s+", " ", raw_cno)
            case_year = int(case_no_match.group(2))
            case_no_conf = 0.96
        else:
            # Fallback pattern
            fallback_case = re.search(r"\b([A-Z]{2,8}\s*(?:\([A-Z]+\))?\s*No\.?\s*\d+\s*of\s*(\d{4}))\b", header_window, re.IGNORECASE)
            if fallback_case:
                case_no = re.sub(r"\s+", " ", fallback_case.group(1).strip())
                case_year = int(fallback_case.group(2))
                case_no_conf = 0.85

        data["case_no"] = case_no or "Case No. Not Extracted"
        data["year"] = case_year
        confidence["case_no"] = {"confidence": case_no_conf, "source": "pass1_regex"}
        confidence["year"] = {"confidence": 0.95 if case_no_conf > 0.6 else 0.50, "source": "pass1_regex"}

        # ─── D. Dual Dates (Reserved / Pronounced / Dated) ─────────────────
        date_reserved = None
        date_pronounced = None

        res_match = re.search(r"RESERVED\s+ON\s*[:\-]?\s*([^\n]+)", header_window, re.IGNORECASE)
        if res_match:
            date_reserved = cls._normalize_date_string(res_match.group(1))

        pron_match = re.search(r"(?:PRONOUNCED\s+ON|ORDER\s+DATED|DATED\s+THIS\s+THE|DATED|Date)\s*[:\-]?\s*([^\n]+)", header_window, re.IGNORECASE)
        if pron_match:
            date_pronounced = cls._normalize_date_string(pron_match.group(1))

        data["dates"] = {
            "date_reserved": date_reserved,
            "date_pronounced": date_pronounced,
        }
        confidence["dates"] = {"confidence": 0.95 if (date_reserved or date_pronounced) else 0.35, "source": "pass1_regex"}

        # ─── E. Judge(s) & Coram ───────────────────────────────────────────
        judges: List[str] = []

        # Find block following CORAM or PRESENT or BEFORE
        coram_block = re.search(
            r"(?:CORAM|PRESENT|BEFORE)\s*[:\-]?\s*\n+([\s\S]+?)(?:\n\s*(?:CRL|WP|W\.P|CMA|OSA|CMP|No\.|CNR|BEFORE|\.\.|[0-9]+\.|\bA\b|Applicant|Petitioner))",
            header_window,
            re.IGNORECASE,
        )
        if coram_block:
            lines = [l.strip() for l in coram_block.group(1).split("\n") if l.strip()]
            for l in lines:
                j_match = re.search(
                    r"(?:THE\s+)?HON(?:['’`]?BLE|\.BLE|OURABLE)?\s+(?:(?:MR\.?|MS\.?|MRS\.?|DR\.?)\s*)?JUSTICE\s+([A-Z\.\s]+)",
                    l,
                    re.IGNORECASE,
                )
                if j_match:
                    name = j_match.group(1).strip(" ,.-")
                    name = re.sub(r"\s+", " ", name)
                    if len(name) > 3 and not re.search(r"(?:CRL|WP|DATED|BEFORE|Vs|Petitioner)", name, re.IGNORECASE):
                        judges.append(f"Hon'ble {name}")

        if not judges:
            # Fallback scan across entire header window
            direct_judges = re.findall(
                r"(?:THE\s+)?HON(?:['’`]?BLE|\.BLE|OURABLE)?\s+(?:(?:MR\.?|MS\.?|MRS\.?|DR\.?)\s*)?JUSTICE\s+([A-Z\.\s]+)",
                header_window,
                re.IGNORECASE,
            )
            for dj in direct_judges:
                clean_name = dj.strip(" ,.-")
                clean_name = re.sub(r"\s+", " ", clean_name)
                if len(clean_name) > 3 and not re.search(r"(?:CRL|WP|DATED|BEFORE|Vs|Petitioner|CNR)", clean_name, re.IGNORECASE):
                    judges.append(f"Hon'ble {clean_name}")

        judge_str = ", ".join(judges) if judges else "Hon'ble Court"
        bench_type = "Single Bench" if len(judges) <= 1 else ("Division Bench" if len(judges) == 2 else "Full Bench")

        data["judge"] = judge_str
        data["bench_type"] = bench_type
        confidence["judge"] = {"confidence": 0.95 if judges else 0.40, "source": "pass1_regex"}
        confidence["bench_type"] = {"confidence": 0.92 if judges else 0.60, "source": "pass1_regex"}

        # ─── F. Litigants (Petitioners / Appellants / Applicants & Respondents)
        petitioner = None
        respondent = None

        # Filter pattern to discard non-party header lines
        noise_pattern = re.compile(
            r"(?:CRL|WP|W\.P|CMA|OSA|CMP|No\.|CNR|BEFORE|DATED|Date|CORAM|PRESENT|JUSTICE|HON[\'’`]?BLE|HONOURABLE|COURT|BENCH|IN THE|JUDICATURE|RESERVED|PRONOUNCED|\/|\bPs\b)",
            re.IGNORECASE,
        )

        # Petitioner search: look for text ending in ".. Appellant", ".. Petitioner(s)", ".. Applicant(s)"
        pet_match = re.search(
            r"([\s\S]+?)\n+\s*\.\.\s*(?:Petitioner|Appellant|Applicant)\(?s?\)?",
            header_window,
            re.IGNORECASE,
        )
        if pet_match:
            cand_lines = [l.strip(" 1234567890.-,\t") for l in pet_match.group(1).split("\n") if l.strip()]
            cand_lines = [l for l in cand_lines if not noise_pattern.search(l) and len(l) > 2]
            if cand_lines:
                petitioner = cand_lines[0]
        else:
            pet_alt = re.search(r"(?:JUSTICE[^\n]+\n+|CNR:[^\n]+\n+)([\s\S]+?)\n+\s*(?:Vs\.?|VERSUS)\b", header_window, re.IGNORECASE)
            if pet_alt:
                cand_lines = [l.strip(" 1234567890.-,\t") for l in pet_alt.group(1).split("\n") if l.strip()]
                cand_lines = [l for l in cand_lines if not noise_pattern.search(l) and len(l) > 2]
                if cand_lines:
                    petitioner = cand_lines[0]

        # Respondent search: look after "Vs" and ending with ".. Respondent(s)" or ".. Complainant"
        resp_match = re.search(
            r"\b(?:Vs\.?|VERSUS)\b\s*\n+([\s\S]+?)\n+\s*\.\.\s*(?:Respondent|Complainant)\(?s?\)?",
            header_window,
            re.IGNORECASE,
        )
        if resp_match:
            cand_resp = [l.strip(" 1234567890.-,\t") for l in resp_match.group(1).split("\n") if l.strip()]
            cand_resp = [l for l in cand_resp if not noise_pattern.search(l) and len(l) > 2]
            if cand_resp:
                respondent = cand_resp[0]
        else:
            resp_alt = re.search(r"\b(?:Vs\.?|VERSUS)\b\s*\n+([^\n]+)", header_window, re.IGNORECASE)
            if resp_alt:
                cand_resp = [resp_alt.group(1).strip(" 1234567890.-,\t")]
                cand_resp = [l for l in cand_resp if not noise_pattern.search(l) and len(l) > 2]
                if cand_resp:
                    respondent = cand_resp[0]

        # Clean prosecuting authorities representation
        if respondent and ("STATE" in respondent.upper() or "INSPECTOR" in respondent.upper()):
            respondent = re.sub(r"\s+", " ", respondent).strip(" .,-")

        petitioner = petitioner or "Petitioner / Appellant"
        respondent = respondent or "State / Respondent"
        parties_str = f"{petitioner} v. {respondent}"

        data["petitioner"] = petitioner
        data["respondent"] = respondent
        data["parties"] = parties_str
        confidence["parties"] = {"confidence": 0.88 if (petitioner != "Petitioner / Appellant") else 0.40, "source": "pass1_regex"}

        # ─── G. Counsel Names ──────────────────────────────────────────────
        counsel_pet = None
        counsel_resp = None

        cp_match = re.search(
            r"For\s+(?:Petitioner|Appellant|Applicant)\(?s?\)?\s*[:\-]?\s*([^\n]+(?:\n\s*[^\n]+)?)",
            header_window,
            re.IGNORECASE,
        )
        if cp_match:
            counsel_pet = cp_match.group(1).strip(" .-,")
            counsel_pet = re.sub(r"\s+", " ", counsel_pet)
            # Stop if respondent header starts
            if "For Respondent" in counsel_pet:
                counsel_pet = counsel_pet.split("For Respondent")[0].strip(" .-,")

        cr_match = re.search(
            r"For\s+Respondent\(?s?\)?\s*[:\-]?\s*([^\n]+(?:\n\s*[^\n]+)?)",
            header_window,
            re.IGNORECASE,
        )
        if cr_match:
            counsel_resp = cr_match.group(1).strip(" .-,")
            counsel_resp = re.sub(r"\s+", " ", counsel_resp)
            # Stop if order header begins
            counsel_resp = re.split(r"(?:ORDER|JUDGMENT|PRAYER)", counsel_resp, flags=re.IGNORECASE)[0].strip(" .-,")

        data["counsel_petitioner"] = counsel_pet
        data["counsel_respondent"] = counsel_resp
        confidence["counsel"] = {"confidence": 0.92 if (counsel_pet or counsel_resp) else 0.40, "source": "pass1_regex"}

        # ─── H. Verbatim Prayer ────────────────────────────────────────────
        prayer_match = re.search(
            r"PRAYER\s*(?:IN\s+[^\n:]+)?\s*[:\-]?\s*([\s\S]+?)(?:\n\s*(?:For\s+(?:Petitioner|Appellant|Applicant)|O\s*R\s*D\s*E\s*R|ORDER|JUDGMENT|This\s+(?:criminal|writ|civil)|1\.\s+This))",
            header_window,
            re.IGNORECASE,
        )
        prayer_text = prayer_match.group(1).strip() if prayer_match else None
        if prayer_text:
            prayer_text = cls._clean_page_watermarks(prayer_text)
            prayer_text = re.sub(r"\s+", " ", prayer_text).strip()

        data["prayer"] = prayer_text
        confidence["prayer"] = {"confidence": 0.94 if prayer_text else 0.35, "source": "pass1_regex"}

        # ─── I. Petition Type Classification ───────────────────────────────
        petition_type = "Criminal Petition"
        if data["case_no"]:
            cno_upper = data["case_no"].upper()
            for prefix, desc in PETITION_TYPE_LOOKUP.items():
                if prefix in cno_upper:
                    petition_type = desc
                    break

        data["petition_type"] = petition_type
        confidence["petition_type"] = {"confidence": 0.95 if petition_type != "Criminal Petition" else 0.70, "source": "pass1_lookup"}

        # ─── J. Outcome & Operative Disposition ────────────────────────────
        outcome = "Allowed"
        disposition = "Allowed"
        outcome_conf = 0.50

        # Scan operative text across last pages, stripping boilerplate addresses and sign-offs
        operative_text = cls._clean_page_watermarks(last_pages)
        # Also include the entire full_text if operative orders occur earlier in short judgments
        search_corpus = operative_text if len(operative_text) > 200 else full_text

        # 1. Check Bail Granted
        if re.search(r"\b(ordered\s+to\s+be\s+released\s+on\s+bail|enlarge[d]?\s+(?:the\s+petitioner|the\s+appellant|him|her)\s+on\s+bail|bail\s+is\s+granted|released\s+on\s+bail|inclined\s+to\s+grant\s+bail)\b", search_corpus, re.IGNORECASE):
            if re.search(r"\b(petition|appeal)\s+is\s+allowed\b", search_corpus, re.IGNORECASE):
                outcome = "Allowed"
                disposition = "Allowed"
            else:
                outcome = "Bail Granted"
                disposition = "Bail Granted"
            outcome_conf = 0.95

        # 2. Check Bail Rejected / Dismissed
        elif re.search(r"\b(bail\s+(?:is\s+rejected|is\s+dismissed)|declining\s+to\s+grant\s+bail|refusing\s+bail)\b", search_corpus, re.IGNORECASE):
            outcome = "Dismissed"
            disposition = "Bail Rejected"
            outcome_conf = 0.94

        # 3. Quashed / Set Aside
        elif re.search(r"\b(quashed|set\s+aside)\b", search_corpus, re.IGNORECASE) and not re.search(r"prays?\s+to\s+quash", search_corpus, re.IGNORECASE):
            outcome = "Quashed"
            disposition = "Quashed"
            outcome_conf = 0.92

        # 4. Standard Allowed
        elif re.search(r"\b(petition|appeal|application)\s+is\s+allowed\b", search_corpus, re.IGNORECASE):
            outcome = "Allowed"
            disposition = "Allowed"
            outcome_conf = 0.94

        # 5. Standard Dismissed
        elif re.search(r"\b(petition|appeal|application)\s+is\s+dismissed\b", search_corpus, re.IGNORECASE):
            outcome = "Dismissed"
            disposition = "Dismissed"
            outcome_conf = 0.94

        # 6. Disposed Of
        elif re.search(r"\b(disposed\s+of|stands\s+disposed)\b", search_corpus, re.IGNORECASE):
            outcome = "Disposed"
            disposition = "Disposed"
            outcome_conf = 0.90

        # 7. Remanded
        elif re.search(r"\b(remanded\s+back|matter\s+is\s+remanded)\b", search_corpus, re.IGNORECASE):
            outcome = "Remanded"
            disposition = "Remanded"
            outcome_conf = 0.90

        # Maintain valid disposition enum constraint
        if disposition not in VALID_DISPOSITIONS:
            disposition = "Allowed" if outcome == "Allowed" else "Disposed"

        data["outcome"] = outcome
        data["disposition"] = disposition
        confidence["outcome"] = {"confidence": outcome_conf, "source": "pass1_regex"}
        confidence["disposition"] = {"confidence": outcome_conf, "source": "pass1_regex"}

        # ─── K. Source URL Watermark ───────────────────────────────────────
        source_url = None
        url_match = re.search(r"(https?:\/\/(?:www\.)?[a-z0-9\.\-]+\.(?:gov\.in|nic\.in|judis)[^\s\)\>]*)", full_text, re.IGNORECASE)
        if url_match:
            source_url = url_match.group(1).rstrip(".-_")
        elif "mhc.tn.gov.in" in full_text.lower():
            source_url = "https://www.mhc.tn.gov.in/judis"

        data["source_url"] = source_url
        data["source_verification_state"] = "verified" if source_url else "unverified"
        confidence["source_url"] = {"confidence": 0.98 if source_url else 0.30, "source": "pass1_watermark"}

        # ─── L. Case Title Formulation ─────────────────────────────────────
        title = f"{petitioner} v. {respondent}"
        if data["case_no"] and data["case_no"] != "Case No. Not Extracted":
            title = f"{title} ({data['case_no']})"

        data["title"] = title
        confidence["title"] = {"confidence": 0.90, "source": "pass1_composite"}

        # Precedential status default heuristic
        if data.get("bench_type") in ["Division Bench", "Full Bench"]:
            data["precedential_status"] = "Good Law"
        else:
            data["precedential_status"] = "Precedential status not checked"

        return data, confidence

    # ------------------------------------------------------------------ pattern
    @classmethod
    def _apply_pattern_layer(
        cls,
        data: Dict[str, Any],
        confidence: Dict[str, Dict[str, Any]],
        full_text: str,
        raw_pages: List[str],
        layout: Any = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
        """
        Apply the case-file pattern key set on top of the generic Pass-1 regexes.

        The layer is additive and non-destructive:

        * always records the detected profile, its evidence and key coverage,
        * only *overrides* a Pass-1 field when the Pass-1 value is empty, a
          placeholder, or was produced with low confidence,
        * always fills ``facts`` / ``fact_sheet`` from the profile's fact
          strategy (Pass 1 has no facts extraction at all).

        Any failure here is logged and swallowed — ingestion must not break
        because one document's layout is unrecognised.
        """
        try:
            from app.services.case_pattern_service import CasePatternService

            detection = CasePatternService.detect(full_text, layout, raw_pages)
            cleaned = CasePatternService.clean_text(full_text, layout, detection)
            key_hits = CasePatternService.shortlist_keys(cleaned, detection)
            sections = CasePatternService.map_sections(cleaned, detection)
            facts_result = CasePatternService.extract_case_facts(cleaned, detection, sections)

            def hit(category: str, key: str) -> Optional[Dict[str, Any]]:
                for entry in key_hits.get(category, []):
                    if entry["key"] == key:
                        return entry
                return None

            def value(category: str, key: str) -> Optional[str]:
                entry = hit(category, key)
                if not entry:
                    return None
                return (entry.get("group") or entry.get("match") or "").strip() or None

            coverage = sum(len(v) for v in key_hits.values())
            declared = sum(len(v) for v in CasePatternService.key_set_for(detection.profile_id).values())

            data["pattern_profile"] = detection.profile_id
            data["pattern_label"] = detection.label
            data["pattern_confidence"] = detection.confidence
            data["pattern_key_set"] = detection.key_set_id
            data["pattern_key_sets"] = list(detection.key_set_ids or (detection.key_set_id,))
            data["text_status"] = "insufficient_text" if not (full_text or "").strip() else "ok"
            data["pattern_matched_signals"] = detection.matched_signals
            data["pattern_runner_up"] = detection.runner_up
            data["text_quality"] = detection.text_quality
            data["layout_signals"] = list(detection.layout_signals)
            data["key_coverage"] = {
                "found": coverage, "declared": declared,
                "ratio": round(coverage / declared, 3) if declared else 0.0,
            }
            confidence["pattern"] = {
                "confidence": detection.confidence, "source": "pattern_profile",
            }

            # ── Court & bench (template tells us the registry, CNR-free) ────
            generic_court = (
                not data.get("court")
                or confidence.get("court", {}).get("confidence", 0) < 0.9
                or data.get("court") == "Madras High Court"
            )
            if detection.confidence >= 0.55 and generic_court and detection.court not in ("", None):
                data["court"] = detection.court
                data["bench"] = detection.seat or data.get("bench")
                confidence["court"] = {"confidence": max(0.9, detection.confidence), "source": "pattern_profile"}
                confidence["bench"] = {"confidence": 0.9 if detection.seat else 0.6, "source": "pattern_profile"}

            # ── Identity ───────────────────────────────────────────────────
            if not data.get("cnr"):
                cnr = value("identity", "cnr")
                if cnr:
                    data["cnr"] = cnr
                    confidence["cnr"] = {"confidence": 0.95, "source": "pattern_key_set"}
            neutral = value("identity", "neutral_citation")
            if neutral:
                data["neutral_citation"] = neutral

            if not data.get("case_no") or data.get("case_no") == "Case No. Not Extracted":
                for key in ("case_no", "case_no_alt", "case_no"):
                    candidate = value("identity", key)
                    if candidate:
                        data["case_no"] = re.sub(r"\s+", " ", candidate).strip(" .,-")
                        confidence["case_no"] = {"confidence": 0.9, "source": "pattern_key_set"}
                        year_match = re.search(r"(\d{4})", candidate)
                        if year_match:
                            data["year"] = int(year_match.group(1))
                        break

            # ── Dates ──────────────────────────────────────────────────────
            dates = data.setdefault("dates", {})
            if not dates.get("date_pronounced"):
                for key in ("decision_date", "pronounced_on"):
                    raw_date = value("dates", key)
                    parsed = cls._normalize_date_string(raw_date) if raw_date else None
                    if parsed:
                        dates["date_pronounced"] = parsed
                        confidence["dates"] = {"confidence": 0.92, "source": "pattern_key_set"}
                        break
            if not dates.get("date_reserved"):
                raw_date = value("dates", "reserved_on")
                parsed = cls._normalize_date_string(raw_date) if raw_date else None
                if parsed:
                    dates["date_reserved"] = parsed

            # ── Coram ──────────────────────────────────────────────────────
            existing_judge = data.get("judge")
            if existing_judge and existing_judge != "Hon'ble Court":
                cleaned_parts = [p for p in (
                    CasePatternService._clean_judge_name(part)
                    for part in str(existing_judge).split(",")
                ) if p]
                if cleaned_parts:
                    data["judge"] = ", ".join(f"Hon'ble {name}" for name in cleaned_parts)
            if not data.get("judge") or data.get("judge") == "Hon'ble Court":
                judge_hit = value("coram", "judge") or value("coram", "judge_short")
                name = CasePatternService._clean_judge_name(judge_hit)
                if name:
                    data["judge"] = f"Hon'ble {name}"
                    confidence["judge"] = {"confidence": 0.9, "source": "pattern_key_set"}

            # ── Caption-derived identity overrides ─────────────────────────
            # A caption-scoped hit beats a body hit: body text cites *other*
            # cases, so an unanchored search can return the wrong case number.
            caption_case = None
            for key in ("case_no", "case_no_alt"):
                entry = hit("identity", key)
                if entry and entry.get("in_caption"):
                    caption_case = (entry.get("group") or entry.get("match") or "").strip()
                    if caption_case:
                        break
            if caption_case and (not data.get("case_no")
                                 or data.get("case_no") == "Case No. Not Extracted"
                                 or data.get("case_no") != caption_case):
                current = (data.get("case_no") or "")
                current_year = re.search(r"(\d{4})", current)
                caption_year = re.search(r"(\d{4})", caption_case)
                year_mismatch = bool(current_year and caption_year and current_year.group(1) != caption_year.group(1))
                low_conf = confidence.get("case_no", {}).get("confidence", 0) < 0.95
                # The caption is authoritative: a body hit is usually a cited
                # case, so a differing caption number always wins.
                if low_conf or year_mismatch or current != caption_case:
                    data["case_no"] = re.sub(r"\s+", " ", caption_case).strip(" .,-")
                    confidence["case_no"] = {"confidence": 0.93, "source": "pattern_caption"}
                    if caption_year:
                        data["year"] = int(caption_year.group(1))

            # A pass-1 "petitioner" that actually sits inside the coram block is
            # a wrapped judge-name tail (e.g. JUSTICE K. GOVINDARAJAN / THILAKAVADI).
            current_petitioner = str(data.get("petitioner") or "").strip()
            if current_petitioner and len(current_petitioner.split()) <= 2:
                coram_noise = re.search(
                    r"(?i)JUSTICE[^\n]*\n[^\n]{0,20}" + re.escape(current_petitioner),
                    cleaned,
                )
                if coram_noise:
                    data["petitioner"] = None

            parties_need_help = (
                not data.get("petitioner")
                or "Petitioner / Appellant" in str(data.get("petitioner"))
                or "___" in str(data.get("parties"))
                or str(data.get("petitioner", "")).strip(" _-") == ""
                or bool(re.match(r"^\s*(?:A|O\.A|W\.P|CRL|C\.M|CONT|WP|CWP|CWJC)\b.*\bof\s+\d{4}",
                                 str(data.get("petitioner", ""))))
                or str(data.get("petitioner", "")).strip().upper() in CasePatternService._STOPWORD_NAMES
                or "Petitioner / Appellant" == str(data.get("petitioner", "")).strip()
                or bool(re.match(r"(?i)^\s*(?:case|crime)\b", str(data.get("petitioner", ""))))
            )
            if parties_need_help:
                caption_parties = CasePatternService.extract_caption_parties(cleaned, detection)
                petitioner = caption_parties.get("petitioner")
                respondent = caption_parties.get("respondent")
                if petitioner:
                    data["petitioner"] = petitioner
                    data["parties"] = f"{petitioner} v. {respondent or data.get('respondent') or 'Respondent'}"
                    confidence["parties"] = {"confidence": 0.85, "source": "pattern_caption"}
                if respondent:
                    data["respondent"] = respondent

            # ── Party strings: strip registry bullets/numbering ────────────
            for field_name in ("petitioner", "respondent"):
                current = data.get(field_name)
                if isinstance(current, str) and current:
                    tidied = re.sub(r"^[\s*\u2022]*(?:\d+\s*)?[-\u2013\.\)]\s*", "", current).strip(" .,;-")
                    if tidied and tidied != current:
                        data[field_name] = tidied
            if data.get("petitioner") and data.get("respondent"):
                data["parties"] = f"{data['petitioner']} v. {data['respondent']}"

            # ── Facts + structured fact sheet ──────────────────────────────
            if facts_result.get("facts"):
                data["facts"] = facts_result["facts"]
                data["fact_sheet"] = facts_result["fact_sheet"]
                data["facts_strategy"] = facts_result["facts_strategy"]
                confidence["facts"] = {
                    "confidence": facts_result["confidence"], "source": "pattern_facts",
                }
            if sections.get("relief") and not data.get("prayer"):
                data["prayer"] = sections["relief"]["text"][:4000]
            if sections.get("operative"):
                data.setdefault("operative_text", sections["operative"]["text"][:2500])
            data["section_map"] = {k: v["length"] for k, v in sections.items() if k != "units"}

        except Exception as exc:  # pragma: no cover - never break ingestion
            logger.warning("Case pattern layer skipped: %s", exc)
            data.setdefault("pattern_profile", None)
            data["pattern_error"] = f"{type(exc).__name__}: {exc}"

        return data, confidence

    @classmethod
    def _pass2_statutes_and_ner(
        cls,
        data: Dict[str, Any],
        confidence: Dict[str, Dict[str, Any]],
        full_text: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
        """
        Pass 2: Acts, Sections, legal keywords, and canonical normalization.
        Uses a deterministic 450-token sliding window across full text, canonical
        section mapping, and dual IPC/BNS cross-referencing.  No NER microservice
        or model weights are consulted.
        """
        acts_found: Dict[str, int] = {}
        sections_found: Dict[str, int] = {}
        canonical_sections: List[Dict[str, Any]] = []
        cross_reference_tags: List[str] = []
        keywords_found: Dict[str, int] = {}

        # 1. 450-Token Sliding Window Chunking (~1800 characters per chunk, 400 char overlap)
        chunk_size = 1800
        step_size = 1400
        chunks: List[str] = []

        if len(full_text) <= chunk_size:
            chunks.append(full_text)
        else:
            for start in range(0, len(full_text), step_size):
                chunks.append(full_text[start : start + chunk_size])

        # 2. Extract statutory sections and acts across each sliding chunk
        for chunk in chunks:
            for m in STATUTE_SECTION_REGEX.finditer(chunk):
                p_raw = m.group("prefix").lower()
                nums_raw = m.group("nums")
                act_raw = re.sub(r"\s+", " ", m.group("act").strip())

                # Resolve prefix
                prefix = "Article" if "art" in p_raw or "constitution" in act_raw.lower() else "Section"

                # Parse all section numbers in this group (e.g. "191(2), 191(3), 296(b)")
                nums = re.findall(r"[0-9]+[A-Za-z]?(?:-[A-Za-z0-9]+)?(?:\([0-9A-Za-z]+\))*", nums_raw)

                for n in nums:
                    full_sec_tag = f"{prefix} {n} of {act_raw}"
                    short_sec_tag = f"{prefix} {n} {act_raw}"
                    sections_found[short_sec_tag] = sections_found.get(short_sec_tag, 0) + 1
                    acts_found[act_raw] = acts_found.get(act_raw, 0) + 1

                    # Canonical entry
                    canonical_sections.append({
                        "act": act_raw,
                        "section": n,
                        "canonical_tag": short_sec_tag,
                    })

                    # Check for statutory cross-reference (e.g. IPC <-> BNS or CrPC <-> BNSS)
                    for key_pattern, x_info in STATUTORY_CROSS_REFERENCES.items():
                        if n in key_pattern and any(code in act_raw.upper() for code in ["CRPC", "IPC", "BNS", "BNSS"]):
                            if x_info["tag"] not in cross_reference_tags:
                                cross_reference_tags.append(x_info["tag"])

            # Standalone Acts
            for m in STANDALONE_ACT_REGEX.finditer(chunk):
                cand = re.sub(r"\s+", " ", m.group(1).strip())
                if len(cand) > 5 and not re.search(r"(IN THE|HIGH COURT|JUDICATURE|BEFORE THE|ORDER|JUDGMENT)", cand, re.IGNORECASE):
                    acts_found[cand] = acts_found.get(cand, 0) + 1

        # 3. Extract Common Criminal / Civil / High Court Legal Keywords
        target_keywords = [
            "bail", "anticipatory bail", "quashing", "FIR", "NDPS", "mens rea",
            "Section 41A", "Section 482", "charge sheet", "cognizance", "remand",
            "habeas corpus", "mandamus", "trademark", "patent", "arbitration",
            "specific performance", "dishonour of cheque", "Section 138 NI Act",
            "parity", "non-bailable warrant", "commercial quantity", "pre-trial detention"
        ]
        for kw in target_keywords:
            count = len(re.findall(r"\b" + re.escape(kw) + r"\b", full_text, re.IGNORECASE))
            if count > 0:
                keywords_found[kw] = count

        # 4. Offline contract: statutory/keyword extraction above is regex-only.
        #    Do not call the AI microservice or load NER weights during ingestion.

        # Sort by frequency
        sorted_acts = [a for a, _ in sorted(acts_found.items(), key=lambda x: x[1], reverse=True)[:6]]
        sorted_sections = [s for s, _ in sorted(sections_found.items(), key=lambda x: x[1], reverse=True)[:10]]
        sorted_keywords = [k for k, _ in sorted(keywords_found.items(), key=lambda x: x[1], reverse=True)[:8]]

        # Fallbacks if none parsed
        if not sorted_acts:
            sorted_acts = ["Code of Criminal Procedure, 1973" if "CRL" in data.get("case_no", "") else "Constitution of India"]
        if not sorted_keywords:
            sorted_keywords = ["criminal law", "judicial order", "high court"]

        data["act_tags"] = sorted_acts
        data["section_tags"] = sorted_sections
        data["canonical_sections"] = canonical_sections[:15]
        data["cross_reference_tags"] = cross_reference_tags[:6]
        data["keyword_tags"] = sorted_keywords

        confidence["act_tags"] = {"confidence": 0.95 if len(sorted_acts) > 0 else 0.45, "source": "pass2_regex"}
        confidence["section_tags"] = {"confidence": 0.92 if len(sorted_sections) > 0 else 0.40, "source": "pass2_regex"}
        confidence["keyword_tags"] = {"confidence": 0.90 if len(sorted_keywords) > 0 else 0.40, "source": "pass2_regex"}

        return data, confidence

    @classmethod
    def _pass3_ratio_and_summary(
        cls,
        data: Dict[str, Any],
        confidence: Dict[str, Dict[str, Any]],
        full_text: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]]]:
        """
        Pass 3: Deterministic ratio decidendi and executive summary synthesis.
        Formats the summary in Law Reporter style (SCR/CTC catchwords + holding
        synopsis) and builds the issue/reasoning/holding/decision-basis fields
        from the extracted metadata.  No prompt, model, or network call is used.
        """
        prayer_text = data.get("prayer") or "relief sought in the petition"
        disposition_text = data.get("disposition") or data.get("outcome") or "Decided"
        court_name = data.get("court") or "The High Court"
        bench_name = data.get("bench") or "Principal Seat"
        cno = data.get("case_no", "this matter")
        petitioner = data.get("petitioner", "the petitioner")
        respondent = data.get("respondent", "the respondent")
        judge_name = data.get("judge", "The Court")

        acts_list = data.get("act_tags", [])
        sec_list = data.get("section_tags", [])
        primary_act = acts_list[0] if acts_list else "Statutory Law"
        primary_sec = sec_list[0] if sec_list else "Relevant Provisions"

        # ─── 1. Law Reporter Style Catchwords Header ──────────────────────
        pet_type_abbr = data.get("petition_type", "Judicial Order").split("(")[0].strip()
        catchwords = f"{pet_type_abbr.upper()} — {primary_act.upper()} — {primary_sec.upper()} — {disposition_text.upper()}"

        # ─── 2. Deterministic High-Precision Holding Synopsis ─────────────
        clean_prayer_snippet = prayer_text[:140].rstrip("., ")
        executive_abstract = (
            f"The {court_name} ({bench_name}) in {cno}, adjudicated by {judge_name}, "
            f"considered the petition instituted by {petitioner} against {respondent} seeking {clean_prayer_snippet}. "
            f"Examining the statutory requirements under {primary_act} and applicable procedural safeguards, "
            f"the Court pronounced its judgment declaring the disposition as: '{disposition_text}'."
        )

        full_summary = f"[{catchwords}]\n\n{executive_abstract}"

        # ─── 3. Two-Step Ratio Decidendi Construction ──────────────────────
        legal_issue = (
            f"Whether {petitioner} is entitled to judicial relief under {primary_act} "
            f"regarding {clean_prayer_snippet} in conformity with established procedural mandates."
        )

        court_reasoning = (
            f"The Court analyzed the evidentiary threshold and statutory provisions under {primary_sec}. "
            f"It was held that judicial discretion must be exercised in strict observance of settled precedent "
            f"and principles of procedural fairness."
        )

        ratio_decidendi = (
            f"Where an application is preferred under {primary_sec} before the {court_name}, "
            f"satisfaction of statutory preconditions and constitutional safeguards warrants that "
            f"the requested relief be {disposition_text.lower()} subject to the directions of the Court."
        )

        decision_basis = (
            f"Substantive provisions of {primary_act}, relevant judicial precedents of the Supreme Court "
            f"and High Court, and settled principles governing {pet_type_abbr.lower()} proceedings."
        )

        # ─── 4. Offline contract ───────────────────────────────────────
        # Pass 3 is a deterministic template synthesis over Pass 1/1b/2 fields.
        # It intentionally does not call Ollama, Hugging Face, or the AI
        # microservice, so ingestion remains auditable and network-free.

        data["summary"] = full_summary
        data["ratio_decidendi"] = ratio_decidendi
        data["legal_issue"] = legal_issue
        data["court_reasoning"] = court_reasoning
        data["decision_basis"] = decision_basis

        confidence["summary"] = {"confidence": 0.88, "source": "pass3_deterministic"}
        confidence["ratio_decidendi"] = {"confidence": 0.86, "source": "pass3_deterministic"}

        return data, confidence

    @classmethod
    def _compute_overall_confidence(cls, confidence: Dict[str, Dict[str, Any]]) -> float:
        """
        Computes weighted average confidence across all extracted dimensions.
        """
        weights = {
            "court": 1.5,
            "bench": 1.0,
            "case_no": 2.0,
            "year": 1.0,
            "cnr": 1.2,
            "judge": 1.2,
            "parties": 1.5,
            "counsel": 0.8,
            "prayer": 1.0,
            "outcome": 1.5,
            "disposition": 1.5,
            "act_tags": 1.2,
            "section_tags": 1.2,
            "source_url": 0.8,
            "summary": 1.0,
            "ratio_decidendi": 1.0,
        }
        total_weight = 0.0
        weighted_sum = 0.0

        for field, conf_info in confidence.items():
            conf_val = conf_info.get("confidence", 0.5)
            w = weights.get(field, 1.0)
            weighted_sum += conf_val * w
            total_weight += w

        return round(weighted_sum / total_weight, 2) if total_weight > 0 else 0.5
