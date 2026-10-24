"""
LexGuard Two-Way Precedent & Citation Network Linker
=====================================================
Analyzes judgment text across the repository to detect cited precedents,
constructs the bidirectional citation graph, links target case UUIDs,
and updates cited_by_count and precedential_status across the database.
"""

import os
import sys
import re
import json

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
from app.core.database import SessionLocal
from app.models.case import Case

# Regex patterns for formal judicial citations in Indian judgments
FORMAL_CITATION_PATTERNS = [
    re.compile(r'(\(\d{4}\)\s+\d+\s+SCC\s+\d+)', re.IGNORECASE),
    re.compile(r'(AIR\s+\d{4}\s+SC\s+\d+)', re.IGNORECASE),
    re.compile(r'(\d{4}\s+SCC\s+OnLine\s+[A-Za-z\s]+\d+)', re.IGNORECASE),
    re.compile(r'(\d{4}\s+Cri?\s*L\.?J\.?\s+\d+)', re.IGNORECASE),
    re.compile(r'(\d{4}\s+SCR\s+\d+)', re.IGNORECASE),
    re.compile(r'((?:19|20)\d{2}\s+Supp\s*\(\d+\)\s+SCC\s+\d+)', re.IGNORECASE),
]

# Landmark name keywords and their canonical metadata
LANDMARK_MATCHERS = [
    {
        "keywords": ["Lalita Kumari", "Lalitha Kumari"],
        "title": "Lalita Kumari v. Government of Uttar Pradesh",
        "citation": "(2014) 2 SCC 1",
        "court": "Supreme Court of India",
        "status": "Good Law (Binding Precedent)",
        "ratio_key": "Mandatory registration of FIR under Section 154 CrPC",
    },
    {
        "keywords": ["Satender Kumar Antil", "Satinder Kumar Antil"],
        "title": "Satender Kumar Antil v. Central Bureau of Investigation",
        "citation": "(2022) 10 SCC 51",
        "court": "Supreme Court of India",
        "status": "Good Law (Binding Precedent)",
        "ratio_key": "Categorization of offences and non-custodial bail guidelines",
    },
    {
        "keywords": ["Arnesh Kumar"],
        "title": "Arnesh Kumar v. State of Bihar",
        "citation": "(2014) 8 SCC 273",
        "court": "Supreme Court of India",
        "status": "Good Law (Binding Precedent)",
        "ratio_key": "Section 41A CrPC notice and safeguards against automatic arrest",
    },
    {
        "keywords": ["Bhajan Lal"],
        "title": "State of Haryana v. Bhajan Lal",
        "citation": "1992 Supp (1) SCC 335",
        "court": "Supreme Court of India",
        "status": "Good Law (Binding Precedent)",
        "ratio_key": "Seven categories of cases for quashing under Section 482 CrPC",
    },
    {
        "keywords": ["D.K. Basu", "DK Basu", "D.K.Basu"],
        "title": "D.K. Basu v. State of West Bengal",
        "citation": "(1997) 1 SCC 416",
        "court": "Supreme Court of India",
        "status": "Good Law (Binding Precedent)",
        "ratio_key": "Mandatory 11-point custodial torture safeguards and arrest memo",
    },
    {
        "keywords": ["Rangappa v. Sri Mohan", "Rangappa vs. Sri Mohan"],
        "title": "Rangappa v. Sri Mohan",
        "citation": "(2010) 11 SCC 441",
        "court": "Supreme Court of India",
        "status": "Good Law (Binding 3-Judge Precedent)",
        "ratio_key": "Rebuttable statutory presumption under Section 139 NI Act",
    },
    {
        "keywords": ["Gian Singh"],
        "title": "Gian Singh v. State of Punjab",
        "citation": "(2012) 10 SCC 303",
        "court": "Supreme Court of India",
        "status": "Good Law (Binding 3-Judge Precedent)",
        "ratio_key": "Inherent power to quash non-compoundable private disputes on settlement",
    },
    {
        "keywords": ["Maneka Gandhi"],
        "title": "Maneka Gandhi v. Union of India",
        "citation": "(1978) 1 SCC 248",
        "court": "Supreme Court of India",
        "status": "Good Law (Foundational 7-Judge Landmark)",
        "ratio_key": "Substantive due process and golden triangle under Article 21",
    },
    {
        "keywords": ["Puttaswamy", "K.S. Puttaswamy"],
        "title": "Justice K.S. Puttaswamy (Retd.) v. Union of India",
        "citation": "(2017) 10 SCC 1",
        "court": "Supreme Court of India",
        "status": "Good Law (Unanimous 9-Judge Benchmark)",
        "ratio_key": "Fundamental right to privacy under Article 21",
    },
    {
        "keywords": ["Gurbaksh Singh Sibbia", "Gurbaksh Sibbia"],
        "title": "Gurbaksh Singh Sibbia v. State of Punjab",
        "citation": "(1980) 2 SCC 565",
        "court": "Supreme Court of India",
        "status": "Good Law (5-Judge Constitution Bench Precedent)",
        "ratio_key": "Wide judicial discretion for anticipatory bail under Section 438 CrPC",
    },
    {
        "keywords": ["Sushila Aggarwal", "Sushila Agarwal"],
        "title": "Sushila Aggarwal v. State (NCT of Delhi)",
        "citation": "(2020) 5 SCC 1",
        "court": "Supreme Court of India",
        "status": "Good Law (5-Judge Constitution Bench)",
        "ratio_key": "Anticipatory bail protection endures until conclusion of trial",
    },
    {
        "keywords": ["Shreya Singhal"],
        "title": "Shreya Singhal v. Union of India",
        "citation": "(2015) 5 SCC 1",
        "court": "Supreme Court of India",
        "status": "Good Law (Landmark Free Speech Ruling)",
        "ratio_key": "Unconstitutionality of Section 66A IT Act under Article 19(1)(a)",
    },
    {
        "keywords": ["Vishaka v. State of Rajasthan", "Vishakha v. State of Rajasthan"],
        "title": "Vishaka v. State of Rajasthan",
        "citation": "(1997) 6 SCC 241",
        "court": "Supreme Court of India",
        "status": "Good Law (Codified into POSH Act, 2013)",
        "ratio_key": "Guidelines against sexual harassment of women at workplaces",
    },
    {
        "keywords": ["P. Chidambaram v. Directorate of Enforcement", "P.Chidambaram v. Directorate of Enforcement"],
        "title": "P. Chidambaram v. Directorate of Enforcement",
        "citation": "(2019) 9 SCC 24",
        "court": "Supreme Court of India",
        "status": "Good Law (Precedent on PMLA Bail)",
        "ratio_key": "Economic offences alone do not justify mechanical denial of bail",
    },
    {
        "keywords": ["Mishrilal", "Mishri Lal"],
        "title": "State of M.P. v. Mishrilal",
        "citation": "(2003) 9 SCC 426",
        "court": "Supreme Court of India",
        "status": "Good Law (Binding Procedural Precedent)",
        "ratio_key": "Procedure for simultaneous trial and judgment in cross-cases",
    },
    {
        "keywords": ["Indra Sawhney", "Indira Sawhney"],
        "title": "Indra Sawhney v. Union of India",
        "citation": "1992 Supp (3) SCC 217",
        "court": "Supreme Court of India",
        "status": "Good Law (Constitutional Benchmark)",
        "ratio_key": "50% ceiling limit on reservations and creamy layer exclusion",
    },
]

