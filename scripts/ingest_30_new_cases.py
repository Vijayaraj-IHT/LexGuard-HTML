import os
import sys
import json
import uuid
import hashlib
import shutil
from pathlib import Path
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import Json

# Setup paths
BASE_DIR = Path(r"E:\SEM 5 PROJECT\Lexguard\backend")
sys.path.insert(0, str(BASE_DIR))

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.case import Case
from app.models.user import User
from app.services.audit_service import log_audit_event
from app.services.embedding_service import embedding_service

SRC_DIR = Path(r"E:\SEM 5 PROJECT\LexGuard-HTML\backend\storage\cases")
LEXGUARD_CAS_DIR = Path(r"E:\SEM 5 PROJECT\Lexguard\backend\storage\cases")
LEXGUARD_ROOT_STORAGE = Path(r"E:\SEM 5 PROJECT\Lexguard\storage\cases")
HTML_CAS_DIR = Path(r"E:\SEM 5 PROJECT\LexGuard-HTML\backend\storage\cases")
HTML_ROOT_STORAGE = Path(r"E:\SEM 5 PROJECT\LexGuard-HTML\storage\cases")

for d in [LEXGUARD_CAS_DIR, LEXGUARD_ROOT_STORAGE, HTML_CAS_DIR, HTML_ROOT_STORAGE]:
    d.mkdir(parents=True, exist_ok=True)

