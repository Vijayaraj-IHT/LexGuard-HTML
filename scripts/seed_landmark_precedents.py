"""
Seed Top 15 Landmark Supreme Court Judgments (Precedential Anchors)
===================================================================
Generates authentic PDFs using ReportLab, computes SHA-256 seals,
registers canonical records in PostgreSQL, and establishes the foundation
for the LexGuard two-way precedent citation network.
"""

import os
import sys
import uuid
import hashlib
import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))
from app.core.database import SessionLocal
from app.models.case import Case
from app.services.audit_service import get_chain_head_hash, build_audit_entry
from app.models.document_version import DocumentVersion
from app.models.audit_log import AuditLog
from app.models.user import User

TARGET_DIRS = [
    r"e:\SEM 5 PROJECT\Lexguard\backend\storage\cases",
    r"e:\SEM 5 PROJECT\Lexguard\storage\cases",
    r"e:\SEM 5 PROJECT\LexGuard-HTML\storage\cases",
    r"e:\SEM 5 PROJECT\LexGuard-HTML\backend\storage\cases",
]

LANDMARKS_DATA = [
    {
        "id": "11111111-0001-4000-8000-000000000001",
        "case_no": "Writ Petition (Crl.) No. 68 of 2008",
        "cnr_number": "SCIN010000682008",
        "title": "Lalita Kumari v. Government of Uttar Pradesh and Others",
        "court": "Supreme Court of India",
        "year": 2014,
        "decision_date": datetime.date(2013, 11, 12),
        "judge": "Hon'ble P. Sathasivam, C.J., B.S. Chauhan, Ranjana P. Desai, Ranjan Gogoi, S.A. Bobde, JJ.",
        "bench_type": "Constitution Bench (5 Judges)",
        "petitioner": "Lalita Kumari",
        "respondent": "Government of Uttar Pradesh & Others",
        "petitioner_counsel": "Senior Advocate Colin Gonsalves",
        "respondent_counsel": "Solicitor General of India",
        "legal_domain": "Criminal Procedure & Police Powers",
        "act_tags": ["Code of Criminal Procedure, 1973", "Indian Penal Code, 1860"],
        "section_tags": ["Section 154 CrPC", "Section 156(3) CrPC", "Section 157 CrPC"],
        "keyword_tags": ["mandatory FIR", "cognizable offence", "preliminary inquiry", "Section 154 CrPC", "police duty"],
        "summary": "Five-Judge Constitution Bench ruling declaring that registration of FIR under Section 154 CrPC is mandatory upon receipt of information disclosing commission of a cognizable offence.",
        "layman_summary": "Police officers are legally obligated to register an FIR whenever someone reports a serious crime. Preliminary inquiry is only allowed in exceptional cases like matrimonial disputes, medical negligence, or corruption.",
        "outcome": "Guidelines Issued",
        "disposition": "Petition Disposed with Binding Directions",
        "ratio_decidendi": "Registration of FIR is mandatory under Section 154 of the Code if the information discloses commission of a cognizable offence and no preliminary inquiry is permissible in such a situation. If the information does not disclose a cognizable offence but indicates the necessity for an inquiry, a preliminary inquiry may be conducted only to ascertain whether a cognizable offence is disclosed or not within a maximum period of seven days.",
        "precedential_status": "Good Law (Binding Precedent)",
        "official_citation": "(2014) 2 SCC 1",
        "filename": "SC_2014_WP_Crl_No_68_of_2008_11110001.pdf",
    },
    {
        "id": "11111111-0002-4000-8000-000000000002",
        "case_no": "SLP (Crl.) No. 5191 of 2021",
        "cnr_number": "SCIN010051912021",
        "title": "Satender Kumar Antil v. Central Bureau of Investigation & Another",
        "court": "Supreme Court of India",
        "year": 2022,
        "decision_date": datetime.date(2022, 7, 11),
        "judge": "Hon'ble Sanjay Kishan Kaul & M.M. Sundresh, JJ.",
        "bench_type": "Division Bench (2 Judges)",
        "petitioner": "Satender Kumar Antil",
        "respondent": "Central Bureau of Investigation & Another",
        "petitioner_counsel": "Senior Advocate Sidharth Luthra",
        "respondent_counsel": "Additional Solicitor General S.V. Raju",
        "legal_domain": "Bail & Custodial Jurisprudence",
        "act_tags": ["Code of Criminal Procedure, 1973", "Prevention of Money Laundering Act, 2002"],
        "section_tags": ["Section 41 CrPC", "Section 41A CrPC", "Section 88 CrPC", "Section 170 CrPC", "Section 437 CrPC", "Section 439 CrPC"],
        "keyword_tags": ["bail guidelines", "Section 41A notice", "non-arrest during investigation", "personal liberty", "undertrial prisoner"],
        "summary": "Landmark ruling laying down comprehensive categorization of offences (Categories A to D) and mandating grant of bail/release on appearance without custody if the accused cooperated during investigation.",
        "layman_summary": "If an accused cooperated during police investigation and was not arrested before the chargesheet was filed, the court should grant bail or release them on personal bond without sending them to jail.",
        "outcome": "Directions Issued",
        "disposition": "Comprehensive Bail Guidelines Affirmed",
        "ratio_decidendi": "When an accused is not arrested during investigation and has cooperated with the investigating agency, on filing of the charge sheet under Section 170 CrPC, the court must issue summons or bailable warrant in the first instance. Accused persons under Category A offences (punishable up to 7 years) are entitled to be released on bail/bonds without mechanical custodial remand.",
        "precedential_status": "Good Law (Binding Precedent)",
        "official_citation": "(2022) 10 SCC 51",
        "filename": "SC_2022_SLP_Crl_No_5191_of_2021_11110002.pdf",
    },
    {
        "id": "11111111-0003-4000-8000-000000000003",
        "case_no": "Criminal Appeal No. 1277 of 2014",
        "cnr_number": "SCIN010012772014",
        "title": "Arnesh Kumar v. State of Bihar & Another",
        "court": "Supreme Court of India",
        "year": 2014,
        "decision_date": datetime.date(2014, 7, 2),
        "judge": "Hon'ble Chandramauli Kr. Prasad & Pinaki Chandra Ghose, JJ.",
        "bench_type": "Division Bench (2 Judges)",
        "petitioner": "Arnesh Kumar",
        "respondent": "State of Bihar & Another",
        "petitioner_counsel": "Advocate Kumar Shivam",
        "respondent_counsel": "Advocate Gopal Singh",
        "legal_domain": "Criminal Law & Arrest Safeguards",
        "act_tags": ["Code of Criminal Procedure, 1973", "Indian Penal Code, 1860"],
        "section_tags": ["Section 41 CrPC", "Section 41A CrPC", "Section 498A IPC", "Section 4 Dowry Prohibition Act"],
        "keyword_tags": ["arrest checklist", "Section 498A IPC", "harassment", "magistrate remand scrutiny", "preventing routine arrest"],
        "summary": "Mandatory safeguards restraining routine and mechanical arrests under Section 498-A IPC and offences punishable with imprisonment up to 7 years without satisfying Section 41 CrPC checklist.",
        "layman_summary": "Police cannot arrest individuals automatically upon filing of a matrimonial dispute or complaint for offences carrying less than 7 years. They must serve a Section 41A notice to appear first.",
        "outcome": "Allowed",
        "disposition": "Arrest Guidelines Enacted Nationwide",
        "ratio_decidendi": "Police officers shall not automatically arrest the accused when a case under Section 498-A IPC or offences punishable with imprisonment for a term which may be less than seven years is registered. Police must satisfy themselves about the necessity of arrest based on the parameters in Section 41 CrPC, furnish a checklist, and magistrates must record satisfaction before authorizing detention.",
        "precedential_status": "Good Law (Binding Precedent)",
        "official_citation": "(2014) 8 SCC 273",
        "filename": "SC_2014_Crl_A_No_1277_of_2014_11110003.pdf",
    },
    {
        "id": "11111111-0004-4000-8000-000000000004",
        "case_no": "Civil Appeal No. 5412 of 1990",
        "cnr_number": "SCIN010054121990",
        "title": "State of Haryana and Others v. Bhajan Lal and Others",
        "court": "Supreme Court of India",
        "year": 1992,
        "decision_date": datetime.date(1990, 11, 21),
        "judge": "Hon'ble S. Ratnavel Pandian & K. Jayachandra Reddy, JJ.",
        "bench_type": "Division Bench (2 Judges)",
        "petitioner": "State of Haryana and Others",
        "respondent": "Ch. Bhajan Lal and Others",
        "petitioner_counsel": "Senior Advocate K. Parasaran",
        "respondent_counsel": "Senior Advocate R.K. Garg",
        "legal_domain": "Inherent Powers & Criminal Quashing",
        "act_tags": ["Code of Criminal Procedure, 1973", "Prevention of Corruption Act, 1947"],
        "section_tags": ["Section 482 CrPC", "Article 226", "Section 154 CrPC", "Section 157 CrPC"],
        "keyword_tags": ["quashing of FIR", "Section 482 CrPC", "inherent powers", "seven categories", "malicious prosecution"],
        "summary": "The locus classicus establishing seven definitive categories of cases where High Courts may exercise inherent jurisdiction under Section 482 CrPC or extraordinary powers under Article 226 to quash criminal proceedings.",
        "layman_summary": "The master judgment used by courts across India to dismiss groundless, malicious, or fabricated criminal cases when the allegations even if accepted as true do not disclose any offence.",
        "outcome": "Allowed in Part",
        "disposition": "Seven Guiding Principles for Section 482 Formulated",
        "ratio_decidendi": "Where the allegations made in the first information report or the complaint, even if they are taken at their face value and accepted in their entirety, do not prima facie constitute any offence or make out a case against the accused, or where criminal proceeding is manifestly attended with mala fide and/or instituted maliciously with an ulterior motive, the High Court has inherent power under Section 482 CrPC to quash the proceedings.",
        "precedential_status": "Good Law (Binding Precedent)",
        "official_citation": "1992 Supp (1) SCC 335",
        "filename": "SC_1992_Civil_Appeal_No_5412_of_1990_11110004.pdf",
    },
    {
        "id": "11111111-0005-4000-8000-000000000005",
        "case_no": "Writ Petition (Crl.) No. 592 of 1987",
        "cnr_number": "SCIN010005921987",
        "title": "D.K. Basu v. State of West Bengal",
        "court": "Supreme Court of India",
        "year": 1997,
        "decision_date": datetime.date(1996, 12, 18),
        "judge": "Hon'ble Kuldip Singh & Dr. A.S. Anand, JJ.",
        "bench_type": "Division Bench (2 Judges)",
        "petitioner": "D.K. Basu, Ashok K. Johri",
        "respondent": "State of West Bengal & State of U.P.",
        "petitioner_counsel": "Senior Advocate Abhishek Manu Singhvi (Amicus Curiae)",
        "respondent_counsel": "Advocate General of West Bengal",
        "legal_domain": "Human Rights & Custodial Justice",
        "act_tags": ["Constitution of India", "Code of Criminal Procedure, 1973"],
        "section_tags": ["Article 21", "Article 22", "Section 50 CrPC", "Section 54 CrPC", "Section 57 CrPC"],
        "keyword_tags": ["custodial torture", "arrest memo", "medical examination", "fundamental rights", "Article 21"],
        "summary": "Framed mandatory 11-point procedural requirements to be followed in all cases of arrest or detention to eradicate custodial violence and uphold Articles 21 and 22.",
        "layman_summary": "Police must prepare an arrest memo, inform a family member of the arrest, conduct medical examinations every 48 hours, and allow the arrested person to consult an advocate.",
        "outcome": "Directions Issued",
        "disposition": "Eleven Mandatory Arrest Guidelines Codified",
        "ratio_decidendi": "Custodial violence, including torture and death in the lock-up, strikes a blow at the rule of law. The requirements of preparing an arrest memo, informing a relative or friend, conducting medical examination by a trained doctor, and entering details in the police station diary are mandatory and failure to comply entails contempt of court and departmental action.",
        "precedential_status": "Good Law (Binding Precedent)",
        "official_citation": "(1997) 1 SCC 416",
        "filename": "SC_1997_WP_Crl_No_592_of_1987_11110005.pdf",
    },
    {
        "id": "11111111-0006-4000-8000-000000000006",
        "case_no": "Criminal Appeal No. 1020 of 2010",
        "cnr_number": "SCIN010010202010",
        "title": "Rangappa v. Sri Mohan",
        "court": "Supreme Court of India",
        "year": 2010,
        "decision_date": datetime.date(2010, 5, 7),
        "judge": "Hon'ble K.G. Balakrishnan, C.J., P. Sathasivam, J.M. Panchal, JJ.",
        "bench_type": "Full Bench (3 Judges)",
        "petitioner": "Rangappa",
        "respondent": "Sri Mohan",
        "petitioner_counsel": "Advocate S.N. Bhat",
        "respondent_counsel": "Advocate Anand Sanjay M. Nuli",
        "legal_domain": "Negotiable Instruments & Commercial Offences",
        "act_tags": ["Negotiable Instruments Act, 1881"],
        "section_tags": ["Section 138 NI Act", "Section 139 NI Act", "Section 118 NI Act"],
        "keyword_tags": ["cheque dishonour", "Section 139 presumption", "legally enforceable debt", "preponderance of probabilities"],
        "summary": "Three-Judge Bench ruling holding that the statutory presumption mandated under Section 139 NI Act includes the existence of a legally enforceable debt, which can be rebutted on preponderance of probabilities.",
        "layman_summary": "In cheque bounce cases, the court presumes the cheque was issued for a valid debt. The drawer does not need absolute proof to defend themselves, but only needs to raise a probable doubt.",
        "outcome": "Allowed",
        "disposition": "Conviction Set Aside under Section 138",
        "ratio_decidendi": "The presumption mandated by Section 139 of the Act does indeed include the existence of a legally enforceable debt or liability. However, the standard of proof for rebutting the presumption is that of preponderance of probabilities. The accused can rely on the materials submitted by the complainant in order to raise such a defence and it is conceivable that in some cases the accused may not need to adduce evidence of his own.",
        "precedential_status": "Good Law (Binding 3-Judge Precedent)",
        "official_citation": "(2010) 11 SCC 441",
        "filename": "SC_2010_Crl_A_No_1020_of_2010_11110006.pdf",
    },
    {
        "id": "11111111-0007-4000-8000-000000000007",
        "case_no": "SLP (Crl.) No. 8989 of 2010",
        "cnr_number": "SCIN010089892010",
        "title": "Gian Singh v. State of Punjab and Another",
        "court": "Supreme Court of India",
        "year": 2012,
        "decision_date": datetime.date(2012, 9, 24),
        "judge": "Hon'ble R.M. Lodha, T.S. Thakur, Anil R. Dave, JJ.",
        "bench_type": "Full Bench (3 Judges)",
        "petitioner": "Gian Singh",
        "respondent": "State of Punjab and Another",
        "petitioner_counsel": "Senior Advocate KTS Tulsi",
        "respondent_counsel": "Advocate Kuldip Singh",
        "legal_domain": "Inherent Powers & Criminal Settlement",
        "act_tags": ["Code of Criminal Procedure, 1973", "Indian Penal Code, 1860"],
        "section_tags": ["Section 482 CrPC", "Section 320 CrPC"],
        "keyword_tags": ["compromise quashing", "non-compoundable offence", "Section 482 CrPC", "amicable settlement", "private dispute"],
        "summary": "Three-Judge Bench upholding the inherent power of the High Court under Section 482 CrPC to quash criminal proceedings in non-compoundable offences having predominantly civil or personal character upon genuine compromise.",
        "layman_summary": "If both sides in a private or commercial dispute have settled their grievances peacefully, the High Court can quash the criminal case even if the offence is officially non-compoundable.",
        "outcome": "Clarified",
        "disposition": "Quashing on Amicable Compromise Affirmed",
        "ratio_decidendi": "The power of the High Court in quashing a criminal proceeding or FIR or complaint in exercise of its inherent jurisdiction is distinct and different from the power given to a criminal court for compounding the offences under Section 320 of the Code. In offences arising from commercial, financial, mercantile, civil, partnership or such like transactions or the offences arising out of matrimony relating to dowry, etc. or family disputes where the wrong is basically private or personal and parties have resolved their dispute, the High Court may quash proceedings.",
        "precedential_status": "Good Law (Binding 3-Judge Precedent)",
        "official_citation": "(2012) 10 SCC 303",
        "filename": "SC_2012_SLP_Crl_No_8989_of_2010_11110007.pdf",
    },
    {
        "id": "11111111-0008-4000-8000-000000000008",
        "case_no": "Writ Petition No. 231 of 1977",
        "cnr_number": "SCIN010002311977",
        "title": "Maneka Gandhi v. Union of India and Another",
        "court": "Supreme Court of India",
        "year": 1978,
        "decision_date": datetime.date(1978, 1, 25),
        "judge": "Hon'ble M.H. Beg, C.J., Y.V. Chandrachud, P.N. Bhagwati, V.R. Krishna Iyer, N.L. Untwalia, S. Murtaza Fazal Ali, P.S. Kailasam, JJ.",
        "bench_type": "Constitution Bench (7 Judges)",
        "petitioner": "Maneka Gandhi",
        "respondent": "Union of India and Another",
        "petitioner_counsel": "Senior Advocate Fali S. Nariman",
        "respondent_counsel": "Attorney General S.V. Gupte",
        "legal_domain": "Constitutional Law & Fundamental Rights",
        "act_tags": ["Constitution of India", "Passports Act, 1967"],
        "section_tags": ["Article 21", "Article 14", "Article 19", "Section 10(3)(c) Passports Act"],
        "keyword_tags": ["right to travel", "Article 21 due process", "golden triangle", "natural justice", "audi alteram partem"],
        "summary": "Seven-Judge Bench ruling revolutionizing Article 21 by establishing that 'procedure established by law' must be just, fair, and reasonable, and not arbitrary or oppressive.",
        "layman_summary": "The government cannot restrict a citizen's passport or personal liberty arbitrarily. The legal procedure must be completely fair, non-discriminatory, and respect natural justice.",
        "outcome": "Allowed in Principle",
        "disposition": "Passport Impounding Quashed & Principles Affirmed",
        "ratio_decidendi": "The principle of reasonableness, which legally as well as philosophically, is an essential element of equality or non-arbitrariness pervades Article 14 like a brooding omnipresence and the procedure contemplated by Article 21 must answer the test of reasonableness in order to be in conformity with Article 14. It must be 'right and just and fair' and not arbitrary, fanciful or oppressive.",
        "precedential_status": "Good Law (Foundational 7-Judge Landmark)",
        "official_citation": "(1978) 1 SCC 248",
        "filename": "SC_1978_Writ_Petition_No_231_of_1977_11110008.pdf",
    },
    {
        "id": "11111111-0009-4000-8000-000000000009",
        "case_no": "Writ Petition (Civil) No. 494 of 2012",
        "cnr_number": "SCIN010004942012",
        "title": "Justice K.S. Puttaswamy (Retd.) and Another v. Union of India and Others",
        "court": "Supreme Court of India",
        "year": 2017,
        "decision_date": datetime.date(2017, 8, 24),
        "judge": "9-Judge Constitution Bench (per J.S. Khehar, C.J., J. Chelameswar, S.A. Bobde, R.K. Agrawal, Rohinton Fali Nariman, A.M. Sapre, D.Y. Chandrachud, Sanjay Kishan Kaul, S. Abdul Nazeer, JJ.)",
        "bench_type": "Constitution Bench (9 Judges)",
        "petitioner": "Justice K.S. Puttaswamy (Retd.)",
        "respondent": "Union of India and Others",
        "petitioner_counsel": "Senior Advocates Shyam Divan, Gopal Subramanium, Arvind Datar",
        "respondent_counsel": "Attorney General K.K. Venugopal, ASG Tushar Mehta",
        "legal_domain": "Constitutional Law & Digital Rights",
        "act_tags": ["Constitution of India", "Information Technology Act, 2000"],
        "section_tags": ["Article 21", "Article 14", "Article 19", "Article 12"],
        "keyword_tags": ["right to privacy", "fundamental right", "informational privacy", "biometrics", "proportionality test"],
        "summary": "Unanimous Nine-Judge Constitution Bench holding that the Right to Privacy is a fundamental right protected intrinsically under Article 21 and Part III of the Constitution.",
        "layman_summary": "Every Indian citizen possesses an inherent fundamental right to privacy, shielding their bodily autonomy, personal choices, and digital data from unjustified surveillance.",
        "outcome": "Allowed",
        "disposition": "Right to Privacy Affirmed as Fundamental Right",
        "ratio_decidendi": "The right to privacy is protected as an intrinsic part of the right to life and personal liberty under Article 21 and as a part of the freedoms guaranteed by Part III of the Constitution. Privacy has both positive and negative contents. Any encroachment by the State must satisfy the three-fold test of legality, legitimate state aim, and proportionality.",
        "precedential_status": "Good Law (Unanimous 9-Judge Benchmark)",
        "official_citation": "(2017) 10 SCC 1",
        "filename": "SC_2017_WP_Civil_No_494_of_2012_11110009.pdf",
    },
    {
        "id": "11111111-0010-4000-8000-000000000010",
        "case_no": "Criminal Appeal No. 335 of 1978",
        "cnr_number": "SCIN010003351978",
        "title": "Gurbaksh Singh Sibbia and Others v. State of Punjab",
        "court": "Supreme Court of India",
        "year": 1980,
        "decision_date": datetime.date(1980, 4, 9),
        "judge": "Hon'ble Y.V. Chandrachud, C.J., P.N. Bhagwati, N.L. Untwalia, R.S. Pathak, O. Chinnappa Reddy, JJ.",
        "bench_type": "Constitution Bench (5 Judges)",
        "petitioner": "Gurbaksh Singh Sibbia and Others",
        "respondent": "State of Punjab",
        "petitioner_counsel": "Senior Advocate Soli J. Sorabjee",
        "respondent_counsel": "Advocate General of Punjab",
        "legal_domain": "Anticipatory Bail Jurisprudence",
        "act_tags": ["Code of Criminal Procedure, 1973"],
        "section_tags": ["Section 438 CrPC", "Section 437 CrPC", "Article 21"],
        "keyword_tags": ["anticipatory bail", "judicial discretion", "personal liberty", "Section 438 CrPC", "freedom from custody"],
        "summary": "Five-Judge Constitution Bench holding that judicial discretion under Section 438 CrPC to grant anticipatory bail must remain wide and untrammeled by judicially created rigid conditions.",
        "layman_summary": "High Courts and Sessions Courts possess broad authority to grant anticipatory bail to protect citizens against unjustified arrests; courts should not place artificial limits on this power.",
        "outcome": "Allowed",
        "disposition": "Anticipatory Bail Scope Expanded",
        "ratio_decidendi": "Section 438 is a procedural provision which is concerned with the personal liberty of each individual citizen. It confers wide powers on the High Court and the Court of Session to grant anticipatory bail and that discretion, by its very nature, cannot be circumscribed by any rigid, iron formula or cast in a stone jacket.",
        "precedential_status": "Good Law (5-Judge Constitution Bench Precedent)",
        "official_citation": "(1980) 2 SCC 565",
        "filename": "SC_1980_Crl_A_No_335_of_1978_11110010.pdf",
    },
    {
        "id": "11111111-0011-4000-8000-000000000011",
        "case_no": "Special Leave Petition (Crl.) Nos. 7281-7282 of 2017",
        "cnr_number": "SCIN010072812017",
        "title": "Sushila Aggarwal and Others v. State (NCT of Delhi) and Another",
        "court": "Supreme Court of India",
        "year": 2020,
        "decision_date": datetime.date(2020, 1, 29),
        "judge": "Hon'ble Arun Mishra, Indira Banerjee, Vineet Saran, M.R. Shah, S. Ravindra Bhat, JJ.",
        "bench_type": "Constitution Bench (5 Judges)",
        "petitioner": "Sushila Aggarwal and Others",
        "respondent": "State (NCT of Delhi) and Another",
        "petitioner_counsel": "Senior Advocate Harin P. Raval",
        "respondent_counsel": "Solicitor General Tushar Mehta",
        "legal_domain": "Anticipatory Bail Duration",
        "act_tags": ["Code of Criminal Procedure, 1973"],
        "section_tags": ["Section 438 CrPC", "Section 173(2) CrPC"],
        "keyword_tags": ["duration of anticipatory bail", "chargesheet filing", "trial duration", "Section 438 CrPC", "liberty protection"],
        "summary": "Five-Judge Constitution Bench settling the law that anticipatory bail does not automatically terminate upon filing of the chargesheet and normally continues till the conclusion of trial.",
        "layman_summary": "Once a court grants anticipatory bail, that protection usually lasts throughout the entire criminal trial, not just until the police complete their investigation.",
        "outcome": "Answered in Affirmative",
        "disposition": "Anticipatory Bail Life Sustained Till End of Trial",
        "ratio_decidendi": "The protection granted to a person under Section 438 CrPC should not invariably be limited to a fixed period; it should inure in favour of the accused without any restriction on time and normally endure till the conclusion of trial. The mere filing of a charge sheet does not automatically compel the accused to surrender and apply for regular bail.",
        "precedential_status": "Good Law (5-Judge Constitution Bench)",
        "official_citation": "(2020) 5 SCC 1",
        "filename": "SC_2020_SLP_Crl_Nos_7281_7282_of_2017_11110011.pdf",
    },
    {
        "id": "11111111-0012-4000-8000-000000000012",
        "case_no": "Writ Petition (Criminal) No. 167 of 2012",
        "cnr_number": "SCIN010001672012",
        "title": "Shreya Singhal v. Union of India",
        "court": "Supreme Court of India",
        "year": 2015,
        "decision_date": datetime.date(2015, 3, 24),
        "judge": "Hon'ble J. Chelameswar & Rohinton Fali Nariman, JJ.",
        "bench_type": "Division Bench (2 Judges)",
        "petitioner": "Shreya Singhal",
        "respondent": "Union of India",
        "petitioner_counsel": "Senior Advocates Soli J. Sorabjee, Mukul Rohatgi",
        "respondent_counsel": "Additional Solicitor General Tushar Mehta",
        "legal_domain": "Free Speech & Cyber Jurisprudence",
        "act_tags": ["Information Technology Act, 2000", "Constitution of India"],
        "section_tags": ["Section 66A IT Act", "Section 79 IT Act", "Article 19(1)(a)", "Article 19(2)"],
        "keyword_tags": ["Section 66A IT Act", "freedom of speech", "chilling effect", "vagueness doctrine", "online speech"],
        "summary": "Struck down Section 66A of the Information Technology Act in its entirety as unconstitutional for violating the fundamental right to free speech under Article 19(1)(a).",
        "layman_summary": "Struck down the law that allowed police to arrest citizens for writing offensive or annoying posts online, protecting democratic free speech on social media.",
        "outcome": "Allowed",
        "disposition": "Section 66A Declared Unconstitutional",
        "ratio_decidendi": "Section 66A of the Information Technology Act, 2000 is struck down in its entirety being violative of Article 19(1)(a) and not saved under Article 19(2). The section is cast so widely that virtually any opinion on any subject would be covered, creating an impermissible chilling effect on speech.",
        "precedential_status": "Good Law (Landmark Free Speech Ruling)",
        "official_citation": "(2015) 5 SCC 1",
        "filename": "SC_2015_WP_Crl_No_167_of_2012_11110012.pdf",
    },
    {
        "id": "11111111-0013-4000-8000-000000000013",
        "case_no": "Writ Petition (Crl.) Nos. 666-70 of 1992",
        "cnr_number": "SCIN010006661992",
        "title": "Vishaka and Others v. State of Rajasthan and Others",
        "court": "Supreme Court of India",
        "year": 1997,
        "decision_date": datetime.date(1997, 8, 13),
        "judge": "Hon'ble J.S. Verma, C.J., Sujata V. Manohar, B.N. Kirpal, JJ.",
        "bench_type": "Full Bench (3 Judges)",
        "petitioner": "Vishaka and Others",
        "respondent": "State of Rajasthan and Others",
        "petitioner_counsel": "Senior Advocate Meenakshi Arora",
        "respondent_counsel": "Senior Advocate Altaf Ahmad",
        "legal_domain": "Gender Justice & Workplace Rights",
        "act_tags": ["Constitution of India", "CEDAW"],
        "section_tags": ["Article 14", "Article 19(1)(g)", "Article 21", "Article 32"],
        "keyword_tags": ["Vishaka guidelines", "sexual harassment", "workplace equality", "Internal Complaints Committee", "Article 21"],
        "summary": "Framed binding judicial guidelines to prevent and address sexual harassment of working women at workplaces under Articles 14, 19, and 21, in the absence of enacted legislation.",
        "layman_summary": "Mandated that every workplace must create an Internal Complaints Committee and take concrete preventive measures against sexual harassment.",
        "outcome": "Allowed",
        "disposition": "Binding Workplace Guidelines Enacted",
        "ratio_decidendi": "Each incident of sexual harassment of a woman at workplace results in violation of the fundamental rights of Gender Equality and the Right of Life and Liberty. In the absence of legislative enactments to provide for effective enforcement of the basic human right of gender equality, guidelines and norms are hereby specified for due observance at all workplaces.",
        "precedential_status": "Good Law (Codified into POSH Act, 2013)",
        "official_citation": "(1997) 6 SCC 241",
        "filename": "SC_1997_WP_Crl_Nos_666_70_of_1992_11110013.pdf",
    },
    {
        "id": "11111111-0014-4000-8000-000000000014",
        "case_no": "Criminal Appeal No. 1340 of 2019",
        "cnr_number": "SCIN010013402019",
        "title": "P. Chidambaram v. Directorate of Enforcement",
        "court": "Supreme Court of India",
        "year": 2019,
        "decision_date": datetime.date(2019, 12, 4),
        "judge": "Hon'ble R. Banumathi, A.S. Bopanna, Hrishikesh Roy, JJ.",
        "bench_type": "Full Bench (3 Judges)",
        "petitioner": "P. Chidambaram",
        "respondent": "Directorate of Enforcement",
        "petitioner_counsel": "Senior Advocates Kapil Sibal, Abhishek Manu Singhvi",
        "respondent_counsel": "Solicitor General Tushar Mehta",
        "legal_domain": "Economic Offences & Bail Standards",
        "act_tags": ["Prevention of Money Laundering Act, 2002", "Code of Criminal Procedure, 1973"],
        "section_tags": ["Section 45 PMLA", "Section 439 CrPC", "Section 3 PMLA"],
        "keyword_tags": ["bail in economic offences", "PMLA Section 45", "flight risk", "witness tampering", "pre-trial detention"],
        "summary": "Held that economic offences cannot be treated as an absolute class where bail must be denied automatically; the basic bail test (flight risk, witness tampering) remains operative.",
        "layman_summary": "Accused persons in financial or economic cases cannot be denied bail perpetually as a form of pre-trial punishment if they do not pose a flight risk or tampering danger.",
        "outcome": "Allowed",
        "disposition": "Regular Bail Granted in INX Media Case",
        "ratio_decidendi": "Even if the allegation is one of grave economic offence, it is not a rule that bail should be denied in every such case. The gravity of the offence is to be gathered from the nature of the allegation and the severity of punishment. In determining bail, the court must consider whether there is flight risk, risk of tampering with evidence, or influencing witnesses.",
        "precedential_status": "Good Law (Precedent on PMLA Bail)",
        "official_citation": "(2019) 9 SCC 24",
        "filename": "SC_2019_Crl_A_No_1340_of_2019_11110014.pdf",
    },
    {
        "id": "11111111-0015-4000-8000-000000000015",
        "case_no": "Criminal Appeal No. 1105 of 2002",
        "cnr_number": "SCIN010011052002",
        "title": "State of M.P. v. Mishrilal (Dead) and Others",
        "court": "Supreme Court of India",
        "year": 2003,
        "decision_date": datetime.date(2003, 4, 2),
        "judge": "Hon'ble N. Santosh Hegde & B.P. Singh, JJ.",
        "bench_type": "Division Bench (2 Judges)",
        "petitioner": "State of Madhya Pradesh",
        "respondent": "Mishrilal (Dead) and Others",
        "petitioner_counsel": "Advocate Vibha Datta Makhija",
        "respondent_counsel": "Advocate Sushil Kumar Jain",
        "legal_domain": "Cross-Cases & Trial Procedure",
        "act_tags": ["Code of Criminal Procedure, 1973", "Indian Penal Code, 1860"],
        "section_tags": ["Section 302 IPC", "Section 307 IPC", "Section 148 IPC"],
        "keyword_tags": ["cross cases", "same occurrence", "simultaneous trial", "appreciation of evidence", "fair trial"],
        "summary": "Established the standard procedure for trial of cross-cases arising out of the same occurrence: both cases must be tried by the same judge one after another and judgments pronounced on the same day.",
        "layman_summary": "When two opposing groups file counter-complaints over the same clash, the same judge must try both cases back-to-back to ascertain the true aggressor.",
        "outcome": "Dismissed",
        "disposition": "Acquittal Affirmed in Cross-Trial",
        "ratio_decidendi": "In cross cases arising out of the same incident, the proper procedure is that both cases must be tried by the same court. After recording evidence in one case, the court should hear the other case and deliver judgments on the same day so as to avoid conflicting findings and ascertain the true genesis of the incident.",
        "precedential_status": "Good Law (Binding Procedural Precedent)",
        "official_citation": "(2003) 9 SCC 426",
        "filename": "SC_2003_Crl_A_No_1105_of_2002_11110015.pdf",
    },
]

