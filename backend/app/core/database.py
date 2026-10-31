import os
import logging
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.core.config import settings

logger = logging.getLogger(__name__)

# Configure engine with engine-specific options and resilient PostgreSQL -> SQLite fallback
target_url = settings.DATABASE_URL
connect_args = {}
engine_kwargs = {
    "pool_pre_ping": True,
    "echo": False,
}

if target_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    engine_kwargs["connect_args"] = connect_args
else:
    engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
        "pool_recycle": 1800,
        "pool_timeout": 30,
        "connect_args": {"connect_timeout": 3},
    })

try:
    engine = create_engine(target_url, **engine_kwargs)
    with engine.connect() as conn:
        pass
except Exception as e:
    if not target_url.startswith("sqlite"):
        logger.warning(
            f"PostgreSQL connection to '{target_url}' failed ({e}). "
            "Falling back to local SQLite database (lexguard.db) for development/evaluation."
        )
        target_url = "sqlite:///./lexguard.db"
        engine = create_engine(
            target_url,
            connect_args={"check_same_thread": False},
            pool_pre_ping=True,
            echo=False,
        )
    else:
        raise e

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency that yields a database session and ensures it closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
