"""
LexGuard Text Sanitizer and Indian Judicial PDF Extraction Service.
Extracts clean, normalized text, CNRs, coram, dates, and statutory references from court judgments.
"""
import re
import os
from typing import Dict, Any, List, Optional
from datetime import datetime
import pdfplumber


class TextSanitizerService:
    """Service for cleaning raw PDF court text and extracting rich legal metadata."""

    # Common recurring court headers across Indian High Courts & Supreme Court
    HEADER_PATTERNS = [
        r'IN\s+THE\s+HIGH\s+COURT\s+OF\s+JUDICATURE\s+AT[^\n]*',
        r'BEFORE\s+THE\s+MADURAI\s+BENCH\s+OF\s+MADRAS\s+HIGH\s+COURT[^\n]*',
        r'HIGH\s+COURT\s+OF\s+GUJARAT\s+AT\s+AHMEDABAD[^\n]*',
        r'IN\s+THE\s+HIGH\s+COURT\s+OF\s+BOMBAY[^\n]*',
        r'IN\s+THE\s+SUPREME\s+COURT\s+OF\s+INDIA[^\n]*',
        r'IN\s+THE\s+HIGH\s+COURT\s+AT\s+CALCUTTA[^\n]*',
        r'HIGH\s+COURT\s+OF\s+JAMMU\s+&\s+KASHMIR[^\n]*',
        r'Page\s+\d+\s+of\s+\d+',
        r'https?://[^\s]+',
        r'Downloaded\s+on\s+-\s+\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}',
    ]

    # Statutory reference patterns
    ACT_SECTION_PATTERNS = [
        # CrPC sections
        (r'\b(?:Section|Sec\.)\s*(\d+[A-Z]?)\s*(?:of\s+(?:the\s+)?)?(?:Cr\.?P\.?C\.?|Code\s+of\s+Criminal\s+Procedure)\b', 'Cr.P.C.'),
        # IPC sections
        (r'\b(?:Section|Sec\.)\s*(\d+[A-Z]?)\s*(?:of\s+(?:the\s+)?)?(?:I\.?P\.?C\.?|Indian\s+Penal\s+Code)\b', 'IPC'),
        # NI Act sections
        (r'\b(?:Section|Sec\.)\s*(138|139|141|142)\s*(?:of\s+(?:the\s+)?)?(?:N\.?I\.?\s*Act|Negotiable\s+Instruments\s+Act)\b', 'NI Act'),
        # NDPS Act
        (r'\b(?:Section|Sec\.)\s*(\d+[A-Z]?)\s*(?:of\s+(?:the\s+)?)?(?:N\.?D\.?P\.?S\.?\s*Act)\b', 'NDPS Act'),
        # POCSO Act
        (r'\b(?:Section|Sec\.)\s*(\d+[A-Z]?)\s*(?:of\s+(?:the\s+)?)?(?:POCSO\s*Act)\b', 'POCSO Act'),
        # Constitution Articles
        (r'\b(?:Article|Art\.)\s*(\d+[A-Z]?)\s*(?:of\s+(?:the\s+)?)?(?:Constitution\s+of\s+India|Constitution)\b', 'Constitution of India'),
        # Arbitration Act
        (r'\b(?:Section|Sec\.)\s*(\d+[A-Z]?)\s*(?:of\s+(?:the\s+)?)?(?:Arbitration\s+and\s+Conciliation\s+Act)\b', 'Arbitration Act'),
    ]

    @classmethod
    def clean_text(cls, raw_text: str) -> str:
        """
        Cleans OCR noise, joins hyphenated split words, strips headers/footers,
        and normalizes judicial paragraph structure.
        """
        if not raw_text:
            return ""

        text = raw_text

        # 1. Strip repetitive headers and web download stamps
        for pattern in cls.HEADER_PATTERNS:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        # 2. Rejoin hyphenated words split across line breaks (e.g. "ju-\nrisdiction" -> "jurisdiction")
        text = re.sub(r'(\b[a-zA-Z]{2,})\s*-\s*\n\s*([a-zA-Z]{2,}\b)', r'\1\2', text)

        # 3. Normalize multiple whitespace and excessive blank lines
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # 4. Clean line margin numbers (e.g. lone numbers at start of lines that are page stamps)
        lines = []
        for line in text.splitlines():
            line_str = line.strip()
            # Skip lone page numbers or bare timestamps
            if re.match(r'^\d{1,4}$', line_str) and len(line_str) <= 3:
                continue
            lines.append(line)

        return '\n'.join(lines).strip()

    @classmethod
    def extract_metadata_from_pdf(cls, pdf_path: str) -> Dict[str, Any]:
        """
        Extracts structured legal metadata from an authentic court judgment PDF.
        """
        if not os.path.exists(pdf_path):
            return {}

        extracted: Dict[str, Any] = {
            "cnr_number": None,
            "case_no": None,
            "decision_date": None,
            "court": None,
            "judge": None,
            "bench_type": "Single Bench",
            "petitioner": None,
            "respondent": None,
            "petitioner_counsel": None,
            "respondent_counsel": None,
            "act_tags": [],
            "section_tags": [],
            "full_text": "",
            "page_count": 0,
            "case_type": "Judgment",
            "legal_domain": "General",
        }

        pages_text = []
        with pdfplumber.open(pdf_path) as pdf:
            extracted["page_count"] = len(pdf.pages)
            for page in pdf.pages:
                txt = page.extract_text() or ""
                pages_text.append(txt)

        raw_full_text = "\n\n".join(pages_text)
        cleaned_text = cls.clean_text(raw_full_text)
        extracted["full_text"] = cleaned_text

        # First 3 pages contain the judicial header coram and parties
        header_text = "\n".join(pages_text[:3])

        # 1. 16-character CNR Number
        cnr_match = re.search(r'CNR\s*:\s*\{?([A-Z0-9]{16})\}?', header_text, re.IGNORECASE)
        if cnr_match:
            extracted["cnr_number"] = cnr_match.group(1).upper()

        # 2. Judgment Date (multiple formats)
        date_patterns = [
            r'DATED\s*:\s*(\d{1,2}[-\/\.]\d{1,2}[-\/\.]\d{4})',
            r'DATED\s*:\s*(\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s+\d{4})',
            r'Date\s+of\s+(?:Decision|Order|Judgment)\s*:\s*(\d{1,2}[-\/\.]\d{1,2}[-\/\.]\d{4})',
            r'Pronounced\s+on\s*:\s*(\d{1,2}[-\/\.]\d{1,2}[-\/\.]\d{4})',
            r'ORDER\s+DATED\s*:\s*(\d{1,2}[-\/\.]\d{1,2}[-\/\.]\d{4})',
        ]
        for dp in date_patterns:
            date_match = re.search(dp, header_text, re.IGNORECASE)
            if date_match:
                raw_d = date_match.group(1).replace('/', '-').replace('.', '-')
                try:
                    parts = raw_d.split('-')
                    if len(parts) == 3:
                        if len(parts[0]) == 4:
                            dt = datetime.strptime(raw_d, "%Y-%m-%d")
                        else:
                            dt = datetime.strptime(raw_d, "%d-%m-%Y")
                        extracted["decision_date"] = dt.strftime("%Y-%m-%d")
                        break
                except Exception:
                    # Try text month parse (e.g. 14th March 2026)
                    clean_d = re.sub(r'(st|nd|rd|th)', '', date_match.group(1))
                    for fmt in ["%d %B %Y", "%d %b %Y"]:
                        try:
                            dt = datetime.strptime(clean_d.strip(), fmt)
                            extracted["decision_date"] = dt.strftime("%Y-%m-%d")
                            break
                        except Exception:
                            pass
                    if extracted["decision_date"]:
                        break

        # 3. Coram / Judge
        coram_match = re.search(
            r'(?:THE\s+)?HON[\'\’]?BLE\s+(?:MR\.|MRS\.|MS\.)?\s*JUSTICE\s+([A-Za-z\s\.\-]+?)(?:\n|AND|\Z)',
            header_text,
            re.IGNORECASE
        )
        if coram_match:
            judge_name = coram_match.group(1).strip()
            judge_name = re.sub(r'[\r\n\t]+', ' ', judge_name).strip()
            if len(judge_name) < 60:
                extracted["judge"] = "Hon'ble Mr. Justice " + judge_name.title()

        # Detect Division Bench
        if "AND" in header_text.upper() and header_text.upper().count("JUSTICE") >= 2:
            extracted["bench_type"] = "Division Bench"

        # 4. Case Number (Expanded Indian High Court & Supreme Court types)
        case_no_match = re.search(
            r'((?:W\.?P\.?|CRL\.?\s*O\.?P\.?|Crl\.?A\.?|C\.?R\.?P\.?|C\.?M\.?A\.?|O\.?S\.?A\.?|W\.?A\.?|Bail\s+Appln|S\.?L\.?P\.?|Arb\.?O\.?P\.?|Cont\.?P\.?|Review\s+Appln)(?:\s*\([A-Z]+\))?[\s\.\w\/]*?(?:No\.?|Nos\.?)\s*[\d\s,andAND]+(?:of|\/)\s*\d{4})',
            header_text,
            re.IGNORECASE
        )
        if case_no_match:
            extracted["case_no"] = case_no_match.group(1).strip()
            c_upper = extracted["case_no"].upper()
            if "CRL" in c_upper and ("OP" in c_upper or "O.P" in c_upper):
                extracted["case_type"] = "Criminal Original Petition"
            elif "CRL" in c_upper and ("A" in c_upper or "APPEAL" in c_upper):
                extracted["case_type"] = "Criminal Appeal"
            elif "W.P" in c_upper or "WP" in c_upper:
                extracted["case_type"] = "Writ Petition"
            elif "W.A" in c_upper or "WA" in c_upper:
                extracted["case_type"] = "Writ Appeal"
            elif "C.R.P" in c_upper or "CRP" in c_upper:
                extracted["case_type"] = "Civil Revision Petition"
            elif "C.M.A" in c_upper or "CMA" in c_upper:
                extracted["case_type"] = "Civil Miscellaneous Appeal"
            elif "BAIL" in c_upper:
                extracted["case_type"] = "Bail Application"
            elif "ARB" in c_upper:
                extracted["case_type"] = "Arbitration Original Petition"
            elif "SLP" in c_upper:
                extracted["case_type"] = "Special Leave Petition"

        # 5. Petitioner and Respondent
        vs_match = re.search(
            r'([^\n]+(?:\n[^\n]+){1,4})\s+(?:\.\.|\s+)(?:Petitioner|Appellant|Applicant)[s\(\)]*?\s*\n+[\s\.\:\-]*Vs\.?[\s\.\:\-]*\n+([^\n]+(?:\n[^\n]+){1,4})',
            header_text,
            re.IGNORECASE
        )
        if vs_match:
            p_lines = [l.strip() for l in vs_match.group(1).splitlines() if l.strip() and not l.strip().isdigit()]
            r_lines = [l.strip() for l in vs_match.group(2).splitlines() if l.strip() and not l.strip().isdigit()]
            if p_lines:
                extracted["petitioner"] = p_lines[0][:150]
            if r_lines:
                extracted["respondent"] = r_lines[0][:150]

        # 6. Statutory Sections Referenced
        acts_found = set()
        sections_found = set()
        for pattern, act_name in cls.ACT_SECTION_PATTERNS:
            matches = re.finditer(pattern, cleaned_text, re.IGNORECASE)
            for m in matches:
                sec_no = m.group(1).strip()
                acts_found.add(act_name)
                sections_found.add(f"Section {sec_no} {act_name}")

        extracted["act_tags"] = sorted(list(acts_found))
        extracted["section_tags"] = sorted(list(sections_found))

        # 7. Determine Legal Domain
        all_acts_upper = " ".join(extracted["act_tags"] + extracted["section_tags"]).upper()
        if any(k in all_acts_upper for k in ["CRPC", "IPC", "NDPS", "POCSO"]):
            extracted["legal_domain"] = "Criminal Law"
        elif "CONSTITUTION" in all_acts_upper or "WRIT" in (extracted["case_type"] or "").upper():
            extracted["legal_domain"] = "Constitutional Law"
        elif "NI ACT" in all_acts_upper:
            extracted["legal_domain"] = "Banking & Negotiable Instruments"
        elif "ARBITRATION" in all_acts_upper:
            extracted["legal_domain"] = "Commercial & Arbitration"
        else:
            extracted["legal_domain"] = "Civil Law"

        return extracted


text_sanitizer = TextSanitizerService()
