import sys
import os
from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from app.core.database import engine

def migrate():
    with engine.connect() as conn:
        res = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'cases';
        """))
        cols = {r[0] for r in res.fetchall()}
        print(f"Total existing columns: {len(cols)}")

        new_cols = [
            ("source_url", "VARCHAR(500)"),
            ("source_verification_state", "VARCHAR(50) DEFAULT 'unverified'"),
            ("precedential_status", "VARCHAR(100) DEFAULT 'Precedential status not checked'"),
        ]

        for col, col_type in new_cols:
            if col not in cols:
                print(f"Adding column {col}...")
                conn.execute(text(f"ALTER TABLE cases ADD COLUMN IF NOT EXISTS {col} {col_type};"))
            else:
                print(f"Column {col} already exists.")
        
        conn.commit()
        print("Schema migration for source fields successfully completed.")

if __name__ == "__main__":
    migrate()
