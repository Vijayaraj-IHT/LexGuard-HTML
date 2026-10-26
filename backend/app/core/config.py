from pathlib import Path
from typing import List, Union, Optional
import json
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FRONTEND_DIR = REPO_ROOT / "frontend"


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
    APP_VERSION: str = "1.1.0-phase1"
    API_V1_STR: str = "/api/v1"
    ENABLE_API_DOCS: bool = True

    # Single-service deployment: FastAPI can serve the zero-build frontend
    # from the same origin as the API. This keeps HttpOnly-cookie auth and
    # CSRF behaviour simple on free hosting. Local two-server development
    # leaves this disabled by default.
    SERVE_FRONTEND: bool = False
    FRONTEND_DIR: str = str(DEFAULT_FRONTEND_DIR)

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

    # Database Configuration (PostgreSQL default; Neon-compatible)
    DATABASE_URL: str = "postgresql+psycopg2://lexguard:lexguard123@localhost:5432/lexguard"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    # The canonical dump stores embeddings as JSON. Native pgvector is an
    # explicit opt-in for fresh databases whose cases.embedding column was
    # created as vector(384); merely installing the package must not change
    # the ORM type against a restored JSON column.
    USE_PGVECTOR: bool = False

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

    @field_validator("ENVIRONMENT", mode="before")
    @classmethod
    def normalize_environment(cls, v: str) -> str:
        return str(v or "development").strip().lower()

    @field_validator("COOKIE_SAMESITE", mode="before")
    @classmethod
    def normalize_cookie_samesite(cls, v: str) -> str:
        return str(v or "lax").strip().lower()

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        """Accept provider URLs from Neon/Render/Heroku-style dashboards."""
        value = str(v or "").strip()
        if value.startswith("postgres://"):
            return "postgresql+psycopg2://" + value[len("postgres://") :]
        if value.startswith("postgresql://"):
            return "postgresql+psycopg2://" + value[len("postgresql://") :]
        return value

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, str) and v.startswith("["):
            return [str(i).strip() for i in json.loads(v) if str(i).strip()]
        return [str(i).strip() for i in (v or []) if str(i).strip()]

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
            if self.COOKIE_SAMESITE not in {"lax", "strict", "none"}:
                raise ValueError("COOKIE_SAMESITE must be one of: lax, strict, none.")
            if "*" in self.CORS_ORIGINS:
                raise ValueError(
                    "Production security violation: CORS_ORIGINS must list explicit origins; "
                    "wildcard origins are incompatible with credentialed cookie auth."
                )
        if self.DB_POOL_SIZE < 1 or self.DB_MAX_OVERFLOW < 0:
            raise ValueError("DB_POOL_SIZE must be at least 1 and DB_MAX_OVERFLOW cannot be negative.")
        return self


settings = Settings()

