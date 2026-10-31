"""
Tests for the case-file pattern service.

Two layers of coverage:

1. **Synthetic caption fixtures** — one short header/body per registry template,
   written from the real corpus shapes.  These run everywhere, including CI
   machines with no PDFs and no PyMuPDF.
2. **Corpus smoke tests** — if the git-ignored seed corpus is present, verify the
   eight detected profiles, the facts-extraction contract and that the key sets
   resolve.  Skipped automatically when the corpus is absent.

Run with:  pytest backend/tests/test_case_pattern_service.py -q
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.case_pattern_service import (  # noqa: E402
    CasePatternService,
    KEY_SETS,
    PROFILES,
    LayoutFingerprint,
    detect_case_pattern,
    profile_catalog,
)

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "..", "seed_corpus", "pdfs")


# ---------------------------------------------------------------------------
# Synthetic fixtures (one per drafting template)
# ---------------------------------------------------------------------------

MADRAS_PS_CORAM = """CRL OP No. 26220 of 2026
__________
Page1 of 11
IN THE HIGH COURT OF JUDICATURE AT MADRAS
DATED:  09-10-2026
CORAM
THE HON'BLE MR.JUSTICE N.RAMESH
CRL OP No. 26220 of 2026
CNR: {HCMA012161402026}
Yuvaraj
..Petitioner(s)
Vs
The State Rep by
The Inspector of Police
PEW Gummidipoondi,
Tiruvallur District.
Crime No.120/2025.
..Respondent(s)
PRAYER: This criminal original petition filed under Section 482 BNSS Act to
enlarge the petitioner on bail in CC No.597 of 2026 in connection to the Crime
No.120 of 2025 pending on the file of the II Additional Special Judge.
For Petitioner(s):
Mr.P.Muthamizhselvakumar
For Respondent(s):
Mr.M.M.I.Khaleel
Government Advocate (Crl.Side)
ORDER
This is a petition for bail in a case under the NDPS Act ("the Act"), filed
under Section 483 of the BNSS.
2. On 09.10.2025 at about 09.00 hours, the respondent police stopped a lorry at
the Elavur check post in Crime No. 120 of 2025 and seized about 100 kilograms of ganja. The petitioner
was not in the lorry and nothing was seized from him.
3. The final report was laid on 02.04.2026 and the petitioner surrendered before
the Special Court on 16.04.2026 and was remanded to judicial custody.
4. I have heard the learned counsel appearing for the petitioner and the learned
Public Prosecutor.
JUDGE
"""

MADRAS_PS_RESERVED = """A. Nos. 3875 & 3876 of 2026 & O.A. Nos. 778 & 779 of 2026
IN THE HIGH COURT OF JUDICATURE AT MADRAS
RESERVED ON            :   01.10.2026
PRONOUNCED ON      :   09.10.2026
CORAM:
THE HONOURABLE DR. JUSTICE A.D. MARIA CLETE
A Nos. 3875 & 3876 of 2026:
Annapurna Swadisht Limited
Chatterjee International Building
..Applicant(s) in both
Vs
GEF Foods India Private Limited
15/29, Thambu Chetty Street,
..Respondent(s) in both
PRAYER IN A Nos. 3875 & 3876 of 2026:
To vacate the interim injunction granted Order dated 05.08.2026.
For Applicant(s):
Mr.Sathish Parasaran, Senior Advocate
For Respondent(s):
Mr.Arun C. Mohan
The predecessor obtained registrations Nos.988210 and 988211 in Class 30,
applied for on 06.02.2001, and copyright registration No.A-114222/2015.
2. By an Agreement and an IP Assignment Deed dated 31.01.2025 the predecessor
transferred its business, and assigned the trade marks.
JUDGE
"""

MADRAS_MB_CORAM = """CRL A(MD) No. 1150 of 2026
BEFORE THE MADURAI BENCH OF MADRAS HIGH COURT
DATED: 09-10-2026
CORAM
THE HON'BLE MR.JUSTICE S.KARTHIKEYAN
CRL A(MD) No. 1150 of 2026
CNR:{HCMD011350712026}
Karuppasamy
S/o.Manthaidurai,
Melur Taluk,
.. Appellant
Vs
1. The State of Tamil Nadu, rep by The Deputy Superintendent of Police,
Melur Taluk,
..Respondent(s)
PRAYER: Criminal Appeal filed under Section 14-A(2) of the SC/ST
(Amendment) Act, 2015, to set aside the order dated made in Cr.M.p.No.403 of
2026.
For Petitioner:
Ms.A.Rajini
ORDER
The appellant was arrested on 01.09.2026 in Crime No. 560/2025 and has been in
custody since then.
"""

MADRAS_MB_CRIM_JURIS = """CRL OP(MD). No.23127 of 2026
BEFORE THE MADURAI BENCH OF MADRAS HIGH COURT
( Criminal Jurisdiction )
Date  : 09.10.2026
PRESENT
The Hon`ble  Mr.Justice K.MURALI SHANKAR
CRL OP(MD). No.23127 of 2026
1.Jeyaprakash @ Jeyaprakashraj
2.Praveenkumar
... Petitioners/
   Accused 5 & 3
   Vs
The State of Tamil Nadu rep by
The Inspector of Police,
Mallanginar Police Station,
Virudhunagar District.
(Crime No.206 of 2026)
... Respondent/
    Complainant
  For Petitioners: Mr.G.R.Nesakkaran,
                   Advocate
  For Respondent : Mr.N.Balasubramanian,
                   Counsel for State of TN(Crl.Side)
     PETITION FOR BAIL Under Section 483 of B.N.S.S.
PRAYER :-
   For Bail in Crime No.206 of 2026 on the file of
the Respondent Police.
ORDER :  The Court made the following order :-
The petitioners / accused 5 and 3, who were
arrested and remanded to judicial custody on
17.09.2026 for the offence punishable under Section
25(1B)(b) of Arms Act, in Crime No.206 of 2026, on
the file of the respondent police, seek bail.
2. The case of the prosecution is that on
17.09.2026, at about 10.30 a.m., while the respondent
police were on patrol duty near the Devar Statue, the
petitioners were found in possession of knives.
1/6
"""

CGHC = """1


         2026:CGHC:36890


                NAFR
HIGH COURT OF CHHATTISGARH AT BILASPUR
Order Reserved on : 09.04.2026
Order passed on :  15.06.2026
WPS No. 4979 of 2022
* - Meena Dewangan D/o Bahoran Dewangan Aged About 42 Years R/o Ward
No. 2, Dongripara, Tehsil Lormi, District Mungeli, Chhattisgarh.
          --- Petitioner(s)
versus
* - State Of Chhattisgarh Through Directorate Of Women And Child
Development, Naya Raipur (C.G.)
          --- Respondent(s)
For Petitioner
:
Mr. Kaustubh Singh Thakur, Advocate
For Respondent/State
:
Mr. Rishabh Chandra Singh Deo,
Panel Lawyer
Hon'ble Shri Justice Rakesh Mohan Pandey
Order on Board
18/08/2026
1.
The petitioner has filed this petition seeking the following relief(s):-
"10.1 That, this Hon'ble Court may kindly be please to allow this present writ
petition and quash the impugned appointment order dated 27.05.2022."
2.
The facts, in brief, are that an advertisement was issued on 02.12.2021 to fill
up 200 posts of Supervisor through direct recruitment.
3.
I have heard learned counsel for the parties and perused the documents.
4.
With the aforesaid observations, the present writ petition stands dismissed.
Sd/-
  (Rakesh Mohan Pandey)
Judge
"""

PATNA = """IN THE HIGH COURT OF JUDICATURE AT PATNA
Civil Writ Jurisdiction Case No.20547 of 2018
======================================================
Vishwambhar Singh Son of Late Ram Bahadur Singh, Resident of Village-
Sanduar, District Saran at Chapra.
...  ...  Petitioner/s
Versus
1.
The State of Bihar through the Chief Secretary, Government of Bihar, Patna.
...  ...  Respondent/s
======================================================
Appearance :
For the Petitioner/s
:
 Mr. Vishwambhar Singh (In-Person)
For the Respondent/s
:
 Mr. G.P. 20
Patna High Court CWJC No.20547 of 2018 dt.23-06-2026
2/38
Brief Facts Of Case
3. The brief facts giving rise to the present writ petition are that an
advertisement was issued for 56th to 59th Combined Preliminary Competitive
Examination for 22 services, having total 746 vacancies.
Consideration and Analysis
4. Having heard the parties, this Court finds that the grievance relates to
category-wise reservation.
Patna High Court CWJC No.20547 of 2018 dt.23-06-2026
38/38
25. With the aforementioned observations and directions the present writ petition
is disposed of.
"""

PIECES = {
    "MHC-PS-CORAM-ORDER": MADRAS_PS_CORAM,
    "MHC-PS-RESERVED-JUDGMENT": MADRAS_PS_RESERVED,
    "MHC-MB-CORAM-ORDER": MADRAS_MB_CORAM,
    "MHC-MB-CRIM-JURIS": MADRAS_MB_CRIM_JURIS,
    "CGHC-BILASPUR-ORDER": CGHC,
    "PATNA-CWJC-JUDGMENT": PATNA,
}


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------

def test_profile_catalog_is_self_consistent():
    catalog = profile_catalog()
    ids = [profile["id"] for profile in catalog]
    assert len(ids) == len(set(ids)), "profile ids must be unique"
    assert "GENERIC-HC" in ids
    for profile in catalog:
        assert profile["key_set"] in KEY_SETS, f"{profile['id']} references a missing key set"
        assert profile["facts_strategy"], f"{profile['id']} must declare a facts strategy"


def test_every_key_has_anchors_and_confidence():
    for set_id, keyset in KEY_SETS.items():
        for category, keys in keyset.items():
            assert keys, f"{set_id}.{category} is empty"
            for key_id, spec in keys.items():
                assert spec["anchors"], f"{set_id}.{category}.{key_id} has no anchors"
                assert 0 < spec["confidence"] <= 1.0
                for anchor in spec["anchors"]:
                    # compiling now surfaces a broken anchor at test time, not in prod
                    import re
                    re.compile(anchor)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("expected_profile,text", sorted(PIECES.items()))
def test_detects_expected_profile_from_caption(expected_profile, text):
    detection = CasePatternService.detect_from_text(text)
    assert detection.profile_id == expected_profile
    assert detection.confidence >= 0.55
    assert detection.key_set_id in KEY_SETS


def test_madurai_branch_of_madras_is_not_confused_with_principal_seat():
    principal = detect_case_pattern(MADRAS_PS_CORAM)
    madurai = detect_case_pattern(MADRAS_MB_CORAM)
    assert principal.seat == "Principal Seat, Chennai"
    assert madurai.seat == "Madurai Bench"


def test_unknown_text_falls_back_to_generic():
    detection = detect_case_pattern("Some order text without any registry caption at all.")
    assert detection.profile_id == "GENERIC-HC"
    assert detection.confidence == 0.0


def test_layout_signals_influence_detection():
    text = MADRAS_MB_CRIM_JURIS
    layout = LayoutFingerprint(mono_ratio=0.9, layout_signals=["layout:mono_font"], has_text_layer=True)
    detection = CasePatternService.detect(text, layout=layout)
    assert detection.profile_id == "MHC-MB-CRIM-JURIS"
    assert "layout:mono_font" in detection.layout_signals


# ---------------------------------------------------------------------------
# Key sets / shortlisting
# ---------------------------------------------------------------------------

def test_shortlist_reports_caption_scoped_identity():
    detection = CasePatternService.detect_from_text(MADRAS_PS_CORAM)
    hits = CasePatternService.shortlist_keys(MADRAS_PS_CORAM, detection)
    case_hits = [h for h in hits["identity"] if h["key"] == "case_no"]
    assert case_hits and case_hits[0]["in_caption"] is True


def test_noise_patterns_are_stripped():
    detection = CasePatternService.detect_from_text(MADRAS_PS_CORAM)
    cleaned = CasePatternService.clean_text(MADRAS_PS_CORAM, None, detection)
    assert "Page1 of 11" not in cleaned
    assert "__________" not in cleaned


def test_judge_name_cleanup():
    clean = CasePatternService._clean_judge_name
    assert clean("THE HON'BLE MR.JUSTICE N.RAMESH") == "N.RAMESH"
    assert clean("HON'BLE MS. JUSTICE NIDHI GUPTA Present") == "NIDHI GUPTA"
    assert clean("HONOURABLE MR. JUSTICE RITESH KUMAR CAV JUDGMENT Date") == "RITESH KUMAR"
    assert clean("") is None


# ---------------------------------------------------------------------------
# Sections and facts
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("profile_id,fixture", sorted(PIECES.items()))
def test_facts_extraction_contract(profile_id, fixture):
    detection = CasePatternService.detect_from_text(fixture)
    result = CasePatternService.extract_case_facts(fixture, detection)
    assert set(result) >= {"facts", "facts_strategy", "facts_anchor", "fact_sheet", "confidence"}
    assert result["fact_sheet"].keys() >= {"dates", "crime_numbers", "places", "offences"}
    if result["facts"]:
        assert len(result["facts"]) <= CasePatternService.FACT_CAP
        assert result["confidence"] > 0


def test_facts_prefer_dated_narrative_over_caption():
    detection = CasePatternService.detect_from_text(MADRAS_PS_CORAM)
    facts = CasePatternService.extract_case_facts(MADRAS_PS_CORAM, detection)
    assert facts["facts"]
    assert "..Petitioner" not in facts["facts"]
    assert "seized about 100 kilograms of ganja" in facts["facts"]
    assert facts["fact_sheet"]["dates"], "incident dates should be captured"
    assert any("Crime" in c for c in facts["fact_sheet"]["crime_numbers"])


def test_explicit_facts_heading_is_used_when_present():
    detection = CasePatternService.detect_from_text(PATNA)
    facts = CasePatternService.extract_case_facts(PATNA, detection)
    assert facts["facts_strategy"] == "explicit_heading"
    assert "advertisement was issued" in facts["facts"]


def test_section_map_respects_unit_caps():
    detection = CasePatternService.detect_from_text(MADRAS_PS_CORAM)
    sections = CasePatternService.map_sections(MADRAS_PS_CORAM, detection)
    assert "units" in sections
    for unit, payload in sections.items():
        if unit == "units":
            continue
        assert payload["length"] <= CasePatternService.UNIT_CAPS[unit]


def test_caption_parties_extraction():
    detection = CasePatternService.detect_from_text(CGHC)
    parties = CasePatternService.extract_caption_parties(CGHC, detection)
    assert parties["petitioner"] == "Meena Dewangan"
    assert parties["respondent"].startswith("State Of Chhattisgarh")


# ---------------------------------------------------------------------------
# Corpus smoke tests (skipped when the git-ignored PDFs are absent)
# ---------------------------------------------------------------------------

corpus_available = os.path.isdir(CORPUS_DIR) and any(
    name.lower().endswith(".pdf") for name in os.listdir(CORPUS_DIR)
)


@pytest.mark.skipif(not corpus_available, reason="seed corpus PDFs not present")
def test_corpus_profiles_cover_all_registries():
    reports = []
    for name in sorted(os.listdir(CORPUS_DIR)):
        if name.lower().endswith(".pdf"):
            reports.append(CasePatternService.analyse_pdf(os.path.join(CORPUS_DIR, name)))
    assert len(reports) >= 25
    profiles = {report["profile"]["profile_id"] for report in reports}
    assert {"MHC-PS-CORAM-ORDER", "MHC-MB-CORAM-ORDER", "MHC-MB-CRIM-JURIS",
            "CGHC-BILASPUR-ORDER", "PATNA-CWJC-JUDGMENT"} <= profiles
    for report in reports:
        assert report["profile"]["confidence"] >= 0.55
        assert report["key_coverage"]["found"] >= 5


@pytest.mark.skipif(not corpus_available, reason="seed corpus PDFs not present")
def test_corpus_repaired_layout_recovers_punjab_caption():
    report = CasePatternService.analyse_pdf(os.path.join(CORPUS_DIR, "28_cwp-1744-2024-ph.pdf"))
    assert report["profile"]["profile_id"] == "PHHC-CWP-COLUMNAR"
    assert report["layout"]["needs_geometric_repair"] is True
    assert report["layout"]["repaired_page_ratio"] >= 0.3
