import re
import logging
from typing import Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)

# Pre-compiled regex patterns for high-precision Indian statutory citation extraction
STATUTE_PATTERNS = [
    # IPC (Indian Penal Code)
    (r"(?:Section|Sec\.?|s\.)\s*(\d+[A-Z]?)\s*(?:of\s*(?:the\s*)?)?(?:IPC|Indian\s*Penal\s*Code)", "IPC"),
    (r"(?:IPC|Indian\s*Penal\s*Code)\s*(?:Section|Sec\.?|s\.)\s*(\d+[A-Z]?)", "IPC"),
    
    # CrPC (Code of Criminal Procedure)
    (r"(?:Section|Sec\.?|s\.)\s*(\d+[A-Z]?)\s*(?:of\s*(?:the\s*)?)?(?:CrPC|Cr\.P\.C\.?|Code\s*of\s*Criminal\s*Procedure)", "CrPC"),
    (r"(?:CrPC|Cr\.P\.C\.?)\s*(?:Section|Sec\.?|s\.)\s*(\d+[A-Z]?)", "CrPC"),
    
    # NDPS Act
    (r"(?:Section|Sec\.?|s\.)\s*(\d+[A-Z]?)\s*(?:of\s*(?:the\s*)?)?(?:NDPS|Narcotic\s*Drugs(?:\s*and\s*Psychotropic\s*Substances)?\s*Act)", "NDPS Act"),
    
    # Constitution of India
    (r"(?:Article|Art\.?)\s*(\d+[A-Z]?)\s*(?:of\s*(?:the\s*)?)?(?:Constitution|Constitution\s*of\s*India)?", "Constitution of India"),
    
    # IT Act
    (r"(?:Section|Sec\.?|s\.)\s*(\d+[A-Z]?)\s*(?:of\s*(?:the\s*)?)?(?:IT\s*Act|Information\s*Technology\s*Act)", "IT Act"),
    
    # Negotiable Instruments Act (Section 138)
    (r"(?:Section|Sec\.?|s\.)\s*(\d+[A-Z]?)\s*(?:of\s*(?:the\s*)?)?(?:NI\s*Act|Negotiable\s*Instruments\s*Act)", "NI Act"),

    # Bharatiya Nyaya Sanhita (BNS / BNSS)
    (r"(?:Section|Sec\.?|s\.)\s*(\d+[A-Z]?)\s*(?:of\s*(?:the\s*)?)?(?:BNS|Bharatiya\s*Nyaya\s*Sanhita)", "BNS"),
    (r"(?:Section|Sec\.?|s\.)\s*(\d+[A-Z]?)\s*(?:of\s*(?:the\s*)?)?(?:BNSS|Bharatiya\s*Nagarik\s*Suraksha\s*Sanhita)", "BNSS"),
]

LEGAL_KEYWORDS = [
    "anticipatory bail", "regular bail", "bail", "quashing", "prima facie",
    "mens rea", "parity", "custodial interrogation", "habeas corpus",
    "mandamus", "certiorari", "injunction", "stay of arrest", "charge sheet",
    "prolonged incarceration", "speedy trial", "confession", "admissibility",
    "murder", "culpable homicide", "conviction", "homicide", "death penalty", "section 302"
]


class LegalNERService:
    """
    Indian Legal Named Entity & Statute Extraction Service.
    Integrates Hugging Face InLegalBERT (law-ai/InLegalBERT) with
    high-speed pattern extraction for Indian legal texts.
    """

    def __init__(self):
        self.model_name = settings.LEGAL_NER_MODEL_NAME
        self._pipeline = None
        self._loaded = False

    def _load_pipeline(self):
        if self._loaded:
            return self._pipeline
        try:
            from transformers import pipeline
            logger.info(f"Loading Hugging Face legal NER pipeline: {self.model_name}...")
            self._pipeline = pipeline(
                "token-classification",
                model=self.model_name,
                device=-1 if settings.DEVICE == "cpu" else 0,
            )
            self._loaded = True
            logger.info("InLegalBERT pipeline loaded successfully.")
        except Exception as e:
            logger.info(
                f"Hugging Face InLegalBERT model deferred or not cached locally ({e}). "
                "Using fast Indian statutory pattern extraction."
            )
            self._pipeline = None
            self._loaded = True
        return self._pipeline

    def extract_legal_entities(self, text: str) -> Dict[str, Any]:
        """
        Extracts legal sections, Acts, and legal terms from text.
        Returns:
            {
                "acts": ["IPC", "CrPC"],
                "sections": ["Section 420 IPC", "Section 439 CrPC"],
                "keywords": ["bail", "parity"],
                "hf_entities": [...]
            }
        """
        if not text:
            return {"acts": [], "sections": [], "keywords": [], "hf_entities": []}

        acts_found = set()
        sections_found = set()
        keywords_found = set()

        # 1. Rule-Based Indian Statute NER
        for pattern, act_name in STATUTE_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for m in matches:
                sec_num = m.group(1)
                acts_found.add(act_name)
                if act_name == "Constitution of India":
                    sections_found.add(f"Article {sec_num}")
                else:
                    sections_found.add(f"Section {sec_num} {act_name}")

        # 2. Key legal terms matching
        text_lower = text.lower()
        for kw in LEGAL_KEYWORDS:
            if re.search(r"\b" + re.escape(kw) + r"\b", text_lower):
                keywords_found.add(kw)

        # 3. Hugging Face InLegalBERT inference (if pipeline available)
        hf_entities = []
        pipe = self._load_pipeline()
        if pipe is not None:
            try:
                # Truncate text chunk for BERT token classification
                raw_results = pipe(text[:1024])
                for res in raw_results:
                    hf_entities.append({
                        "word": res.get("word"),
                        "entity": res.get("entity"),
                        "score": round(float(res.get("score", 0.0)), 4),
                    })
            except Exception as e:
                logger.error(f"InLegalBERT classification error: {e}")

        return {
            "acts": sorted(list(acts_found)),
            "sections": sorted(list(sections_found)),
            "keywords": sorted(list(keywords_found)),
            "hf_entities": hf_entities,
        }


ner_service = LegalNERService()
