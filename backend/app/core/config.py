from typing import List, Union, Optional
import json
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PROJECT_NAME: str = "Lexguard Legal Research & Verification System"
    API_V1_STR: str = "/api/v1"

    # Cryptography & JWT Security
    SECRET_KEY: str = "lexguard-super-secret-jwt-key-2026-production-ready-32-chars-min"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # 60 minutes (1 hour)
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Cookie & CSRF Protection
    COOKIE_NAME: str = "lexguard_access_token"
    COOKIE_SECURE: bool = False  # Set to True when served over HTTPS (enforced outside development)
    COOKIE_SAMESITE: str = "lax"
    CSRF_HEADER_NAME: str = "X-CSRF-Token"
    CSRF_SECRET: str = "lexguard-csrf-protection-secret-key-salt"

    # Database Configuration (PostgreSQL default)
    DATABASE_URL: str = "postgresql+psycopg2://lexguard:lexguard123@localhost:5432/lexguard"

    # File Storage
    STORAGE_DIR: str = "./storage/cases"

    # Hugging Face Open-Source Model Stack
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"
    LEGAL_NER_MODEL_NAME: str = "law-ai/InLegalBERT"
    LOCAL_LLM_MODEL_NAME: str = "Qwen/Qwen2.5-3B-Instruct"  # or meta-llama/Llama-3.2-3B-Instruct
    USE_LOCAL_LLM: bool = True
    HF_TOKEN: Optional[str] = None
    DEVICE: str = "cpu"  # "cuda" if GPU is available
    QUANTIZATION_BITS: int = 4

    # Optional Fallbacks
    ANTHROPIC_API_KEY: str = ""
    USE_MOCK_LLM: bool = False

    # CORS Allowed Origins
    CORS_ORIGINS: Union[List[str], str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://localhost:8888",
        "http://127.0.0.1:8888",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, str) and v.startswith("["):
            return json.loads(v)
        return v

    @model_validator(mode="after")
    def validate_production_security(self):
        default_secret = "lexguard-super-secret-jwt-key-2026-production-ready-32-chars-min"
        if self.ENVIRONMENT != "development":
            if self.SECRET_KEY == default_secret or len(self.SECRET_KEY) < 32:
                raise ValueError(
                    "Production security violation: SECRET_KEY must be set to a secure, "
                    "non-default string of at least 32 characters in production."
                )
            if not self.COOKIE_SECURE:
                raise ValueError(
                    "Production security violation: COOKIE_SECURE must be True outside development "
                    "to ensure auth cookies are only transmitted over HTTPS."
                )
        return self


settings = Settings()

import os
import re
from pathlib import Path

COURT_CODES = {
    "supreme court of india": "SC",
    "madras high court": "MHC",
    "madras high court (principal seat)": "MHC-PS",
    "madras high court (madurai bench)": "MHC-MB",
    "bombay high court": "BHC",
    "delhi high court": "DHC",
    "calcutta high court": "CHC",
    "gujarat high court": "GHC",
    "allahabad high court": "ALHC",
    "punjab and haryana high court": "PHHC",
}


def build_case_pdf_filename(court: str, year: int, case_no: str, case_id: str) -> str:
    """Generates standardized judicial PDF filename: {COURT_CODE}_{YEAR}_{CASE_NO}_{SHORT_ID}.pdf"""
    court_key = (court or "").strip().lower()
    court_code = COURT_CODES.get(court_key)
    if not court_code:
        for k, v in COURT_CODES.items():
            if k in court_key:
                court_code = v
                break
    court_code = court_code or "HC"
    clean_case_no = re.sub(r"[^A-Za-z0-9]+", "-", (case_no or "CASE")).strip("-")[:40]
    short_id = str(case_id).split("-")[0][:8]
    return f"{court_code}_{year}_{clean_case_no}_{short_id}.pdf"


def resolve_case_pdf_path(stored_path: str) -> Path:
    """Resolves physical PDF path across execution environments and root/backend storage trees."""
    if not stored_path:
        return Path(settings.STORAGE_DIR)
    p = Path(stored_path)
    if p.exists():
        return p
    clean_name = Path(stored_path.replace("\\", "/")).name
    candidates = [
        Path(settings.STORAGE_DIR) / clean_name,
        Path("storage/cases") / clean_name,
        Path("backend/storage/cases") / clean_name,
        Path(os.getcwd()) / "storage" / "cases" / clean_name,
        Path(os.getcwd()) / "backend" / "storage" / "cases" / clean_name,
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    return Path(settings.STORAGE_DIR) / clean_name

