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
    PROFILES as _PROFILES,
    _merge_key_sets,
    PROFILES,
    LayoutFingerprint,
    detect_case_pattern,
    profile_catalog,
    extract_pdf_text,
    _choose_page_text,
    _has_double_drawn_runs,
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
        spec = profile["key_set"]
        ids = spec if isinstance(spec, (list, tuple)) else [spec]
        assert ids, f"{profile['id']} declares no key set"
        for set_id in ids:
            assert set_id in KEY_SETS, f"{profile['id']} references missing key set {set_id}"
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


# ---------------------------------------------------------------------------
# Registry extension: key-set composition, court derivation, new templates
# ---------------------------------------------------------------------------

def test_merge_key_sets_unions_anchors_and_keeps_inputs_intact():
    """Court profiles compose a shared set with a small registry extra set."""
    base = {"identity": {"case_no": {"category": "identity", "anchors": ["A"],
                                     "window": "line", "confidence": 0.8, "note": ""}}}
    extra = {"identity": {"case_no": {"category": "identity", "anchors": ["A", "B"],
                                      "window": "line", "confidence": 0.95, "note": ""}},
             "forum": {"bench": {"category": "forum", "anchors": ["C"],
                                 "window": "line", "confidence": 0.9, "note": ""}}}
    merged = _merge_key_sets(base, extra)
    assert merged["identity"]["case_no"]["anchors"] == ["A", "B"]
    assert merged["identity"]["case_no"]["confidence"] == 0.95
    assert merged["forum"]["bench"]["anchors"] == ["C"]
    # merging must never mutate the source sets
    assert base["identity"]["case_no"]["anchors"] == ["A"]
    assert extra["identity"]["case_no"]["confidence"] == 0.95


def test_key_set_for_accepts_a_list_of_sets():
    merged = CasePatternService.key_set_for("ALLAHABAD-HC")
    common = KEY_SETS["KEY-HC-COMMON"]
    extra = KEY_SETS["KEY-EXTRA-ALLAHABAD"]
    for category, keys in extra.items():
        for key_id, spec in keys.items():
            assert key_id in merged[category], f"{category}.{key_id} lost during merge"
            for anchor in spec["anchors"]:
                assert anchor in merged[category][key_id]["anchors"]
    # every common category survives the merge
    assert set(common) <= set(merged)


def test_key_set_for_single_id_still_works():
    resolved = CasePatternService.key_set_for("MHC-PS-CORAM-ORDER")
    assert resolved == KEY_SETS["KEY-MHC-PS-CORAM"]


# --- one compact caption per registry, transcribed from the real corpus ----

