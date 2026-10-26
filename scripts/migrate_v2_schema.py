"""
Database Migration: Add v2 Legal Research & Verification Schema Fields.
Non-destructive: Adds nullable/default columns to 'cases' table.
"""
import psycopg2
import re

DB_URI = "postgresql://lexguard:lexguard123@localhost:5432/lexguard"

NEW_COLUMNS = [
    ("cnr_number", "VARCHAR(16)", "ADD COLUMN IF NOT EXISTS cnr_number VARCHAR(16)"),
    ("case_type", "VARCHAR(50)", "ADD COLUMN IF NOT EXISTS case_type VARCHAR(50) DEFAULT 'Judgment'"),
    ("decision_date", "DATE", "ADD COLUMN IF NOT EXISTS decision_date DATE"),
    ("bench_type", "VARCHAR(50)", "ADD COLUMN IF NOT EXISTS bench_type VARCHAR(50) DEFAULT 'Single Bench'"),
    ("petitioner", "VARCHAR(255)", "ADD COLUMN IF NOT EXISTS petitioner VARCHAR(255)"),
    ("respondent", "VARCHAR(255)", "ADD COLUMN IF NOT EXISTS respondent VARCHAR(255)"),
    ("petitioner_counsel", "VARCHAR(255)", "ADD COLUMN IF NOT EXISTS petitioner_counsel VARCHAR(255)"),
    ("respondent_counsel", "VARCHAR(255)", "ADD COLUMN IF NOT EXISTS respondent_counsel VARCHAR(255)"),
    ("legal_domain", "VARCHAR(100)", "ADD COLUMN IF NOT EXISTS legal_domain VARCHAR(100) DEFAULT 'General'"),
    ("layman_summary", "TEXT", "ADD COLUMN IF NOT EXISTS layman_summary TEXT"),
    ("cited_by_count", "INTEGER", "ADD COLUMN IF NOT EXISTS cited_by_count INTEGER DEFAULT 0"),
    ("official_citation", "VARCHAR(150)", "ADD COLUMN IF NOT EXISTS official_citation VARCHAR(150)"),
]

NEW_INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_cases_cnr_number ON cases (cnr_number);",
    "CREATE INDEX IF NOT EXISTS ix_cases_case_type ON cases (case_type);",
    "CREATE INDEX IF NOT EXISTS ix_cases_decision_date ON cases (decision_date);",
    "CREATE INDEX IF NOT EXISTS ix_cases_legal_domain ON cases (legal_domain);",
]

def derive_case_type(case_no: str) -> str:
    """Derives standard Indian legal case type abbreviation to human-readable form."""
    c_upper = case_no.upper()
    if "CRL OP" in c_upper or "CRL.O.P" in c_upper:
        return "Criminal Original Petition"
    if "CRL A" in c_upper or "CRL.A" in c_upper:
        return "Criminal Appeal"
    if "CRL RC" in c_upper or "CRL.R.C" in c_upper:
        return "Criminal Revision Case"
    if "W.P" in c_upper or "WP" in c_upper:
        return "Writ Petition"
    if "W.A" in c_upper or "WA" in c_upper:
        return "Writ Appeal"
    if "C.R.P" in c_upper or "CRP" in c_upper:
        return "Civil Revision Petition"
    if "C.M.A" in c_upper or "CMA" in c_upper:
        return "Civil Miscellaneous Appeal"
    if "O.S.A" in c_upper or "OSA" in c_upper:
        return "Original Side Appeal"
    if "BAIL" in c_upper:
        return "Bail Application"
    if "SLP" in c_upper:
        return "Special Leave Petition"
    if "CIVIL APPEAL" in c_upper or "C.A" in c_upper:
        return "Civil Appeal"
    return "Judgment"

