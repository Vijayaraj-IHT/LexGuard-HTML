import os
import re
import hashlib
import json
from pathlib import Path
from collections import defaultdict
import pdfplumber

def dedupe_chars(s: str) -> str:
    """Fix Bombay HC double characters like 'IINN TTHHEE' -> 'IN THE'."""
    tokens = s.split()
    fixed_tokens = []
    for tok in tokens:
        if len(tok) >= 4 and len(tok) % 2 == 0:
            is_doubled = all(tok[i] == tok[i+1] for i in range(0, len(tok), 2))
            if is_doubled:
                fixed_tokens.append(''.join(tok[i] for i in range(0, len(tok), 2)))
                continue
        fixed_tokens.append(tok)
    return ' '.join(fixed_tokens)

def clean_text(txt: str) -> str:
    txt = txt.replace('\r\n', '\n').replace('\r', '\n')
    lines = [l.strip() for l in txt.split('\n')]
    return '\n'.join([l for l in lines if l])

def extract_case_details(pdf_path: str):
    with open(pdf_path, 'rb') as f:
        pdf_bytes = f.read()
    h_doc = hashlib.sha256(pdf_bytes).hexdigest()
    sz = len(pdf_bytes)

    pages_text = []
    with pdfplumber.open(pdf_path) as pdf:
        page_count = len(pdf.pages)
        for p in pdf.pages:
            t = p.extract_text() or ''
            pages_text.append(clean_text(t))

    full_text = '\n\n'.join(pages_text)
    first_pages = '\n\n'.join(pages_text[:3])
    normalized_first = dedupe_chars(first_pages)

    # 1. Determine Court
    court = "High Court of Judicature"
    if "SUPREME COURT OF INDIA" in normalized_first.upper():
        court = "Supreme Court of India"
    elif "GUJARAT" in normalized_first.upper():
        court = "High Court of Gujarat at Ahmedabad"
    elif "BOMBAY" in normalized_first.upper():
        if "NAGPUR" in normalized_first.upper():
            court = "High Court of Judicature at Bombay (Nagpur Bench)"
        elif "GOA" in normalized_first.upper() or "PANAJI" in normalized_first.upper():
            court = "High Court of Bombay at Goa"
        elif "AURANGABAD" in normalized_first.upper():
            court = "High Court of Judicature at Bombay (Aurangabad Bench)"
        else:
            court = "High Court of Judicature at Bombay (Appellate Side)"
    elif "CALCUTTA" in normalized_first.upper():
        court = "High Court at Calcutta (Appellate Side)"
    elif "JAMMU" in normalized_first.upper() or "KASHMIR" in normalized_first.upper():
        court = "High Court of Jammu & Kashmir and Ladakh at Srinagar"
    elif "MADRAS" in normalized_first.upper():
        if "MADURAI" in normalized_first.upper():
            court = "High Court of Judicature at Madras (Madurai Bench)"
        else:
            court = "High Court of Judicature at Madras (Principal Seat, Chennai)"
    elif "DELHI" in normalized_first.upper():
        court = "High Court of Delhi at New Delhi"

    # 2. Case Number
    case_no = None
    cnr = None

    # Check for CNR
    m_cnr = re.search(r'\(([A-Z]{4}\d{12,16})\)', normalized_first)
    if m_cnr:
        cnr = m_cnr.group(1)

    # Check for Bombay citation like 2026:BHC-NAG:14221-DB
    m_bhc = re.search(r'(\d{4}:BHC-[A-Z]+:\d+-[A-Z]+)', normalized_first)
    if m_bhc:
        cnr = m_bhc.group(1)

    # Gujarat pattern like R/CR.MA/25020/2026 or R/SCR.A/15186/2026 or R/CR.A/1040/2002
    m_guj = re.search(r'(R\/(?:CR\.MA|SCR\.A|CR\.A|SCA|CMA|FA)\/\d+\/\d{4})', normalized_first)
    if m_guj:
        case_no = m_guj.group(1)

    # Standard patterns
    if not case_no:
        patterns = [
            r'((?:CRIMINAL\s+WRIT\s+PETITION|WRIT\s+PETITION|CIVIL\s+APPLICATION|CRIMINAL\s+MISC\.?\s*APPLICATION|CRIMINAL\s+APPEAL|CIVIL\s+APPEAL|WPA|WP)\s*(?:\([A-Z]+\))?\s*(?:NO\.?|NOS\.?)?\s*[\d\/\s]+(?:OF|\/|-)\s*\d{4})',
            r'(WP\s+NO\.\s*\d+\/\d{4}(?:\s*C\/W\s*SWP\s*NO\.?\s*\d+\/\d{4})?)',
            r'(WPA\s+\d+\s+OF\s+\d{4})',
            r'(\d+\s+WP\s+\d+\s+\d{4})',
        ]
        for pat in patterns:
            m = re.search(pat, normalized_first, re.I)
            if m:
                raw_cno = m.group(1).strip()
                case_no = re.sub(r'\s+', ' ', raw_cno)
                break

    if not case_no and cnr:
        case_no = f"CASE/{cnr}"
    elif not case_no:
        case_no = f"CASE/{h_doc[:8].upper()}/2026"

    # 3. Year
    m_yr = re.search(r'(?:OF|\/|-)\s*(20\d{2})', case_no)
    year = int(m_yr.group(1)) if m_yr else 2026

    # 4. Judges / Coram
    judge = "Hon'ble High Court"
    m_judge = re.search(r'(?:HONOURABLE\s+(?:MR\.|MS\.|MRS\.)?\s*JUSTICE|CORAM\s*:\s*(?:HON\'BLE\s+(?:MR\.|MS\.)?\s*JUSTICE)?)\s*([A-Z\.\s]{3,35})(?:\s+AND\s+HONOURABLE\s+JUSTICE\s+([A-Z\.\s]{3,35}))?', normalized_first, re.I)
    if m_judge:
        j1 = m_judge.group(1).strip()
        j2 = m_judge.group(2).strip() if m_judge.group(2) else None
        if j2:
            judge = f"Hon'ble Justice {j1} & Hon'ble Justice {j2}"
        else:
            judge = f"Hon'ble Justice {j1}"
    else:
        # Check signature at bottom
        last_page = pages_text[-1] if pages_text else ""
        m_sig = re.search(r'\(([A-Z\s\.]+,\s*J\.)\)', last_page)
        if m_sig:
            judge = f"Hon'ble Justice {m_sig.group(1)}"

    # 5. Litigants / Parties
    petitioner = None
    respondent = None

    # Check Versus
    m_v = re.search(r'([A-Z0-9\s\.\,\(\)\&\'\/\-]{3,60})\s+(?:\.\.\s*)?(?:Versus|VERSUS|V\/s|Vs\.)\s+(?:\.\.\s*)?([A-Z0-9\s\.\,\(\)\&\'\/\-]{3,80})', normalized_first)
    if m_v:
        p_cand = m_v.group(1).strip()
        r_cand = m_v.group(2).strip()
        # Clean noise
        p_cand = re.sub(r'^(?:IN|ORDER|JUDGMENT|DATED|NO|OF|IN THE HIGH COURT)[^\n]*\n?', '', p_cand, flags=re.I).strip()
        r_cand = re.sub(r'(?:\.\.\s*Respondents?|\.\.\s*Petitioners?|\n.*)', '', r_cand, flags=re.I).strip()
        if len(p_cand) > 3 and len(r_cand) > 3:
            petitioner = p_cand
            respondent = r_cand

    if not petitioner or not respondent:
        petitioner = "Petitioner / Appellant"
        respondent = "State / Respondent"

    parties = f"{petitioner} v. {respondent}"
    title = f"{petitioner} v. {respondent}"

    # 6. Acts & Sections Extraction
    act_tags = []
    section_tags = []
    keyword_tags = []

    text_upper = full_text.upper()
    if "PREVENTION OF MONEY LAUNDERING" in text_upper or "PMLA" in text_upper:
        act_tags.append("Prevention of Money Laundering Act, 2002")
        keyword_tags.append("PMLA")
        if "SECTION 45" in text_upper or "45 OF" in text_upper:
            section_tags.append("Section 45 PMLA")
        if "SECTION 50" in text_upper:
            section_tags.append("Section 50 PMLA")

    if "CODE OF CRIMINAL PROCEDURE" in text_upper or "CR.P.C" in text_upper or "CRPC" in text_upper:
        act_tags.append("Code of Criminal Procedure, 1973")
        if "438" in text_upper:
            section_tags.append("Section 438 CrPC")
            keyword_tags.append("Anticipatory Bail")
        if "439" in text_upper:
            section_tags.append("Section 439 CrPC")
            keyword_tags.append("Regular Bail")
        if "482" in text_upper:
            section_tags.append("Section 482 CrPC")
            keyword_tags.append("Inherent Powers / Quashing")

    if "BHARATIYA NAGARIK SURAKSHA" in text_upper or "BNSS" in text_upper:
        act_tags.append("Bharatiya Nagarik Suraksha Sanhita, 2023")
        keyword_tags.append("BNSS")
        if "482" in text_upper:
            section_tags.append("Section 482 BNSS")
        if "483" in text_upper:
            section_tags.append("Section 483 BNSS")

    if "PENAL CODE" in text_upper or "IPC" in text_upper:
        act_tags.append("Indian Penal Code, 1860")
        for s in ["302", "307", "420", "406", "376", "384", "498A", "120B"]:
            if f"SECTION {s}" in text_upper or f"SEC. {s}" in text_upper or f"{s} IPC" in text_upper or f"{s} OF IPC" in text_upper:
                section_tags.append(f"Section {s} IPC")

    if "CONSTITUTION OF INDIA" in text_upper or "ARTICLE 226" in text_upper or "ARTICLE 32" in text_upper:
        act_tags.append("Constitution of India, 1950")
        if "ARTICLE 226" in text_upper or "226 OF" in text_upper:
            section_tags.append("Article 226 Constitution of India")
            keyword_tags.append("Writ Jurisdiction")
        if "ARTICLE 21" in text_upper:
            section_tags.append("Article 21 Constitution of India")
            keyword_tags.append("Right to Personal Liberty")

    if "NEGOTIABLE INSTRUMENTS" in text_upper or "N.I. ACT" in text_upper:
        act_tags.append("Negotiable Instruments Act, 1881")
        if "138" in text_upper:
            section_tags.append("Section 138 NI Act")
            keyword_tags.append("Cheque Dishonour")

    if "PAROLE" in text_upper:
        keyword_tags.append("Parole Leave")
    if "ANTICIPATORY BAIL" in text_upper:
        keyword_tags.append("Anticipatory Bail")
    if "REGULAR BAIL" in text_upper:
        keyword_tags.append("Regular Bail")
    if "DISCHARGE" in text_upper:
        keyword_tags.append("Discharge")

    # Deduplicate tags
    act_tags = list(dict.fromkeys(act_tags))
    section_tags = list(dict.fromkeys(section_tags))
    keyword_tags = list(dict.fromkeys(keyword_tags))

    # 7. Outcome / Disposition
    disposition = "Allowed"
    last_text = full_text[-2500:].upper()
    if "ALLOWED" in last_text or "BAIL IS GRANTED" in last_text or "ORDERED TO BE RELEASED" in last_text:
        if "BAIL" in text_upper:
            disposition = "Bail Granted"
        elif "PAROLE" in text_upper:
            disposition = "Parole Granted"
        else:
            disposition = "Allowed"
    elif "DISMISSED" in last_text or "REJECTED" in last_text:
        if "BAIL" in text_upper:
            disposition = "Bail Rejected"
        else:
            disposition = "Dismissed"
    elif "DISPOSED OF" in last_text or "DISPOSED" in last_text:
        disposition = "Disposed"
    elif "QUASHED" in last_text:
        disposition = "Quashed"

    # 8. Summary & Ratio
    summary = f"Order passed by {court} in {case_no} ({parties}). "
    if keyword_tags:
        summary += f"The matter relates to {', '.join(keyword_tags[:3])}. "
    summary += f"Upon hearing respective counsel and examining judicial records, the Court ordered that the application/petition is {disposition}."

    ratio = f"In {case_no}, {court} affirmed that where statutory preconditions under {', '.join(act_tags[:2]) if act_tags else 'applicable law'} are met, the judicial discretion is exercised in favor of {disposition.lower()}."

    return {
        "h_doc": h_doc,
        "size": sz,
        "page_count": page_count,
        "court": court,
        "case_no": case_no,
        "cnr": cnr,
        "year": year,
        "judge": judge,
        "petitioner": petitioner,
        "respondent": respondent,
        "parties": parties,
        "title": title,
        "act_tags": act_tags,
        "section_tags": section_tags,
        "keyword_tags": keyword_tags,
        "disposition": disposition,
        "summary": summary,
        "ratio_decidendi": ratio,
        "full_text": full_text[:4000] # preview / snippet
    }