REGISTRY_PIECES = {
    "BRIEF-CARD": """SUPREME COURT OF INDIA
JUDICIAL APPELLATE JURISDICTION
CASE NO: Civil Appeal No. 4531 of 2022 (YEAR: 2010)
CORAM: G.S. SINGHVI, A.K. PATNAIK, JJ.
Union of India
... Appellant(s)
Versus
Rameshwar Prasad
... Respondent(s)
Acts Referred:
Constitution of India, 1950
JUDICIAL HEADNOTE & SUMMARY
RATIO DECIDENDI
OPERATIVE ORDER
ORDER: Decided
""",
    "ALLAHABAD-HC": """HIGH COURT OF JUDICATURE AT ALLAHABAD
Neutral Citation No. - 2025:AHC-LKO:26496
Court No. - 26
APPLICATION U/S 482 No. - 15395 of 2009
Vijay Pandey And Others
... Applicant
State Of U.P. And Another
... Opposite Party
Hon'ble Vikas Kunvar Srivastav, J.
Heard learned counsel for the applicant.
Order Date :- 26.11.2021
""",
    "ALLAHABAD-CASELINE": """Court No. - 42
Case :- CRIMINAL MISC. BAIL APPLICATION No. - 9981 of 2026
Applicant :- Mohd Arif
Opposite Party :- State Of U.P.
Counsel for Applicant :- Mr. K. Kumar
Order Date :- 04.02.2026
""",
    "GAUHATI-HC": """Page No.# 1/7
GAHC020007272026
THE GAUHATI HIGH COURT
(HIGH COURT OF ASSAM, NAGALAND, MIZORAM AND ARUNACHAL PRADESH)
KOHIMA BENCH
Case No. : Bail Appln./24/2026
Mr. X
... Petitioner
-Versus-
State of Nagaland
... Respondent
Heard Mr. A, learned counsel for the petitioner.
""",
    "CALCUTTA-HC": """22.10.2026
274
Ct.-7
(NMD/D.Hira)
WPA 24114 of 2026
IN THE HIGH COURT AT CALCUTTA
Constitutional Writ Jurisdiction
Appellate Side
Between:
Bangarh Scholar Teachers Training Institute
-Vs-
State of West Bengal & Ors.
""",
    "CALCUTTA-CAUSELIST": """22.10.2026
Sl. No. 277 (DL)
Ct.No.07
(M.D./S.M)
WPA 27867 of 2026
Tafijul Hoque
Vs.
State of West Bengal & Ors.
Mr. C.R. Chakraborty ...for the petitioner
1. The petitioner and the State are represented.
""",
    "TELANGANA-HC": """[ 3383 ]
IN THE HIGH COURT FOR THE STATE OF TELANGANA
AT HYDERABAD
(Special Original Jurisdiction)
TUESDAY, THE FIFTEENTH DAY OF SEPTEMBER, 2026
PRESENT
THE HONOURABLE SRI JUSTICE K. LAKSHMAN
WRIT PETITION No. 24367 of 2026
Between:
M/s. Alpha Traders
... Petitioner
And
State of Telangana
... Respondent
""",
    "ANDHRA-HC": """APHC010456352026
IN THE HIGH COURT OF ANDHRA PRADESH AT AMARAVATI
(Special Original Jurisdiction)
WEDNESDAY, THE 2nd DAY OF SEPTEMBER, 2026
PRESENT
THE HONOURABLE SRI JUSTICE D.V.S.S. SOMAYAJULU
WRIT PETITION No. 12345 of 2026
""",
    "RAJASTHAN-HC": """[2026:RJ-JP:42311]
HIGH COURT OF JUDICATURE FOR RAJASTHAN
BENCH AT JAIPUR
S.B. Criminal Miscellaneous Bail Application No. 1234/2026
CNR: RJHC010012342026 | URN: CRLMB / 26726U / 2026
Before Hon'ble Mr. Justice Anoop Dhand
""",
    "KARNATAKA-HC": """- 1 -
IN THE HIGH COURT OF KARNATAKA AT BENGALURU
DATED THIS THE 14TH DAY OF OCTOBER, 2026
BEFORE
THE HON'BLE MR. JUSTICE D K SINGH
WP No. 12345 of 2026 C/W WP No. 12346 of 2026
""",
    "BOMBAY-HC": """WP.358.2026.doc
Arnav
IN THE HIGH COURT OF JUDICATURE AT BOMBAY
CRIMINAL APPELLATE JURISDICTION
CRIMINAL WRIT PETITION NO. 358 OF 2026
Arnav Manish Mandhana and Anr.
.. Petitioners
Versus
Directorate of Enforcement and Anr.
.. Respondents
CORAM : MILIND N. JADHAV, J.
DATE : OCTOBER 22, 2026.
P.C.:
""",
    "BOMBAY-NEUTRAL-CITATION": """WP 207-2026
Page 1 of 10
19th October, 2026
2026:BHC-GOA:2108
1. Heard learned counsel for the petitioner.
""",
    "ORISSA-HC": """Page 1 of 3.
IN THE HIGH COURT OF ORISSA AT CUTTACK
ABLAPL No.11991 of 2026
CNR No. ODHC010797902026
Sk. Sarifuddin
..... Petitioner
Represented by Adv. - Mr. S. Das
""",
    "MEGHALAYA-HC": """Serial No.16
Regular List
HIGH COURT OF MEGHALAYA
AT SHILLONG
Date of Decision: 30.10.2026
Uploaded on: 30.10.2026
""",
    "JK-LADAKH-HC": """HIGH COURT OF JAMMU & KASHMIR AND LADAKH AT JAMMU
Uploaded on: 30.10.2026
Through: Mr. Rahul Sharma, Advocate
Rakesh Kumar
.....Appellant(s)/Petitioner(s)
v/s
Union Territory of J&K
.....Respondent(s)
""",
    "TRIPURA-HC": """TRHC010009872026
2026:THC:767
HIGH COURT OF TRIPURA
AGARTALA
Sri Bimal Das
... APPELLANT-OPPOSITE PARTY(S)
VERSUS
The State of Tripura
""",
    "UTTARAKHAND-HC": """UKHC010036772026
IN THE HIGH COURT OF UTTARAKHAND AT NAINITAL
Reserved on 28.09.2026
Delivered on 14.10.2026
Hon'ble Sushil Kumar Gupta, J.
""",
    "HIMACHAL-HC": """( 2026:HHC:40909 )
IN THE HIGH COURT OF HIMACHAL PRADESH, SHIMLA
Reserved on: 01.10.2026
Date of decision: 14.10.2026
Date of uploading on website: 15.10.2026
""",
    "JHARKHAND-HC": """2026:JHHC:31060-DB
IN THE HIGH COURT OF JHARKHAND AT RANCHI
A. B. A. No. 5013 of 2026
Ramesh Mahto
--- Petitioner
Versus
The State of Jharkhand
--- Opposite Party
""",
    "KERALA-HC": """IN THE HIGH COURT OF KERALA AT ERNAKULAM
PRESENT
THE HONOURABLE MR.JUSTICE C.S.DIAS
OP(C) NO. 3112 OF 2015
MONDAY, THE 18TH DAY OF NOVEMBER 2022 / 27TH KARTHIKA, 1944
""",
    "DELHI-HC": """$~
* IN THE HIGH COURT OF DELHI AT NEW DELHI
%                                   Reserved on: 01.10.2026
                                    Pronounced on: 14.10.2026
+   CS(COMM) 123/2026
    M/s Alpha
                                                        ..... Plaintiff
                        Through: Mr. A. Advocate
    Versus
    Beta Pvt Ltd
                                                        ..... Defendant
""",
    "DAILY-CAUSE-ORDER": """30.10.2026
Court No.8
S/L 34
SD
CRM (M) 2834 of 2026
In Re: An application for bail under Section 483 of the Bharatiya
Nagarik Suraksha Sanhita, 2023
(Allowed)
""",
    "MADRAS-SHORT-ORDER": """WMP. No.48807 of 2026 in
W.P. No.43496 of 2026
V. LAKSHMINARAYANAN,J.
Ordered.
23.10.2026
""",
    "MADRAS-REVIEW-SLIP": """17.07.2026.
Court No. 13
Item No. 1.
sp
R.V.W. 369 of 2024
With
CAN 1 of 2024
In the matter of: M/s. Alpha
""",
    "OFFICE-NOTES": """UKHC010091362026
2026:UHC:9929
Office Notes, reports,
orders or proceedings
SL. No.
Date or directions and COURT'S OR JUDGE'S ORDERS
CRLR/405/2026
Ravindra Kumar
--Revisionist
Versus
State Of Uttarakhand and Another
--Respondents
Hon'ble Siddhartha Sah, J.
""",
    "LAW-REPORT-REPRINT": """Ramakrishna Aiyar vs Narayana Aiyar on 24 February, 1800
Equivalent citations: (1897)7MLJ227
JUDGMENT
The suit was for partition of the family property.
""",
    "NON-JUDGMENT": """Legal Case Research System - Full Project Redesign
1. Project Overview & Objectives
A web-based Legal Case Research and Drafting platform.
4. Tech Stack
FastAPI, React, PostgreSQL.
5. System Architecture
""",
}