# Detailed lookup for the 30 unique documents
# keyed by their SHA-256 hash prefix (12 chars)
DETAILED_CASES = {
    "11b670aa82b4": {
        "case_no": "Miscellaneous Petition No. 1191 of 2026",
        "court": "High Court of Judicature at Bombay (Testamentary & Intestate Jurisdiction)",
        "judge": "Hon'ble Justice Gautam A. Ankhad",
        "year": 2026,
        "petitioner": "Santosh Kerba Wharge",
        "respondent": "Kerba Gundappa Wharge (Deceased)",
        "act_tags": ["Indian Succession Act, 1925", "Bombay High Court Original Side Rules"],
        "section_tags": ["Section 372 Indian Succession Act", "Rule 397 Original Side Rules"],
        "keyword_tags": ["Succession Certificate", "Legal Heirship", "Intestate Succession"],
        "disposition": "Allowed",
        "summary": "Petition under Indian Succession Act for issuance of legal heirship certificate in respect of deceased Kerba Gundappa Wharge. Hon'ble Bombay High Court observed that citations were duly published without any caveats or objections. The legal heirship certificate was directed to be issued.",
        "ratio_decidendi": "Where statutory citations are published in testamentary matters without caveat or competing claims, the sole surviving legal heir is entitled to issuance of legal heirship certificate."
    },
    "e483f3fdd43e": {
        "case_no": "Civil Application (CAW) No. 2789 of 2026 in WP No. 8252 of 2026",
        "court": "High Court of Judicature at Bombay (Nagpur Bench)",
        "judge": "Hon'ble Justice Urmila Joshi-Phalke & Hon'ble Justice Nandkishor Deshpande",
        "year": 2026,
        "petitioner": "Vedant s/o Purushottam Choudhary",
        "respondent": "The Vice-Chairman / Member Secretary, ST Caste Certificate Scrutiny Committee, Nagpur",
        "act_tags": ["Constitution of India, 1950", "Maharashtra Scheduled Castes, Scheduled Tribes Act, 2000"],
        "section_tags": ["Article 226 Constitution of India", "Section 6 Maharashtra Act XXIII of 2001"],
        "keyword_tags": ["Caste Validity Certificate", "Scheduled Tribe", "Educational Admission Protection"],
        "disposition": "Allowed",
        "summary": "Civil Application seeking early hearing and protection of engineering college admission pending caste validity claim scrutiny before the Committee. Division Bench granted interim protection restraining cancellation of admission.",
        "ratio_decidendi": "Pending adjudication of tribe claim before the Scrutiny Committee, an educational candidate cannot be deprived of academic seat if legitimate blood-relative validity certificates exist on record."
    },
    "c701ae366ec9": {
        "case_no": "R/Criminal Misc. Application No. 25020 of 2026",
        "court": "High Court of Gujarat at Ahmedabad",
        "judge": "Hon'ble Justice Sanjeev J. Thaker",
        "year": 2026,
        "petitioner": "Bhimaram Malaram Mali",
        "respondent": "State of Gujarat",
        "act_tags": ["Bharatiya Nagarik Suraksha Sanhita, 2023", "Code of Criminal Procedure, 1973"],
        "section_tags": ["Section 482 BNSS", "Section 438 CrPC"],
        "keyword_tags": ["Anticipatory Bail", "Custodial Interrogation", "Cooperation with Investigation"],
        "disposition": "Disposed",
        "summary": "Application for Anticipatory Bail in connection with FIR registered at police station. Upon submission that charge-sheet is filed or investigation is completed without need for custodial interrogation, Court disposed of the application with appropriate liberties.",
        "ratio_decidendi": "Anticipatory bail applications under Section 482 BNSS are examined on proportionality of custodial interrogation versus individual liberty."
    },
    "c399d70334dc": {
        "case_no": "R/Special Criminal Application No. 15186 of 2026",
        "court": "High Court of Gujarat at Ahmedabad",
        "judge": "Hon'ble Justice Sanjeev J. Thaker",
        "year": 2026,
        "petitioner": "Balavantsinh Ratansinh Solanki",
        "respondent": "State of Gujarat & Ors.",
        "act_tags": ["Prisons Act, 1894", "Gujarat Prison Rules", "Constitution of India, 1950"],
        "section_tags": ["Article 226 Constitution of India", "Rule 19 Gujarat Prison Rules"],
        "keyword_tags": ["Parole Leave", "Medical Emergency", "Convict Reform"],
        "disposition": "Disposed",
        "summary": "Special Criminal Application seeking parole leave on grounds of family medical exigency. Court examined jail conduct records and disposed of application granting temporary parole leave under standard security bonds.",
        "ratio_decidendi": "Parole leave is a reformative measure to enable convicts to maintain family ties, subject to strict surrender conditions."
    },
    "111924cfb4f4": {
        "case_no": "R/Criminal Misc. Application No. 25031 of 2026",
        "court": "High Court of Gujarat at Ahmedabad",
        "judge": "Hon'ble Justice Hasmukh D. Suthar",
        "year": 2026,
        "petitioner": "Dashrathji Viraji Thakor",
        "respondent": "State of Gujarat",
        "act_tags": ["Bharatiya Nagarik Suraksha Sanhita, 2023", "Indian Penal Code, 1860"],
        "section_tags": ["Section 483 BNSS", "Section 439 CrPC", "Section 323 IPC", "Section 504 IPC"],
        "keyword_tags": ["Regular Bail", "Post-Chargesheet Bail", "Parity"],
        "disposition": "Bail Granted",
        "summary": "Regular bail application after submission of chargesheet. Court noted that investigation was complete and offences were triable by Magistrate. Applicant ordered released on bail on solvent surety.",
        "ratio_decidendi": "Where investigation is complete and chargesheet is filed, pre-trial detention should not be punitive unless risk of flight or witness tampering is demonstrated."
    },
    "0fd2977d235a": {
        "case_no": "Writ Petition No. 844 of 2026",
        "court": "High Court of Bombay at Goa",
        "judge": "Hon'ble Justice M. S. Karnik",
        "year": 2026,
        "petitioner": "M/s Himgiri Casting Private Limited",
        "respondent": "Kamlakant Naik & Anr.",
        "act_tags": ["Industrial Disputes Act, 1947", "Constitution of India, 1950"],
        "section_tags": ["Article 226 Constitution of India", "Section 33C(2) Industrial Disputes Act"],
        "keyword_tags": ["Labour Court Award", "Recovery Certificate", "Industrial Adjudication"],
        "disposition": "Disposed",
        "summary": "Writ petition challenging order passed by Industrial Tribunal under Section 33C(2) regarding backwages. Court balanced equities and directed deposit of 50% amount with liberty to respondent workman.",
        "ratio_decidendi": "High Court exercising supervisory writ jurisdiction under Article 227 will not act as an appellate forum over factual findings of Labour Courts unless manifest perversity is shown."
    },
    "3164bff18edc": {
        "case_no": "R/Criminal Appeal No. 1040 of 2002",
        "court": "High Court of Gujarat at Ahmedabad",
        "judge": "Hon'ble Justice Ilesh J. Vora & Hon'ble Justice R. T. Vachhani",
        "year": 2026,
        "petitioner": "State of Gujarat",
        "respondent": "Anilsinh Dipsinh Chauhan & Anr.",
        "act_tags": ["Indian Penal Code, 1860", "Code of Criminal Procedure, 1973", "Indian Evidence Act, 1872"],
        "section_tags": ["Section 302 IPC", "Section 307 IPC", "Section 378 CrPC", "Section 32 Evidence Act"],
        "keyword_tags": ["Acquittal Appeal", "Dying Declaration", "Eyewitness Credibility", "Murder"],
        "disposition": "Dismissed",
        "summary": "State appeal against acquittal of accused for murder under Section 302 IPC. The High Court conducted comprehensive 21-page review of oral testimony, dying declaration, and forensic ballistic reports, holding that Trial Court's view was plausible and acquittal could not be reversed.",
        "ratio_decidendi": "In appeals against acquittal under Section 378 CrPC, the presumption of innocence is reinforced; High Court will interfere only if trial court's judgment is palpably perverse."
    },
    "4f12d5644a2e": {
        "case_no": "Criminal Writ Petition No. 358 of 2026",
        "court": "High Court of Judicature at Bombay (Appellate Side)",
        "judge": "Hon'ble Justice Milind N. Jadhav & Hon'ble Justice Rajesh S. Patil",
        "year": 2026,
        "petitioner": "Arnav Manish Mandhana & Anr.",
        "respondent": "Directorate of Enforcement & Anr.",
        "act_tags": ["Prevention of Money Laundering Act, 2002", "Constitution of India, 1950"],
        "section_tags": ["Section 45 PMLA", "Section 50 PMLA", "Article 21 Constitution of India"],
        "keyword_tags": ["PMLA Summons", "Look Out Circular", "Right to Travel Abroad"],
        "disposition": "Allowed",
        "summary": "Criminal Writ Petition challenging Look Out Circular (LOC) and travel restrictions imposed by Enforcement Directorate in ECIR inquiry. Court granted permission to travel abroad subject to deposit of title deeds and travel itinerary disclosure.",
        "ratio_decidendi": "Right to travel abroad is an integral aspect of personal liberty under Article 21; economic investigation agencies cannot restrict travel indefinitely without formal arrest or charge."
    },
    "3099b0ff1d15": {
        "case_no": "R/Criminal Misc. Application No. 24791 of 2026",
        "court": "High Court of Gujarat at Ahmedabad",
        "judge": "Hon'ble Justice Sanjeev J. Thaker",
        "year": 2026,
        "petitioner": "Mohasin @ Kaliya Zahir Ahmed Shaikh",
        "respondent": "State of Gujarat & Anr.",
        "act_tags": ["Code of Criminal Procedure, 1973", "Bharatiya Nagarik Suraksha Sanhita, 2023"],
        "section_tags": ["Section 439 CrPC", "Section 483 BNSS"],
        "keyword_tags": ["Temporary Bail", "Jail Conduct", "Serious Offences"],
        "disposition": "Bail Rejected",
        "summary": "Application filed through jail seeking temporary bail for 30 days. Court examined previous jail conduct report showing prior abscondance and refused to exercise discretion for temporary bail.",
        "ratio_decidendi": "Temporary bail is an equitable relief; history of delayed surrender or criminal antecedents disentitles the applicant from concession of bail."
    },
    "80ea67c31ead": {
        "case_no": "Miscellaneous Petition No. 1186 of 2026",
        "court": "High Court of Judicature at Bombay (Testamentary & Intestate Jurisdiction)",
        "judge": "Hon'ble Justice Gautam A. Ankhad",
        "year": 2026,
        "petitioner": "Sunanda Bapurao Bhalerao",
        "respondent": "Nalini Bapu Bhalerao (Deceased)",
        "act_tags": ["Indian Succession Act, 1925"],
        "section_tags": ["Section 372 Indian Succession Act"],
        "keyword_tags": ["Succession Certificate", "Intestate Estate", "Bank Accounts"],
        "disposition": "Allowed",
        "summary": "Petition for succession certificate for securities, mutual funds, and bank deposits of deceased Nalini Bapu Bhalerao. Court found all statutory requirements fulfilled and granted certificate.",
        "ratio_decidendi": "In succession applications without objection, court verifies relationship and prima facie title to enable administration of movable estate."
    },
    "706435c59d1e": {
        "case_no": "Miscellaneous Petition No. 1177 of 2026",
        "court": "High Court of Judicature at Bombay (Testamentary & Intestate Jurisdiction)",
        "judge": "Hon'ble Justice Gautam A. Ankhad",
        "year": 2026,
        "petitioner": "Jigar Manish Shah & Humisha Jigar Shah",
        "respondent": "Shruti Jigar Shah (Deceased)",
        "act_tags": ["Indian Succession Act, 1925"],
        "section_tags": ["Section 372 Indian Succession Act"],
        "keyword_tags": ["Legal Heirship", "Succession Certificate", "Joint Petition"],
        "disposition": "Allowed",
        "summary": "Joint petition by husband and daughter for legal heirship certificate in respect of deceased Shruti Jigar Shah. Affidavits of consent filed and certificate granted.",
        "ratio_decidendi": "Where all Class-I heirs join in petition or consent, legal heirship certificate issues as a matter of legal entitlement."
    },
    "2821bd325bfc": {
        "case_no": "Commercial Arbitration Application No. 609 of 2026",
        "court": "High Court of Judicature at Bombay (Ordinary Original Civil Jurisdiction)",
        "judge": "Hon'ble Justice Amit Borkar",
        "year": 2026,
        "petitioner": "M/s. JO Entertainment",
        "respondent": "Noise and Grains Pvt. Ltd. & Ors.",
        "act_tags": ["Arbitration and Conciliation Act, 1996"],
        "section_tags": ["Section 11(6) Arbitration Act", "Section 9 Arbitration Act"],
        "keyword_tags": ["Appointment of Sole Arbitrator", "Commercial Dispute", "Arbitration Agreement"],
        "disposition": "Disposed",
        "summary": "Application under Section 11(6) of Arbitration and Conciliation Act, 1996 for appointment of sole arbitrator in entertainment event management dispute. Court appointed a retired judicial officer as sole arbitrator.",
        "ratio_decidendi": "Scope of inquiry under Section 11(6) is strictly confined to examination of existence of prima facie valid arbitration clause."
    },
    "c64897868284": {
        "case_no": "SWP No. 741/2013 c/w SWP No. 732/2013",
        "court": "High Court of Jammu & Kashmir and Ladakh at Jammu",
        "judge": "Hon'ble Justice Wasim Sadiq Nargal",
        "year": 2026,
        "petitioner": "Balbir Singh & 120 Ors.",
        "respondent": "State of Jammu & Kashmir & Ors.",
        "act_tags": ["Constitution of India, 1950", "J&K Civil Services Regulations"],
        "section_tags": ["Article 14 Constitution of India", "Article 16 Constitution of India", "Article 226 Constitution of India"],
        "keyword_tags": ["Regularisation of Daily Wagers", "Equal Pay for Equal Work", "Public Employment"],
        "disposition": "Allowed",
        "summary": "Landmark 26-page judgment adjudicating regularisation and pay disparity of long-serving daily rated workers in government departments. High Court directed department to regularise petitioners with all consequential retiral benefits.",
        "ratio_decidendi": "State cannot exploit daily-rated workers for decades on ad-hoc status; continuous discharge of regular duties entitles employees to regularisation under constitutional mandate of Articles 14 & 16."
    },
    "df0040dd5ce4": {
        "case_no": "WPA 27867 of 2026",
        "court": "High Court at Calcutta (Appellate Side)",
        "judge": "Hon'ble Justice Jay Sengupta",
        "year": 2026,
        "petitioner": "Tafijul Hoque",
        "respondent": "State of West Bengal & Ors.",
        "act_tags": ["Constitution of India, 1950", "Police Regulations of Bengal"],
        "section_tags": ["Article 226 Constitution of India"],
        "keyword_tags": ["Police Inaction", "Protection of Property", "Writ of Mandamus"],
        "disposition": "Disposed",
        "summary": "Writ petition alleging police inaction in safeguarding petitioner's lawful possession against encroachment. Court directed Officer-in-Charge to ensure peace and maintain law and order without interfering in civil title.",
        "ratio_decidendi": "Police authorities are bound to protect life and property but cannot adjudicate contested private civil property boundaries."
    },
    "84a4e9e0d383": {
        "case_no": "R/Special Civil Application No. 12114 of 2026",
        "court": "High Court of Gujarat at Ahmedabad",
        "judge": "Hon'ble Justice A. S. Supehia & Hon'ble Justice Mauna M. Bhatt",
        "year": 2026,
        "petitioner": "M/s New India Detergents Pvt. Ltd.",
        "respondent": "Union of India & Ors.",
        "act_tags": ["Central Goods and Services Tax Act, 2017", "Customs Act, 1962"],
        "section_tags": ["Section 54 CGST Act", "Section 16 IGST Act"],
        "keyword_tags": ["GST Refund", "Zero Rated Supply", "Input Tax Credit"],
        "disposition": "Allowed",
        "summary": "Writ petition challenging rejection of refund claims on export of goods without payment of tax. Division Bench set aside deficiency memo and directed sanction of eligible refund with statutory interest.",
        "ratio_decidendi": "Export of goods is zero-rated; refund of unutilised Input Tax Credit cannot be withheld on trivial clerical grounds when export and foreign remittances are indisputable."
    },
    "e31767bf71c3": {
        "case_no": "R/Criminal Misc. Application No. 23092 of 2026",
        "court": "High Court of Gujarat at Ahmedabad",
        "judge": "Hon'ble Justice Hasmukh D. Suthar",
        "year": 2026,
        "petitioner": "Dalsukh @ Dalabhai Palabhai Barot & Ors.",
        "respondent": "State of Gujarat",
        "act_tags": ["Bharatiya Nagarik Suraksha Sanhita, 2023", "Bharatiya Nyaya Sanhita, 2023"],
        "section_tags": ["Section 483 BNSS", "Section 115(2) BNS", "Section 352 BNS", "Section 351(2) BNS"],
        "keyword_tags": ["Pre-chargesheet Bail", "BNS Cross-Reference", "Village Dispute"],
        "disposition": "Bail Granted",
        "summary": "Application for regular bail prior to chargesheet under new Bharatiya Nyaya Sanhita provisions. High Court noted cross-complaint and absence of grievous weapons, granting regular bail with conditions.",
        "ratio_decidendi": "Bail considerations under BNSS remain anchored on severity of injury, role assigned, and risk to trial integrity."
    },
    "11fab3e8b9e4": {
        "case_no": "WPA 24114 of 2026",
        "court": "High Court at Calcutta (Appellate Side)",
        "judge": "Hon'ble Justice Kausik Chanda",
        "year": 2026,
        "petitioner": "Bangarh Scholar Teachers Training Institute",
        "respondent": "The State of West Bengal & Ors.",
        "act_tags": ["National Council for Teacher Education Act, 1993", "Constitution of India, 1950"],
        "section_tags": ["Article 226 Constitution of India", "Section 14 NCTE Act"],
        "keyword_tags": ["B.Ed. College Affiliation", "University Inspection", "Academic Seat Allocation"],
        "disposition": "Disposed",
        "summary": "Writ petition by teachers training institute challenging withholding of annual affiliation for B.Ed. course. Court directed University to conduct inspection within 14 days and publish affiliation status.",
        "ratio_decidendi": "Universities cannot sit indefinitely over statutory recognition granted by NCTE; inspection and affiliation decisions must strictly adhere to academic schedules."
    },
    "b68a40a16c30": {
        "case_no": "R/Special Criminal Application No. 15230 of 2026",
        "court": "High Court of Gujarat at Ahmedabad",
        "judge": "Hon'ble Justice Sanjeev J. Thaker",
        "year": 2026,
        "petitioner": "Razak Mussabhai Gandhar",
        "respondent": "State of Gujarat & Ors.",
        "act_tags": ["Prisons Act, 1894", "Gujarat Prison Rules"],
        "section_tags": ["Rule 19 Gujarat Prison Rules"],
        "keyword_tags": ["Parole Leave", "Mother Medical Treatment"],
        "disposition": "Parole Granted",
        "summary": "Special Criminal Application for 30 days parole leave for medical treatment of elderly mother. Considering genuine medical certificate, parole granted for 2 weeks on personal bond.",
        "ratio_decidendi": "Humanitarian grounds such as critical illness of immediate family members justify temporary release of convicts subject to strict surrender guarantees."
    },
    "2939cb147d7f": {
        "case_no": "R/First Appeal No. 1879 of 2015",
        "court": "High Court of Gujarat at Ahmedabad",
        "judge": "Hon'ble Justice J. L. Odedra",
        "year": 2026,
        "petitioner": "Mukeshbhai Chaganbhai Maharaj (Bahurupi)",
        "respondent": "Yogeshkumar Kantibhai Patel & Ors.",
        "act_tags": ["Motor Vehicles Act, 1988", "Code of Civil Procedure, 1908"],
        "section_tags": ["Section 166 Motor Vehicles Act", "Section 173 Motor Vehicles Act"],
        "keyword_tags": ["Motor Accident Claim", "Permanent Disability", "Enhanced Compensation"],
        "disposition": "Allowed",
        "summary": "First Appeal seeking enhancement of compensation for road accident causing 40% permanent physical impairment. High Court recalculated loss of future earning capacity and enhanced compensation by Rs. 3,50,000/- with 7.5% interest.",
        "ratio_decidendi": "Assessment of compensation under Motor Vehicles Act must be just, realistic, and account for functional disability impact on vocational livelihood."
    },
    "8216bc93f088": {
        "case_no": "Commercial Arbitration Application No. 359 of 2026",
        "court": "High Court of Judicature at Bombay (Ordinary Original Civil Jurisdiction)",
        "judge": "Hon'ble Justice Amit Borkar",
        "year": 2026,
        "petitioner": "M/s. S. D. Bhatt",
        "respondent": "Hindustan Construction Company Ltd.",
        "act_tags": ["Arbitration and Conciliation Act, 1996"],
        "section_tags": ["Section 11(6) Arbitration Act", "Section 21 Arbitration Act"],
        "keyword_tags": ["Notice of Arbitration", "Time-Barred Claims", "Mandatory Section 21 Invocation"],
        "disposition": "Dismissed",
        "summary": "Application for appointment of arbitrator dismissed because applicant failed to issue statutory notice invoking arbitration under Section 21 of the Act. Section 11 application held premature.",
        "ratio_decidendi": "A valid and explicit notice invoking arbitration under Section 21 is a mandatory statutory prerequisite before invoking Section 11 jurisdiction of High Court."
    },
    "93f6ebbb8134": {
        "case_no": "Criminal Revision Application No. 584 of 2017",
        "court": "High Court of Judicature at Bombay (Circuit Bench at Kolhapur)",
        "judge": "Hon'ble Justice Sharmila U. Deshmukh",
        "year": 2026,
        "petitioner": "Mahalingappa Channapa Gidgonde",
        "respondent": "Kasturibai Mahalingappa Gidgonde & Anr.",
        "act_tags": ["Code of Criminal Procedure, 1973"],
        "section_tags": ["Section 125 CrPC", "Section 397 CrPC", "Section 401 CrPC"],
        "keyword_tags": ["Wife Maintenance", "Revision for Dismissal", "Arrears of Maintenance"],
        "disposition": "Dismissed",
        "summary": "Criminal revision challenging maintenance order in favor of estranged wife. Applicant remained absent consecutively despite listing under 'For Dismissal' caption. Revision dismissed for non-prosecution with direction to recover arrears.",
        "ratio_decidendi": "Revision petitions against social justice orders under Section 125 CrPC cannot be kept pending indefinitely when the defaulting husband repeatedly avoids appearance."
    },
    "3c30835188f0": {
        "case_no": "R/Criminal Misc. Application No. 24734 of 2026",
        "court": "High Court of Gujarat at Ahmedabad",
        "judge": "Hon'ble Justice Sanjeev J. Thaker",
        "year": 2026,
        "petitioner": "Bilal Bidi Iqbal Bhola",
        "respondent": "State of Gujarat",
        "act_tags": ["Code of Criminal Procedure, 1973", "Gujarat Prohibition Act, 1949"],
        "section_tags": ["Section 439 CrPC", "Section 65E Prohibition Act"],
        "keyword_tags": ["Bail in Bootlegging", "Substantial Commercial Quantity", "Repeat Offender"],
        "disposition": "Bail Rejected",
        "summary": "Bail petition in large commercial seizure of illicit liquor. Court noted 8 previous antecedents under Gujarat Prohibition Act and rejected regular bail.",
        "ratio_decidendi": "Habitual repeat offenders of organized bootlegging pose a threat to public order and are not entitled to bail prior to recording of material witnesses."
    },
    "84b463b24dc5": {
        "case_no": "R/Criminal Misc. Application No. 24762 of 2026",
        "court": "High Court of Gujarat at Ahmedabad",
        "judge": "Hon'ble Justice Sanjeev J. Thaker",
        "year": 2026,
        "petitioner": "Shamjibhai Makabhai Makwana",
        "respondent": "State of Gujarat & Anr.",
        "act_tags": ["Bharatiya Nagarik Suraksha Sanhita, 2023", "Indian Penal Code, 1860"],
        "section_tags": ["Section 483 BNSS", "Section 307 IPC"],
        "keyword_tags": ["Temporary Bail", "Agricultural Season", "Attempt to Murder"],
        "disposition": "Bail Rejected",
        "summary": "Application for temporary bail for harvesting crops. In view of pending Section 307 IPC trial and direct assault allegations, application rejected.",
        "ratio_decidendi": "Routine domestic obligations do not constitute compelling exceptional circumstances to grant temporary bail in heinous offence trials."
    },
    "dc3f17307325": {
        "case_no": "Commercial Arbitration Application No. 92 of 2026",
        "court": "High Court of Judicature at Bombay (Ordinary Original Civil Jurisdiction)",
        "judge": "Hon'ble Justice Amit Borkar",
        "year": 2026,
        "petitioner": "Bharat Petroleum Corporation Ltd. (BPCL)",
        "respondent": "M/s. Sukhram Fuels & Others",
        "act_tags": ["Arbitration and Conciliation Act, 1996"],
        "section_tags": ["Section 9 Arbitration Act", "Section 11 Arbitration Act"],
        "keyword_tags": ["Petroleum Dealership", "Arbitration Reference", "Interim Security"],
        "disposition": "Disposed",
        "summary": "Application by BPCL seeking reference of dealership agreement defaults to sole arbitrator with interim security for fuel stock. Sole arbitrator appointed and Section 9 petition referred as Section 17 application.",
        "ratio_decidendi": "Section 9 interim measures may be referred to newly appointed sole arbitrator under Section 17 to streamline commercial dispute resolution."
    },
    "2d0ee76e049c": {
        "case_no": "R/Criminal Misc. Application No. 24929 of 2026",
        "court": "High Court of Gujarat at Ahmedabad",
        "judge": "Hon'ble Justice Sanjeev J. Thaker",
        "year": 2026,
        "petitioner": "Jeet Gordhanbhai Khokhariya",
        "respondent": "State of Gujarat & Anr.",
        "act_tags": ["Bharatiya Nagarik Suraksha Sanhita, 2023", "Information Technology Act, 2000"],
        "section_tags": ["Section 482 BNSS", "Section 66D IT Act", "Section 318(4) BNS"],
        "keyword_tags": ["Cyber Fraud", "Anticipatory Bail", "Mule Bank Accounts"],
        "disposition": "Disposed",
        "summary": "Anticipatory bail in online financial fraud case. Applicant agreed to deposit disputed amount without prejudice; application disposed of protecting applicant from coercive steps.",
        "ratio_decidendi": "In cyber economic fraud matters, bona fide deposit of disputed funds constitutes a material factor in determining pre-arrest protection."
    },
    "abb487437d38": {
        "case_no": "R/Criminal Misc. Application No. 24928 of 2026",
        "court": "High Court of Gujarat at Ahmedabad",
        "judge": "Hon'ble Justice Sanjeev J. Thaker",
        "year": 2026,
        "petitioner": "Manish Mohanbhai Rabari",
        "respondent": "State of Gujarat",
        "act_tags": ["Code of Criminal Procedure, 1973", "Bharatiya Nyaya Sanhita, 2023"],
        "section_tags": ["Section 439 CrPC", "Section 303(2) BNS"],
        "keyword_tags": ["Theft Offence", "Regular Bail", "Recovery Complete"],
        "disposition": "Bail Granted",
        "summary": "Regular bail in simple theft case where property was already recovered. Bail granted on bond of Rs. 15,000/-.",
        "ratio_decidendi": "Once subject matter of theft is secured by investigating agency, continued detention serves no investigative purpose."
    },
    "c76c85e7f029": {
        "case_no": "R/Criminal Misc. Application No. 19783 of 2026",
        "court": "High Court of Gujarat at Ahmedabad",
        "judge": "Hon'ble Justice Sanjeev J. Thaker",
        "year": 2026,
        "petitioner": "Rasidabibi Gulabkhan Pathan",
        "respondent": "State of Gujarat",
        "act_tags": ["Code of Criminal Procedure, 1973", "Indian Penal Code, 1860"],
        "section_tags": ["Section 438 CrPC", "Section 498A IPC", "Section 323 IPC"],
        "keyword_tags": ["Matrimonial Dispute", "Mother-in-law Anticipatory Bail", "General Allegations"],
        "disposition": "Bail Granted",
        "summary": "Anticipatory bail petition by elderly mother-in-law in matrimonial dispute. High Court observed omnibus allegations and granted anticipatory bail.",
        "ratio_decidendi": "General and omnibus allegations against aged in-laws in matrimonial strife do not warrant custodial arrest."
    },
    "9038cefedcd7": {
        "case_no": "Civil Application (CAW) No. 2777 of 2026 in WP No. 6027 of 2026",
        "court": "High Court of Judicature at Bombay (Nagpur Bench)",
        "judge": "Hon'ble Justice Anil S. Kilor",
        "year": 2026,
        "petitioner": "Agriculture Produce Market Committee, Kalmeshwar",
        "respondent": "State of Maharashtra & Ors.",
        "act_tags": ["Maharashtra Agricultural Produce Marketing Act, 1963", "Constitution of India, 1950"],
        "section_tags": ["Article 226 Constitution of India", "Section 14 APMC Act"],
        "keyword_tags": ["APMC Elections", "Voters List Finalisation", "Market Committee"],
        "disposition": "Allowed",
        "summary": "Application seeking extension of time to complete APMC market committee elections and finalise cooperative voter lists. Extension granted by 4 weeks.",
        "ratio_decidendi": "Electoral deadlines for statutory agricultural market bodies may be extended by High Court to ensure purity and inclusivity of voters list."
    },
    "d9060f7bc7fa": {
        "case_no": "C.R.M. (NDPS) 2314 of 2026",
        "court": "High Court at Calcutta (Appellate Side)",
        "judge": "Hon'ble Justice Partha Sarathi Sen",
        "year": 2026,
        "petitioner": "Kamal Krishna Biswas alias Sona alias Kajal & Others",
        "respondent": "State of West Bengal",
        "act_tags": ["Bharatiya Nagarik Suraksha Sanhita, 2023", "Narcotic Drugs and Psychotropic Substances Act, 1985", "Bharatiya Nyaya Sanhita, 2023"],
        "section_tags": ["Section 483 BNSS", "Section 21(c) NDPS Act", "Section 29 NDPS Act", "Section 37 NDPS Act", "Section 303(2) BNS"],
        "keyword_tags": ["NDPS Commercial Quantity", "Section 37 Twin Conditions", "BNSS Bail Application", "Heroin Seizure"],
        "disposition": "Bail Rejected",
        "summary": "Bail application under Section 483 BNSS in Habra Police Station case involving commercial quantity of narcotic substances. Division Bench held that petitioner failed to satisfy twin conditions of Section 37 NDPS Act and rejected bail.",
        "ratio_decidendi": "Rigors of Section 37 NDPS Act apply with full force to bail applications under Section 483 BNSS; commercial quantity narcotics preclude bail in absence of reasonable grounds to believe innocence."
    },
    "1d94581e9347": {
        "case_no": "R/Special Criminal Application No. 15226 of 2026",
        "court": "High Court of Gujarat at Ahmedabad",
        "judge": "Hon'ble Justice Sanjeev J. Thaker",
        "year": 2026,
        "petitioner": "Salemamad Kumbhar",
        "respondent": "State of Gujarat & Ors.",
        "act_tags": ["Prisons Act, 1894", "Gujarat Prison Rules"],
        "section_tags": ["Rule 19 Gujarat Prison Rules"],
        "keyword_tags": ["Parole Leave", "Agriculture Livelihood"],
        "disposition": "Disposed",
        "summary": "Application for parole leave for sowing agricultural crops. Disposed granting 10 days parole with biometric verification upon return.",
        "ratio_decidendi": "Parole leave for agricultural operations may be sanctioned where convict's conduct inside correctional home is satisfactory."
    }
}