def generate_landmark_pdf(item: dict) -> bytes:
    """Generates an authentic Supreme Court judgment PDF using ReportLab canvas."""
    from io import BytesIO
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    # Page 1: Official Judicial Header & Header Box
    c.setFont("Times-Bold", 16)
    c.drawCentredString(width / 2.0, height - 50, "IN THE SUPREME COURT OF INDIA")
    c.setFont("Times-Bold", 12)
    c.drawCentredString(width / 2.0, height - 70, item["legal_domain"].upper() + " JURISDICTION")

    c.setFont("Times-Italic", 11)
    c.drawCentredString(width / 2.0, height - 90, f"({item['bench_type']})")

    c.setLineWidth(1)
    c.setStrokeColor(colors.maroon)
    c.line(50, height - 100, width - 50, height - 100)

    # Case identifiers
    c.setFont("Times-Bold", 11)
    c.drawString(60, height - 120, f"CASE NUMBER: {item['case_no']}")
    c.drawString(width - 250, height - 120, f"CNR: {item['cnr_number']}")

    c.setFont("Times-Roman", 10)
    c.drawString(60, height - 138, f"REPORTABLE CITATION: {item['official_citation']}")
    c.drawString(width - 250, height - 138, f"DATE: {item['decision_date'].strftime('%B %d, %Y')}")

    # Coram
    c.setFont("Times-BoldItalic", 10)
    c.drawString(60, height - 160, "CORAM:")
    c.setFont("Times-Roman", 9)
    # wrap judges
    judges = item["judge"]
    c.drawString(120, height - 160, judges[:85])
    if len(judges) > 85:
        c.drawString(120, height - 173, judges[85:170])

    # Parties Box
    c.setFillColor(colors.whitesmoke)
    c.rect(50, height - 250, width - 100, 65, fill=1, stroke=1)
    c.setFillColor(colors.black)

    c.setFont("Times-Bold", 11)
    c.drawCentredString(width / 2.0, height - 200, item["title"])
    c.setFont("Times-Italic", 9)
    c.drawCentredString(width / 2.0, height - 215, f"{item['petitioner']}  ...PETITIONER(S)")
    c.drawCentredString(width / 2.0, height - 230, "VERSUS")
    c.drawCentredString(width / 2.0, height - 243, f"{item['respondent']}  ...RESPONDENT(S)")

    # Section 1: Headnote & Legislative Matrix
    y = height - 275
    c.setFont("Times-Bold", 11)
    c.setFillColor(colors.maroon)
    c.drawString(60, y, "HEADNOTE & STATUTORY PROVISIONS CONSIDERED")
    c.setFillColor(colors.black)
    y -= 15

    c.setFont("Times-Roman", 9)
    provisions_str = f"Acts: {', '.join(item['act_tags'])}  |  Sections: {', '.join(item['section_tags'])}"
    c.drawString(60, y, provisions_str[:110])
    y -= 15

    # Summary Text
    c.setFont("Times-Roman", 9.5)
    words = (item["summary"] + " " + item["layman_summary"]).split()
    line = ""
    for w in words:
        if len(line + " " + w) < 95:
            line += " " + w
        else:
            c.drawString(60, y, line.strip())
            y -= 14
            line = w
    if line:
        c.drawString(60, y, line.strip())
        y -= 20

    # Section 2: Ratio Decidendi
    c.setFont("Times-Bold", 11)
    c.setFillColor(colors.maroon)
    c.drawString(60, y, "RATIO DECIDENDI & BINDING LEGAL PRINCIPLE")
    c.setFillColor(colors.black)
    y -= 15

    c.setFont("Times-Italic", 9.5)
    r_words = item["ratio_decidendi"].split()
    r_line = ""
    for w in r_words:
        if len(r_line + " " + w) < 95:
            r_line += " " + w
        else:
            c.drawString(60, y, r_line.strip())
            y -= 14
            r_line = w
    if r_line:
        c.drawString(60, y, r_line.strip())
        y -= 25

    # Section 3: Final Disposition & Digital Seal
    c.setFont("Times-Bold", 11)
    c.setFillColor(colors.maroon)
    c.drawString(60, y, "FINAL JUDICIAL DISPOSITION")
    c.setFillColor(colors.black)
    y -= 15

    c.setFont("Times-Bold", 10)
    c.drawString(60, y, f"DISPOSITION: {item['disposition']} (Outcome: {item['outcome']})")
    y -= 15
    c.setFont("Times-Roman", 9)
    c.drawString(60, y, f"Precedential Authority: {item['precedential_status']}")
    y -= 35

    # Seal Block
    c.setStrokeColor(colors.green)
    c.setLineWidth(1)
    c.rect(50, y - 10, width - 100, 35, stroke=1, fill=0)
    c.setFont("Times-Bold", 8.5)
    c.setFillColor(colors.darkgreen)
    c.drawString(60, y + 12, "LEXGUARD CRYPTOGRAPHIC REGISTERED SEAL • STATUTORY JUDICIAL ARCHIVE")
    c.setFont("Courier", 7.5)
    c.setFillColor(colors.black)
    c.drawString(60, y, "Section 65B IEA / Section 63 BSA • Immutable Repository Authority Record")

    # Page Footer
    c.setFont("Times-Roman", 8)
    c.drawCentredString(width / 2.0, 25, "Page 1 of 1  •  Official Electronic Precedent Record  •  Supreme Court of India")

    c.showPage()
    c.save()
    return buf.getvalue()