@pytest.mark.parametrize("expected_profile,text", sorted(REGISTRY_PIECES.items()))
def test_detects_registry_profile(expected_profile, text):
    detection = CasePatternService.detect_from_text(text)
    assert detection.profile_id == expected_profile, detection.profile_id
    assert detection.key_set_id in KEY_SETS


def test_brief_card_derives_the_sitting_court_from_the_caption():
    sci = CasePatternService.detect_from_text(REGISTRY_PIECES["BRIEF-CARD"])
    assert sci.court == "Supreme Court of India"

    delhi = REGISTRY_PIECES["BRIEF-CARD"].replace(
        "SUPREME COURT OF INDIA", "HIGH COURT OF DELHI")
    assert CasePatternService.detect_from_text(delhi).court == "Delhi High Court"


def test_office_notes_derive_the_court_from_the_registry_code():
    detection = CasePatternService.detect_from_text(REGISTRY_PIECES["OFFICE-NOTES"])
    assert detection.court == "Uttarakhand High Court"
    tripura = REGISTRY_PIECES["OFFICE-NOTES"].replace("UKHC010091362026", "TRHC010009872026")
    assert CasePatternService.detect_from_text(tripura).court == "Tripura High Court"


def test_every_profile_declares_a_resolvable_key_set():
    for profile in _PROFILES:
        resolved = CasePatternService.key_set_for(profile["id"])
        assert resolved, f"{profile['id']} resolved to an empty key set"
        assert "identity" in resolved or profile["id"] == "NON-JUDGMENT"


