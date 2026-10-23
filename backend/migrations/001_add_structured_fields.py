"""
Migration 001: Add structured judicial dimension columns to cases table.
Usage: python backend/migrations/001_add_structured_fields.py
"""
import os
import sys

# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import inspect, text
from app.core.database import engine

COLUMNS = [
    ("facts", "TEXT"),
    ("issues_framed", "JSON"),
    ("ratio_decidendi", "TEXT"),
    ("statutory_tests", "JSON"),
    ("disposition", "VARCHAR(100)"),
    ("precedents_cited", "JSON"),
]

def run():
    print(f"Connecting to database engine: {engine.url.drivername}...")
    inspector = inspect(engine)
    existing_cols = {col["name"] for col in inspector.get_columns("cases")}
    
    is_sqlite = "sqlite" in engine.url.drivername

    with engine.begin() as conn:
        for col_name, col_type in COLUMNS:
            actual_type = "TEXT" if (is_sqlite and col_type == "JSON") else col_type
            if col_name not in existing_cols:
                conn.execute(text(f"ALTER TABLE cases ADD COLUMN {col_name} {actual_type}"))
                print(f"  [+] Added column: {col_name} ({actual_type})")
            else:
                print(f"  [*] Column already exists: {col_name}")

    print("Migration 001 completed successfully.")

if __name__ == "__main__":
    run()