def derive_legal_domain(act_tags, section_tags, title) -> str:
    """Derives primary legal domain from tags and title."""
    combined = " ".join((act_tags or []) + (section_tags or []) + [title or ""]).upper()
    if any(k in combined for k in ["CRPC", "IPC", "CRIMINAL", "BAIL", "NDPS", "POCSO", "FIR", "QUASH"]):
        return "Criminal Law"
    if any(k in combined for k in ["CONSTITUTION", "ARTICLE 226", "ARTICLE 32", "WRIT", "MANDAMUS", "QUO WARRANTO"]):
        return "Constitutional Law"
    if any(k in combined for k in ["NI ACT", "NEGOTIABLE", "SECTION 138", "CHEQUE", "BANKING"]):
        return "Banking & Negotiable Instruments"
    if any(k in combined for k in ["ARBITRATION", "SECTION 34", "SECTION 11", "SECTION 9", "COMMERCIAL"]):
        return "Commercial & Arbitration"
    if any(k in combined for k in ["SERVICE", "PROMOTION", "PENSION", "DISMISSAL", "APPOINTMENT"]):
        return "Service & Employment Law"
    if any(k in combined for k in ["TAX", "INCOME TAX", "GST", "CUSTOMS", "EXCISE"]):
        return "Taxation Law"
    if any(k in combined for k in ["MARRIAGE", "DIVORCE", "MAINTENANCE", "CUSTODY", "HMA", "DV ACT"]):
        return "Family Law"
    return "Civil Law"

def derive_parties(title: str):
    """Splits 'X v. Y' or 'X vs Y' into petitioner and respondent."""
    parts = re.split(r'\s+v(?:s|\.)?\s+', title, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        return parts[0].strip()[:250], parts[1].strip()[:250]
    return title[:250], None

def run_migration():
    print("=" * 60)
    print("EXECUTING LEXGUARD V2 DATABASE SCHEMA MIGRATION")
    print("=" * 60)
    conn = psycopg2.connect(DB_URI)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # 1. Add Columns
        for col, col_type, sql in NEW_COLUMNS:
            cur.execute(f"ALTER TABLE cases {sql};")
            print(f" [+] Ensured column: cases.{col} ({col_type})")

        # 2. Add Indexes
        for idx_sql in NEW_INDEXES:
            cur.execute(idx_sql)
        print(" [+] Ensured index definitions.")

        # 3. Backfill existing 130 cases
        cur.execute("SELECT id, case_no, title, act_tags, section_tags, summary, parties, year FROM cases;")
        rows = cur.fetchall()
        print(f"\nBackfilling {len(rows)} existing cases with intelligent defaults...")

        updated = 0
        for r in rows:
            cid, case_no, title, act_tags, sec_tags, summary, parties_str, year = r
            c_type = derive_case_type(case_no or "")
            domain = derive_legal_domain(act_tags, sec_tags, title)
            pet, resp = derive_parties(title or "")
            if not pet and parties_str:
                pet, resp = derive_parties(parties_str)

            # Generate layman summary if absent
            layman = f"In this {c_type.lower()} under {domain}, the Court ruled on the dispute between {pet or 'the Petitioner'} and {resp or 'the Respondent'}."
            
            # Simple official citation format
            off_cite = f"{year} LexGuard ({c_type[:4].strip()}) {cid[:6].upper()}"

            cur.execute("""
                UPDATE cases
                SET case_type = %s,
                    legal_domain = %s,
                    petitioner = COALESCE(petitioner, %s),
                    respondent = COALESCE(respondent, %s),
                    layman_summary = COALESCE(layman_summary, %s),
                    official_citation = COALESCE(official_citation, %s),
                    precedential_status = CASE WHEN precedential_status IS NULL OR precedential_status = '' THEN 'Precedential status not checked' ELSE precedential_status END
                WHERE id = %s;
            """, (c_type, domain, pet, resp, layman, off_cite, cid))
            updated += 1

        conn.commit()
        print(f" [+] Successfully backfilled {updated} cases!")
        print("=" * 60)
        print("MIGRATION COMPLETED SUCCESSFULLY")
        print("=" * 60)

    except Exception as e:
        conn.rollback()
        print(" [-] MIGRATION FAILED:", e)
        raise e
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    run_migration()