# ---------------------------------------------------------------------------
# Geometric repair gating: no false positives on clean single-column pages
# ---------------------------------------------------------------------------

class _FakePage:
    """Minimal PyMuPDF-page stand-in for offline geometry unit tests."""

    def __init__(self, raw, words, blocks, width=600.0):
        from types import SimpleNamespace
        self.rect = SimpleNamespace(width=width)
        self._raw = raw
        self._words = words
        self._blocks = blocks

    def get_text(self, mode="text"):
        if mode == "dict":
            return {"blocks": self._blocks}
        if mode == "words":
            return self._words
        return self._raw


def _clean_words(lines):
    words = []
    for row, line in enumerate(lines):
        x = 50.0
        for token in line.split():
            width = len(token) * 6.0
            words.append((x, 10.0 + row * 20, x + width, 20.0 + row * 20, token))
            x += width + 6.0
    return words


def _double_drawn_words():
    words = []
    for row, tokens in enumerate((["IN", "THE", "HIGH"], ["COURT", "OF", "JUDICATURE"])):
        x = 50.0
        y = 10.0 + row * 30
        for token in tokens:
            width = len(token) * 6.0
            words.append((x, y, x + width, y + 10, token))
            words.append((x + 1, y, x + width + 1, y + 10, token))
            x += width + 12.0
    return words


def test_double_drawn_detector_requires_a_run_not_an_isolated_overlap():
    assert _has_double_drawn_runs(_double_drawn_words()) is True
    assert _has_double_drawn_runs(_clean_words(["A clean single column line."] * 4)) is False
    # One overlapping row (a stamp/signature) is not a double-drawn text layer.
    assert _has_double_drawn_runs(_double_drawn_words()[:6]) is False


def test_choose_page_text_keeps_clean_single_column_verbatim_even_when_blocks_are_narrow():
    lines = ["This is a clean single column judgment line with enough characters."] * 4
    raw = "\n".join(lines)
    words = _clean_words(lines)
    blocks = [{"type": 0, "bbox": [50, 10 + i * 20, 150, 20 + i * 20]} for i in range(8)]
    text, repaired = _choose_page_text(_FakePage(raw, words, blocks))
    assert text == raw
    assert repaired is False


def test_choose_page_text_repairs_genuine_double_drawn_runs():
    raw = "IN\nIN THE\nTHE HIGH\nHIGH COURT\nCOURT OF\nOF JUDICATURE"
    words = _double_drawn_words()
    blocks = [{"type": 0, "bbox": [50, 10 + i * 10, 120, 20 + i * 10]} for i in range(12)]
    text, repaired = _choose_page_text(_FakePage(raw, words, blocks))
    assert repaired is True
    assert "IN THE HIGH" in text
    assert "COURT OF JUDICATURE" in text


def test_choose_page_text_repairs_double_drawn_runs_even_without_severe_clipping():
    raw = "IN\nIN THE\nTHE HIGH\nHIGH COURT\nCOURT OF\nOF JUDICATURE"
    words = _double_drawn_words()
    # Every block is wide: clipped ratio is 0, so only the overlap gate can fire.
    blocks = [{"type": 0, "bbox": [0, 10 + i * 10, 600, 20 + i * 10]} for i in range(12)]
    text, repaired = _choose_page_text(_FakePage(raw, words, blocks))
    assert repaired is True
    assert "IN THE HIGH" in text