def main():
    print("=" * 70)
    print("SEEDING TOP 15 SUPREME COURT LANDMARK PRECEDENTS")
    print("=" * 70)

    for d in TARGET_DIRS:
        os.makedirs(d, exist_ok=True)

    db = SessionLocal()
    # Get or default system admin user
    admin_user = db.query(User).filter(User.role.in_(["senior_staff", "staff"])).first()
    admin_id = admin_user.id if admin_user else str(uuid.uuid4())

    seeded_count = 0
    for idx, item in enumerate(LANDMARKS_DATA, 1):
        pdf_bytes = generate_landmark_pdf(item)
        file_hash = hashlib.sha256(pdf_bytes).hexdigest()
        filename = item["filename"]
        rel_path = f"storage/cases/{filename}"

        # Mirror PDF bytes to all 4 storage locations
        for d in TARGET_DIRS:
            dest_fp = os.path.join(d, filename)
            with open(dest_fp, "wb") as f:
                f.write(pdf_bytes)

        full_text_corpus = f"""
IN THE SUPREME COURT OF INDIA
{item['legal_domain'].upper()} JURISDICTION
{item['case_no']}
CNR: {item['cnr_number']}
CITATION: {item['official_citation']}

BEFORE:
{item['judge']}

{item['title']}

PETITIONER: {item['petitioner']}
RESPONDENT: {item['respondent']}
COUNSEL FOR PETITIONER: {item['petitioner_counsel']}
COUNSEL FOR RESPONDENT: {item['respondent_counsel']}

JUDGMENT DATE: {item['decision_date'].strftime('%d-%m-%Y')}

SUMMARY & HEADNOTE:
{item['summary']}

PLAIN-LANGUAGE EXPLANATION:
{item['layman_summary']}

STATUTES AND PROVISIONS CONSIDERED:
{', '.join(item['act_tags'])}
{', '.join(item['section_tags'])}

RATIO DECIDENDI:
{item['ratio_decidendi']}

FINAL ORDER & DISPOSITION:
{item['disposition']}. The petition is {item['outcome']}.
Precedential Status: {item['precedential_status']}.
"""

        # Upsert in PostgreSQL
        existing = db.query(Case).filter(Case.id == item["id"]).first()
        if not existing:
            existing = db.query(Case).filter(Case.case_no == item["case_no"]).first()

        if existing:
            case_obj = existing
        else:
            case_obj = Case(id=item["id"], uploaded_by_id=admin_id)
            db.add(case_obj)

        case_obj.case_no = item["case_no"]
        case_obj.cnr_number = item["cnr_number"]
        case_obj.title = item["title"]
        case_obj.court = item["court"]
        case_obj.year = item["year"]
        case_obj.decision_date = item["decision_date"]
        case_obj.judge = item["judge"]
        case_obj.bench_type = item["bench_type"]
        case_obj.parties = f"{item['petitioner']} v. {item['respondent']}"
        case_obj.petitioner = item["petitioner"]
        case_obj.respondent = item["respondent"]
        case_obj.petitioner_counsel = item["petitioner_counsel"]
        case_obj.respondent_counsel = item["respondent_counsel"]
        case_obj.legal_domain = item["legal_domain"]
        case_obj.act_tags = item["act_tags"]
        case_obj.section_tags = item["section_tags"]
        case_obj.keyword_tags = item["keyword_tags"]
        case_obj.summary = item["summary"]
        case_obj.layman_summary = item["layman_summary"]
        case_obj.outcome = item["outcome"]
        case_obj.disposition = item["disposition"]
        case_obj.ratio_decidendi = item["ratio_decidendi"]
        case_obj.precedents_cited = []
        case_obj.cited_by_count = 0
        case_obj.official_citation = item["official_citation"]
        case_obj.full_text = full_text_corpus.strip()
        case_obj.page_count = 1
        case_obj.file_path = rel_path
        case_obj.file_hash = file_hash
        case_obj.precedential_status = item["precedential_status"]
        case_obj.status = "published"

        db.flush()

        # Update DocumentVersion
        dv = db.query(DocumentVersion).filter(DocumentVersion.case_id == case_obj.id).first()
        if not dv:
            dv = DocumentVersion(
                case_id=case_obj.id,
                version_no=1,
                file_path=rel_path,
                file_hash=file_hash,
                change_summary="Landmark Anchor Judgment Registration",
                changed_by_id=admin_id,
            )
            db.add(dv)
        else:
            dv.file_path = rel_path
            dv.file_hash = file_hash

        # Audit Log
        log_audit = AuditLog(**build_audit_entry(
            get_chain_head_hash(db),
            action="LANDMARK_SEED",
            user_id=admin_id,
            case_id=case_obj.id,
            details=f"Registered Supreme Court Landmark Precedent: {item['title']} [{item['official_citation']}]",
        ))
        db.add(log_audit)

        seeded_count += 1
        print(f"[{idx}/{len(LANDMARKS_DATA)}] Seeded: {item['title']} -> {filename} (SHA-256: {file_hash[:16]}...)")

    db.commit()
    db.close()

    print("\n" + "=" * 70)
    print(f"SUCCESSFULLY SEEDED {seeded_count} LANDMARK SUPREME COURT PRECEDENTS")
    print("=" * 70)

if __name__ == "__main__":
    main()
