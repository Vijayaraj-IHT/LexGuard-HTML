"""
Enrich Existing Case Corpus directly from Official Judgment PDFs.
Extracts official CNRs, Case Numbers, Decision Dates, Coram, and Cleaned Full Text.
"""
import sys
import os
import psycopg2

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.services.text_sanitizer import text_sanitizer

DB_URI = "postgresql://lexguard:lexguard123@localhost:5432/lexguard"

def enrich_all_cases():
    print("=" * 65)
    print("ENRICHING 130 CASES FROM OFFICIAL MULTI-PAGE JUDGMENT PDFS")
    print("=" * 65)
    
    conn = psycopg2.connect(DB_URI)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        cur.execute("SELECT id, case_no, title, court, file_path, full_text, cnr_number FROM cases;")
        rows = cur.fetchall()
        print(f"Loaded {len(rows)} cases from database.")

        updated_count = 0
        cnr_extracted = 0
        text_populated = 0

        for idx, (cid, old_cno, old_title, court, fpath, old_full_text, old_cnr) in enumerate(rows, 1):
            if not fpath or not os.path.exists(fpath):
                continue

            try:
                meta = text_sanitizer.extract_metadata_from_pdf(fpath)
            except Exception as e:
                print(f" [-] Failed parsing {cid}: {e}")
                continue

            new_cno = (meta.get("case_no") or old_cno)[:250]
            new_cnr = (meta.get("cnr_number") or old_cnr)
            if new_cnr:
                new_cnr = new_cnr[:16]
            new_date = meta.get("decision_date")
            new_judge = (meta.get("judge") or "")[:450] if meta.get("judge") else None
            new_case_type = (meta.get("case_type") or "Judgment")[:50]
            new_domain = (meta.get("legal_domain") or "General")[:90]
            new_p_count = meta.get("page_count") or 1
            cleaned_text = meta.get("full_text") or old_full_text or ""

            # Check if title is generic / corrupted
            new_title = (old_title or "")[:490]
            pet = meta.get("petitioner")
            resp = meta.get("respondent")
            if pet and resp:
                new_title = f"{pet} v. {resp}"[:490]
            elif ("Home Judgements" in (old_title or "") or len(old_title or "") < 10 or "1Aa " in (old_title or "")) and (pet or resp):
                new_title = f"{pet or 'Petitioner'} v. {resp or 'Respondent'}"[:490]

            # Only update if meaningful data extracted
            if new_cnr and not old_cnr:
                cnr_extracted += 1
            if cleaned_text and not old_full_text:
                text_populated += 1

            cur.execute("""
                UPDATE cases
                SET case_no = CASE WHEN %s IS NOT NULL AND %s NOT LIKE 'CASE/%%' THEN %s ELSE case_no END,
                    cnr_number = COALESCE(%s, cnr_number),
                    decision_date = COALESCE(%s, decision_date),
                    judge = COALESCE(%s, judge),
                    case_type = CASE WHEN %s != 'Judgment' THEN %s ELSE case_type END,
                    legal_domain = COALESCE(%s, legal_domain),
                    title = CASE WHEN %s != %s AND %s NOT LIKE '%%Home Judgements%%' THEN %s ELSE title END,
                    petitioner = COALESCE(%s, petitioner),
                    respondent = COALESCE(%s, respondent),
                    full_text = CASE WHEN (full_text IS NULL OR length(full_text) < 10) AND length(%s) > 10 THEN %s ELSE full_text END,
                    page_count = GREATEST(page_count, %s)
                WHERE id = %s;
            """, (
                new_cno, new_cno, new_cno,
                new_cnr,
                new_date,
                new_judge,
                new_case_type, new_case_type,
                new_domain,
                new_title, old_title, new_title, new_title,
                pet,
                resp,
                cleaned_text, cleaned_text,
                new_p_count,
                cid
            ))
            updated_count += 1

            if idx % 25 == 0 or idx == len(rows):
                print(f" [{idx}/{len(rows)}] Processed... (CNRs newly extracted: {cnr_extracted}, Full texts populated: {text_populated})")

        conn.commit()
        print("=" * 65)
        print(f"SUCCESS: Enriched {updated_count} cases.")
        print(f"Total new CNRs identified: {cnr_extracted}")
        print(f"Total full texts populated: {text_populated}")
        print("=" * 65)

    except Exception as e:
        conn.rollback()
        print(" [-] Corpus enrichment failed:", e)
        raise e
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    enrich_all_cases()