def test_choose_page_text_severe_clipping_boundary_is_quarter_of_blocks():
    raw = "IN\n\nTHE\n\nHIGH\n\nCOURT\n"
    words = _clean_words(["IN THE HIGH COURT"])
    narrow = {"type": 0, "bbox": [50, 10, 120, 20]}
    wide = {"type": 0, "bbox": [0, 10, 600, 20]}

    # 1 / 4 == 0.25: severe clipping gate opens and the sharded layer is repaired.
    text, repaired = _choose_page_text(_FakePage(raw, words, [narrow, wide, wide, wide]))
    assert repaired is True
    assert text == "IN THE HIGH COURT"

    # 1 / 5 < 0.25 and no overlapping runs: repair must not even be accepted.
    text, repaired = _choose_page_text(_FakePage(raw, words, [narrow, wide, wide, wide, wide]))
    assert repaired is False
    assert text == raw


@pytest.mark.skipif(not corpus_available, reason="seed corpus PDFs not present")
@pytest.mark.parametrize("name", ["01_crl-a-md-1150-2026.pdf", "06_crl-op-26284-2026.pdf"])
def test_corpus_clean_madras_judgments_remain_verbatim(name):
    pymupdf = pytest.importorskip("pymupdf")
    path = os.path.join(CORPUS_DIR, name)
    text, layout, _meta = extract_pdf_text(path)
    with pymupdf.open(path) as doc:
        raw = "\n\n".join(page.get_text() for page in doc)
    assert text == raw
    assert layout.needs_geometric_repair is False
    assert layout.repaired_page_ratio == 0.0


def test_corpus_bombay_doc_double_drawn_caption_is_repaired():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "storage", "cases",
                        "BHC_2026_WP_358_2026_doc_Ajay_IINN_TTHHEE_HH_4f12d564.pdf")
    if not os.path.exists(path):
        pytest.skip("Bombay double-drawn corpus PDF not present")
    pymupdf = pytest.importorskip("pymupdf")
    text, layout, meta = extract_pdf_text(path)
    assert layout.repaired_page_ratio > 0.0
    assert "IN THE HIGH COURT OF JUDICATURE AT BOMBAY" in meta["pages"][0]
    with pymupdf.open(path) as doc:
        raw_first = doc[0].get_text()
    assert meta["pages"][0] != raw_first


def test_corpus_supreme_court_caption_text_remains_verbatim():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "storage", "cases",
                        "DHC_1973_Appeal_No_1118_of_2020_7e4f1ace.pdf")
    if not os.path.exists(path):
        pytest.skip("Supreme Court corpus PDF not present")
    pymupdf = pytest.importorskip("pymupdf")
    text, layout, _meta = extract_pdf_text(path)
    with pymupdf.open(path) as doc:
        raw = "\n\n".join(page.get_text() for page in doc)
    detection = detect_case_pattern(text)
    assert detection.court == "Supreme Court of India"
    assert text == raw
    assert layout.repaired_page_ratio == 0.0


# ---------------------------------------------------------------------------
# Structured fact sheet: police stations, crime/FIR numbers, custody/arrest
# ---------------------------------------------------------------------------

def test_fact_sheet_captures_police_station_crime_and_custody_evidence():
    text = (
        "The petitioner was arrested on 01.09.2026 in Crime No. 560/2025 registered at "
        "Mallanginar Police Station, Virudhunagar District and has been in judicial custody since then."
    )
    sheet = CasePatternService._fact_sheet(text)
    assert sheet["police_stations"] == ["Mallanginar"]
    assert "Crime No. 560/2025" in sheet["crime_numbers"]
    assert sheet["arrest"] and "01.09.2026" in sheet["arrest"]
    assert sheet["custody"] and "custody" in sheet["custody"]


def test_fact_sheet_captures_prefix_police_station_and_fir_number():
    text = (
        "FIR No. 123/2025 was registered at P.S. Kotwali, District Patna. "
        "The accused surrendered before the court on 02.01.2026 and was remanded to judicial custody."
    )
    sheet = CasePatternService._fact_sheet(text)
    assert "Kotwali" in sheet["police_stations"]
    assert "FIR No. 123/2025" in sheet["crime_numbers"]
    assert sheet["arrest"] and "surrendered" in sheet["arrest"]
    assert sheet["custody"] and "judicial custody" in sheet["custody"]