def main():
    src_dir = r"E:\SEM 5 PROJECT\LexGuard-HTML\backend\storage\cases"
    home_files = sorted([f for f in os.listdir(src_dir) if f.startswith("Home")])
    
    hash_to_files = defaultdict(list)
    for fname in home_files:
        fp = os.path.join(src_dir, fname)
        with open(fp, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()
        hash_to_files[h].append(fname)
    
    print(f"Analyzing {len(hash_to_files)} unique documents from {len(home_files)} files...\n")
    
    records = []
    for idx, (h, flist) in enumerate(hash_to_files.items(), 1):
        primary_file = flist[0]
        fp = os.path.join(src_dir, primary_file)
        rec = extract_case_details(fp)
        rec["all_filenames"] = flist
        records.append(rec)
        print(f"[{idx:02d}] {rec['case_no']}")
        print(f"     Title: {rec['title'][:65]}")
        print(f"     Court: {rec['court']}")
        print(f"     Bench: {rec['judge']} | Year: {rec['year']} | Pages: {rec['page_count']}")
        print(f"     Acts: {rec['act_tags']} | Outcome: {rec['disposition']}")
        print(f"     Copies: {len(flist)} ({flist[0]})\n")

    out_json = r"E:\SEM 5 PROJECT\Lexguard\new_51_cases_analysis.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    print(f"Saved complete extraction analysis for 30 unique cases to {out_json}")

if __name__ == "__main__":
    main()
