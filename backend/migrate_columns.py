from sqlalchemy import text
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
            ("facts", "TEXT"),
            ("issues_framed", "JSONB DEFAULT '[]'::jsonb"),
            ("ratio_decidendi", "TEXT"),
            ("statutory_tests", "JSONB DEFAULT '[]'::jsonb"),
            ("disposition", "VARCHAR(100)"),
            ("precedents_cited", "JSONB DEFAULT '[]'::jsonb")
        ]

        for col, col_type in new_cols:
            if col not in cols:
                print(f"Adding column {col}...")
                conn.execute(text(f"ALTER TABLE cases ADD COLUMN IF NOT EXISTS {col} {col_type};"))
            else:
                print(f"Column {col} already exists.")
        
        conn.commit()
        print("Schema migration successfully completed.")

if __name__ == "__main__":
    migrate()