def test_extract_case_facts_merges_caption_only_police_station():
    detection = CasePatternService.detect_from_text(MADRAS_MB_CRIM_JURIS)
    result = CasePatternService.extract_case_facts(MADRAS_MB_CRIM_JURIS, detection)
    assert "Mallanginar" in result["fact_sheet"]["police_stations"]
    assert result["fact_sheet"]["crime_numbers"]
    assert result["fact_sheet"]["custody"]


def test_fact_sheet_normalizes_arrest_and_custody_status():
    text = (
        "The petitioner was arrested on 01.09.2026 in Crime No. 560/2025 and was "
        "remanded to judicial custody on 02.09.2026."
    )
    sheet = CasePatternService._fact_sheet(text)
    assert sheet["arrest_status"] == "arrested"
    assert sheet["custody_status"] == "judicial_custody"
    assert sheet["arrest"] and sheet["custody"]


def test_fact_sheet_does_not_turn_prospective_arrest_into_actual_arrest():
    text = (
        "The applicant was not arrested during investigation. The applicant fears that "
        "he may be arrested in the event of arrest being sought by the police. He is not in custody."
    )
    sheet = CasePatternService._fact_sheet(text)
    assert sheet["arrest_status"] == "not_arrested"
    assert sheet["custody_status"] == "not_in_custody"


def test_fact_sheet_uses_latest_explicit_custody_status():
    text = (
        "The accused was remanded to judicial custody on 01.09.2026. "
        "He was later released on bail on 15.09.2026."
    )
    sheet = CasePatternService._fact_sheet(text)
    assert sheet["custody_status"] == "released_on_bail"
    assert "released on bail" in sheet["custody"]


def test_fact_sheet_captures_textual_dates_cr_no_and_acronym_offences():
    text = (
        "On 9th October, 2026 the police registered Cr.No.52 of 2025 at P.S. Kotwali "
        "for the offence under Section 302 IPC. The accused was arrested on OCTOBER 10, 2026."
    )
    sheet = CasePatternService._fact_sheet(text)
    assert "9th October, 2026" in sheet["dates"]
    assert "OCTOBER 10, 2026" in sheet["dates"]
    assert any("Cr.No.52" in c for c in sheet["crime_numbers"])
    assert any("Section 302 IPC" in o for o in sheet["offences"])
    assert "Kotwali" in sheet["police_stations"]


def test_candidate_regions_cover_all_four_fact_strategies():
    seen = set()
    for fixture in PIECES.values():
        detection = CasePatternService.detect_from_text(fixture)
        keyset = CasePatternService.key_set_for(detection.profile_id)
        paragraphs = CasePatternService._paragraphs(fixture)
        seen.update(c["strategy"] for c in CasePatternService._candidate_regions(fixture, keyset, paragraphs))
    assert seen == {"explicit_heading", "anchored_span", "paragraph_scan", "post_caption_body"}


def test_post_caption_body_fallback_works_without_a_prayer_heading():
    caption = MADRAS_PS_CORAM.split("PRAYER:")[0]
    text = caption + (
        "For Petitioner(s):\nMr. A. Advocate\n\n"
        "On 09.10.2025 the respondent police registered Crime No. 120 of 2025 at "
        "Gummidipoondi Police Station and arrested the petitioner. He was remanded "
        "to judicial custody and the final report was filed on 02.04.2026.\n"
    )
    detection = CasePatternService.detect_from_text(text)
    keyset = CasePatternService.key_set_for(detection.profile_id)
    paragraphs = CasePatternService._paragraphs(text)
    strategies = {c["strategy"] for c in CasePatternService._candidate_regions(text, keyset, paragraphs)}
    assert "post_caption_body" in strategies


def test_police_station_fallback_is_caption_scoped_not_precedent_scoped():
    text = MADRAS_MB_CRIM_JURIS + "\n" + ("x" * 6500) + "\nCited Precedent Police Station Pretoria\n"
    detection = CasePatternService.detect_from_text(text)
    result = CasePatternService.extract_case_facts(text, detection)
    assert "Mallanginar" in result["fact_sheet"]["police_stations"]
    assert "Pretoria" not in result["fact_sheet"]["police_stations"]
