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


text_sanitizer = TextSanitizerService()