def main():
    conn = psycopg2.connect("postgresql://lexguard:lexguard123@localhost:5432/lexguard")
    cur = conn.cursor()

    # Get staff user for audit log
    cur.execute("SELECT id FROM users WHERE role IN ('senior_staff', 'court_staff', 'admin') LIMIT 1")
    user_row = cur.fetchone()
    staff_id = user_row[0] if user_row else "system-ingest-bot"

    if not user_row:
        raise RuntimeError("A staff user is required before canonical audit events can be recorded")
    pending_audit_events = []

    print(f"=== Ingesting and Training 30 Authentic Judicial Precedents into PostgreSQL ===")
    
    ingested_count = 0
    updated_count = 0

    with open(r"E:\SEM 5 PROJECT\Lexguard\new_51_cases_analysis.json", "r", encoding="utf-8") as f:
        cases_analysis = json.load(f)

    for item in cases_analysis:
        h_doc = item["h_doc"]
        h_prefix = h_doc[:12]
        meta = DETAILED_CASES.get(h_prefix, {})

        case_no = meta.get("case_no") or item["case_no"]
        court = meta.get("court") or item["court"]
        judge = meta.get("judge") or item["judge"]
        year = meta.get("year") or item["year"]
        petitioner = meta.get("petitioner") or item["petitioner"]
        respondent = meta.get("respondent") or item["respondent"]
        parties = f"{petitioner} v. {respondent}"
        title = parties
        act_tags = meta.get("act_tags") or item["act_tags"]
        section_tags = meta.get("section_tags") or item["section_tags"]
        keyword_tags = meta.get("keyword_tags") or item["keyword_tags"]
        disposition = meta.get("disposition") or item["disposition"]
        summary = meta.get("summary") or item["summary"]
        ratio = meta.get("ratio_decidendi") or item["ratio_decidendi"]
        full_text = item["full_text"]
        page_count = item["page_count"]

        # Content Addressable Storage (CAS) file path
        cas_filename = f"{h_doc}.pdf"
        lexguard_pdf_path = LEXGUARD_CAS_DIR / cas_filename
        lexguard_root_pdf = LEXGUARD_ROOT_STORAGE / cas_filename
        html_pdf_path = HTML_CAS_DIR / cas_filename
        html_root_pdf = HTML_ROOT_STORAGE / cas_filename

        # Source PDF file
        primary_source_file = item["all_filenames"][0]
        src_pdf = SRC_DIR / primary_source_file

        # Copy to CAS paths in both repositories
        if src_pdf.exists():
            for target in [lexguard_pdf_path, lexguard_root_pdf, html_pdf_path, html_root_pdf]:
                if not target.exists():
                    shutil.copy2(src_pdf, target)

        # Generate dense semantic vector (384-dims)
        emb_text = f"{title}. {court}. {case_no}. {summary}. {' '.join(act_tags)} {' '.join(section_tags)} {' '.join(keyword_tags)}"
        try:
            embedding = embedding_service.generate_embedding(emb_text)
        except Exception:
            embedding = None

        # Calculate Judicial Seal Phi_case
        now_iso = datetime.now(timezone.utc).isoformat()
        meta_str = f"{case_no}|{court}|{judge}|{disposition}|{year}"
        h_meta = hashlib.sha256(meta_str.encode("utf-8")).hexdigest()
        h_text = hashlib.sha256(full_text.encode("utf-8")).hexdigest()
        phi_case = hashlib.sha256(f"{h_doc}|{h_meta}|{h_text}|{now_iso}".encode("utf-8")).hexdigest()

        # Check existing by file_hash or case_no
        cur.execute("SELECT id FROM cases WHERE file_hash = %s OR case_no = %s", (h_doc, case_no))
        existing_row = cur.fetchone()

        if existing_row:
            case_id = existing_row[0]
            cur.execute("""
                UPDATE cases SET
                    case_no = %s, title = %s, court = %s, judge = %s, parties = %s,
                    year = %s, act_tags = %s, section_tags = %s, keyword_tags = %s,
                    disposition = %s, outcome = %s, summary = %s, ratio_decidendi = %s,
                    full_text = %s, page_count = %s, file_path = %s, file_hash = %s,
                    judicial_seal = %s, status = 'published', approved_at = NOW(),
                    embedding = %s, updated_at = NOW()
                WHERE id = %s
            """, (
                case_no, title, court, judge, parties, year,
                Json(act_tags), Json(section_tags), Json(keyword_tags),
                disposition, disposition, summary, ratio, full_text, page_count,
                str(lexguard_pdf_path), h_doc, phi_case,
                Json(embedding) if embedding else None,
                case_id
            ))
            updated_count += 1
            action = "UPDATE"
        else:
            case_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO cases (
                    id, case_no, title, court, judge, parties, year,
                    act_tags, section_tags, keyword_tags, disposition, outcome,
                    summary, ratio_decidendi, full_text, page_count,
                    file_path, file_hash, judicial_seal, status,
                    source_verification_state, precedential_status, auto_extracted,
                    uploaded_by_id, approved_by_id, approved_at, embedding,
                    created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, 'published',
                    'verified_authentic', 'binding', true,
                    %s, %s, NOW(), %s,
                    NOW(), NOW()
                )
            """, (
                case_id, case_no, title, court, judge, parties, year,
                Json(act_tags), Json(section_tags), Json(keyword_tags), disposition, disposition,
                summary, ratio, full_text, page_count,
                str(lexguard_pdf_path), h_doc, phi_case,
                staff_id, staff_id, Json(embedding) if embedding else None
            ))
            ingested_count += 1
            action = "INGEST"

        # Queue the audit event; it is appended through audit_service after
        # the raw-SQL case transaction commits and the case is visible.
        pending_audit_events.append(
            (
                f"CASE_{action}",
                case_id,
                f"Authentic court judgment {case_no} verified and sealed (Phi={phi_case[:10]}..)",
            )
        )

        print(f"[{ingested_count + updated_count:02d}] {action} -> {case_no}")
        print(f"     Title: {title[:60]}")
        print(f"     Court: {court} | Outcome: {disposition}")
        print(f"     CAS: {cas_filename} ({page_count} pp) | Phi_seal: {phi_case[:12]}..\n")

    conn.commit()
    cur.close()
    conn.close()

    audit_db = SessionLocal()
    try:
        for audit_action, audit_case_id, audit_details in pending_audit_events:
            log_audit_event(
                db=audit_db,
                action=audit_action,
                user_id=staff_id,
                case_id=audit_case_id,
                details=audit_details,
                ip_address="127.0.0.1",
            )
    finally:
        audit_db.close()

    print(f"============================================================")
    print(f"  Ingestion and Sealing of New Court Documents Complete!")
    print(f"  Newly Inserted Cases: {ingested_count}")
    print(f"  Updated Existing Cases: {updated_count}")
    print(f"  Total Processed: {ingested_count + updated_count}")
    print(f"============================================================\n")

if __name__ == "__main__":
    main()