def main():
    print("=" * 70)
    print("LEXGUARD TWO-WAY CITATION & PRECEDENT NETWORK LINKER")
    print("=" * 70)

    db = SessionLocal()
    cases = db.query(Case).all()
    print(f"Total cases in repository: {len(cases)}")

    # 1. Build lookup maps for fast ID resolution
    citation_to_case = {}
    caseno_to_case = {}
    title_to_case = {}

    for c in cases:
        if c.official_citation:
            citation_to_case[c.official_citation.strip().lower()] = c
        if c.case_no:
            caseno_to_case[c.case_no.strip().lower()] = c
        if c.title:
            title_to_case[c.title.strip().lower()] = c

    # Reverse citation map: target_case_id -> set of citing case_ids
    citation_graph = {c.id: set() for c in cases}
    total_precedents_linked = 0
    cases_with_citations = 0

    # 2. Iterate each case and discover cited precedents
    for idx, c in enumerate(cases, 1):
        corpus = f"{c.full_text or ''} {c.summary or ''} {c.ratio_decidendi or ''}"
        found_precedents = []
        seen_keys = set()

        # Check landmark matchers
        for lm in LANDMARK_MATCHERS:
            matched = False
            for kw in lm["keywords"]:
                if re.search(r'\b' + re.escape(kw) + r'\b', corpus, re.IGNORECASE):
                    matched = True
                    break
            if matched:
                prec_entry = {
                    "title": lm["title"],
                    "citation": lm["citation"],
                    "court": lm["court"],
                    "treatment": "Followed / Relied Upon",
                    "status": lm["status"],
                    "ratio_key": lm["ratio_key"],
                    "case_id": None,
                }
                # Check if this landmark exists in DB
                matched_db_case = citation_to_case.get(lm["citation"].lower())
                if matched_db_case:
                    prec_entry["case_id"] = matched_db_case.id
                    if matched_db_case.id != c.id:
                        citation_graph[matched_db_case.id].add(c.id)

                if lm["citation"] not in seen_keys and prec_entry["case_id"] != c.id:
                    found_precedents.append(prec_entry)
                    seen_keys.add(lm["citation"])

        # Check formal law report regex patterns
        for pat in FORMAL_CITATION_PATTERNS:
            for cit in pat.findall(corpus):
                clean_cit = re.sub(r'\s+', ' ', cit).strip(' ,;()')
                if clean_cit.lower() in seen_keys:
                    continue
                seen_keys.add(clean_cit.lower())

                # Check if matches DB case
                matched_db_case = citation_to_case.get(clean_cit.lower())
                if matched_db_case:
                    if matched_db_case.id != c.id:
                        found_precedents.append({
                            "title": matched_db_case.title,
                            "citation": matched_db_case.official_citation or clean_cit,
                            "court": matched_db_case.court,
                            "treatment": "Referred / Applied",
                            "status": matched_db_case.precedential_status or "Good Law",
                            "case_id": matched_db_case.id,
                        })
                        citation_graph[matched_db_case.id].add(c.id)
                else:
                    # External authoritative precedent
                    court_guess = "Supreme Court of India" if "sc" in clean_cit.lower() else "High Court"
                    found_precedents.append({
                        "title": f"Judicial Precedent [{clean_cit}]",
                        "citation": clean_cit,
                        "court": court_guess,
                        "treatment": "Cited / Considered",
                        "status": "Good Law (External Authority)",
                        "case_id": None,
                    })

        # Save structured precedents list to case
        c.precedents_cited = found_precedents

        # Ensure sensible default for precedential status
        if not c.precedential_status or c.precedential_status.lower() in ["precedential status not checked", "none", ""]:
            c.precedential_status = "Good Law"

        if found_precedents:
            cases_with_citations += 1
            total_precedents_linked += len(found_precedents)

    # 3. Update cited_by_count on all target cases
    db_internal_links = 0
    for case_id, citing_set in citation_graph.items():
        c_target = db.query(Case).filter(Case.id == case_id).first()
        if c_target:
            c_target.cited_by_count = len(citing_set)
            if len(citing_set) > 0:
                db_internal_links += len(citing_set)

    db.commit()

    print(f"Cases with Precedents Found:     {cases_with_citations}/{len(cases)}")
    print(f"Total Precedents Linked:         {total_precedents_linked}")
    print(f"Internal Repository Cross-Links: {db_internal_links}")

    # Top cited judgments in our repository
    top_cited = db.query(Case).filter(Case.cited_by_count > 0).order_by(Case.cited_by_count.desc()).all()
    print("\n--- TOP CITED PRECEDENTS IN LEXGUARD ---")
    for tc in top_cited:
        print(f"  ★ [{tc.cited_by_count} Citations] {tc.title} ({tc.court}, {tc.year}) [{tc.official_citation or tc.case_no}]")

    db.close()
    print("\n" + "=" * 70)
    print("CITATION NETWORK GRAPH LINKING COMPLETED")
    print("=" * 70)

if __name__ == "__main__":
    main()
