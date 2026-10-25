"""
Seed the Top 12 Fundamental Indian Codified Statutes into PostgreSQL.
Provides authentic bare act legislative text and judicial commentary for Acts Explorer.
"""
import sys
import os
import psycopg2

DB_URI = "postgresql://lexguard:lexguard123@localhost:5432/lexguard"

STATUTES_DATA = [
    # 1. Code of Criminal Procedure, 1973
    {
        "act_code": "CRPC",
        "act_title": "Code of Criminal Procedure, 1973",
        "section_no": "482",
        "section_title": "Saving of Inherent Powers of High Court",
        "bare_text": "Nothing in this Code shall be deemed to limit or affect the inherent powers of the High Court to make such orders as may be necessary to give effect to any order under this Code, or to prevent abuse of the process of any Court or otherwise to secure the ends of justice.",
        "explanation": "High Courts exercise extraordinary inherent jurisdiction under Section 482 to quash malicious or groundless FIRs, complaints, and criminal proceedings to prevent abuse of judicial process, guided by the landmark Bhajan Lal parameters."
    },
    {
        "act_code": "CRPC",
        "act_title": "Code of Criminal Procedure, 1973",
        "section_no": "439",
        "section_title": "Special Powers of High Court or Court of Session Regarding Bail",
        "bare_text": "(1) A High Court or Court of Session may direct that any person accused of an offence and in custody be released on bail, and if the offence is of the nature specified in sub-section (3) of section 437, may impose any condition which it considers necessary for the purposes mentioned in that sub-section.",
        "explanation": "Provides wide discretionary powers to Sessions Courts and High Courts to grant regular post-arrest bail to an accused person, balancing personal liberty under Article 21 with societal interests and flight risk."
    },
    {
        "act_code": "CRPC",
        "act_title": "Code of Criminal Procedure, 1973",
        "section_no": "438",
        "section_title": "Direction for Grant of Bail to Person Apprehending Arrest",
        "bare_text": "(1) Where any person has reason to believe that he may be arrested on an accusation of having committed a non-bailable offence, he may apply to the High Court or the Court of Session for a direction under this section that in the event of such arrest he shall be released on bail.",
        "explanation": "Anticipatory bail safeguards citizens against politically motivated, vindictive, or unjustified arrests, imposing conditions requiring cooperation with the investigating agency."
    },
    {
        "act_code": "CRPC",
        "act_title": "Code of Criminal Procedure, 1973",
        "section_no": "313",
        "section_title": "Power to Examine the Accused",
        "bare_text": "(1) In every inquiry or trial, for the purpose of enabling the accused personally to explain any circumstances appearing in the evidence against him, the Court may at any stage, without previously warning the accused, put such questions to him as the Court considers necessary.",
        "explanation": "Mandatory statutory duty of the trial court to personally question the accused on every incriminating piece of evidence, giving the accused an opportunity to explain circumstances without being sworn as a witness."
    },

    # 2. Indian Penal Code, 1860
    {
        "act_code": "IPC",
        "act_title": "Indian Penal Code, 1860",
        "section_no": "420",
        "section_title": "Cheating and Dishonestly Inducing Delivery of Property",
        "bare_text": "Whoever cheats and thereby dishonestly induces the person deceived to deliver any property to any person, or to make, alter or destroy the whole or any part of a valuable security, or anything which is signed or sealed, and which is capable of being converted into a valuable security, shall be punished with imprisonment of either description for a term which may extend to seven years, and shall also be liable to fine.",
        "explanation": "Requires clear proof of fraudulent or dishonest intention right at the inception of the transaction. A mere breach of civil contract does not constitute an offence under Section 420."
    },
    {
        "act_code": "IPC",
        "act_title": "Indian Penal Code, 1860",
        "section_no": "498A",
        "section_title": "Husband or Relative of Husband of a Woman Subjecting Her to Cruelty",
        "bare_text": "Whoever, being the husband or the relative of the husband of a woman, subjects such woman to cruelty shall be punished with imprisonment for a term which may extend to three years and shall also be liable to fine.",
        "explanation": "Enacted to curb dowry harassment and domestic cruelty. Governed by Arnesh Kumar guidelines requiring Section 41A CrPC notice before arrest to prevent generalized roping in of distant relatives."
    },
    {
        "act_code": "IPC",
        "act_title": "Indian Penal Code, 1860",
        "section_no": "302",
        "section_title": "Punishment for Murder",
        "bare_text": "Whoever commits murder shall be punished with death, or imprisonment for life, and shall also be liable to fine.",
        "explanation": "The ultimate penal provision for culpable homicide amounting to murder under Section 300 IPC. Capital punishment is restricted strictly to the 'rarest of rare' doctrine as established in Bachan Singh."
    },

    # 3. Constitution of India
    {
        "act_code": "CONST",
        "act_title": "Constitution of India, 1950",
        "section_no": "226",
        "section_title": "Power of High Courts to Issue Certain Writs",
        "bare_text": "(1) Notwithstanding anything in article 32, every High Court shall have power, throughout the territories in relation to which it exercises jurisdiction, to issue to any person or authority, including in appropriate cases, any Government, within those territories directions, orders or writs, including writs in the nature of habeas corpus, mandamus, prohibition, quo warranto and certiorari, or any of them, for the enforcement of any of the rights conferred by Part III and for any other purpose.",
        "explanation": "The cornerstone of High Court judicial review in India, empowering benches to enforce fundamental rights and strike down arbitrary executive actions under both constitutional and administrative law."
    },
    {
        "act_code": "CONST",
        "act_title": "Constitution of India, 1950",
        "section_no": "21",
        "section_title": "Protection of Life and Personal Liberty",
        "bare_text": "No person shall be deprived of his life or personal liberty except according to procedure established by law.",
        "explanation": "The bedrock of Indian human rights jurisprudence, expanded by the Supreme Court in Maneka Gandhi to require that procedure must be 'just, fair, and reasonable', encompassing speedy trial, privacy, and humane bail."
    },

    # 4. Negotiable Instruments Act, 1881
    {
        "act_code": "NI_ACT",
        "act_title": "Negotiable Instruments Act, 1881",
        "section_no": "138",
        "section_title": "Dishonour of Cheque for Insufficiency, etc., of Funds in the Account",
        "bare_text": "Where any cheque drawn by a person on an account maintained by him with a banker for payment of any amount of money to another person from out of that account for the discharge, in whole or in part, of any debt or other liability, is returned by the bank unpaid, either because of the amount of money standing to the credit of that account is insufficient to honour the cheque or that it exceeds the amount arranged to be paid from that account by an agreement made with that bank, such person shall be deemed to have committed an offence and shall, without prejudice to any other provision of this Act, be punished with imprisonment for a term which may be extended to two years, or with fine which may extend to twice the amount of the cheque, or with both.",
        "explanation": "Criminalizes commercial cheque bounces. Strict procedural timeline: statutory demand notice within 30 days of dishonour, 15 days cure period, and complaint filing within one month thereafter."
    },
    {
        "act_code": "NI_ACT",
        "act_title": "Negotiable Instruments Act, 1881",
        "section_no": "139",
        "section_title": "Presumption in Favour of Holder",
        "bare_text": "It shall be presumed, unless the contrary is proved, that the holder of a cheque received the cheque of the nature referred to in section 138 for the discharge, in whole or in part, of any debt or other liability.",
        "explanation": "Creates a reverse statutory presumption against the drawer. The accused can rebut this presumption not by strict proof beyond reasonable doubt, but on a preponderance of probabilities as held in Rangappa."
    },

    # 5. NDPS Act, 1985
    {
        "act_code": "NDPS",
        "act_title": "Narcotic Drugs and Psychotropic Substances Act, 1985",
        "section_no": "37",
        "section_title": "Offences to be Cognizable and Non-Bailable",
        "bare_text": "(1) Notwithstanding anything contained in the Code of Criminal Procedure, 1973... no person accused of an offence punishable for offences under section 19 or section 24 or section 27A and also for offences involving commercial quantity shall be released on bail unless the Public Prosecutor has been given an opportunity to oppose, and the court is satisfied that there are reasonable grounds for believing that he is not guilty of such offence.",
        "explanation": "Imposes stringent twin conditions for bail in commercial quantity narcotic seizures, severely restricting judicial discretion unless threshold innocence is established."
    },

    # 6. Arbitration and Conciliation Act, 1996
    {
        "act_code": "ARB",
        "act_title": "Arbitration and Conciliation Act, 1996",
        "section_no": "34",
        "section_title": "Application for Setting Aside Arbitral Award",
        "bare_text": "(1) Recourse to a Court against an arbitral award may be made only by an application for setting aside such award in accordance with sub-section (2) and sub-section (3).",
        "explanation": "Grounds for setting aside domestic awards are strictly limited to patent illegality, public policy violation, or procedural invalidity under Associate Builders and Ssangyong Engineering principles."
    },
    {
        "act_code": "ARB",
        "act_title": "Arbitration and Conciliation Act, 1996",
        "section_no": "9",
        "section_title": "Interim Measures, etc., by Court",
        "bare_text": "(1) A party may, before or during arbitral proceedings or at any time after the making of the arbitral award but before it is enforced in accordance with section 36, apply to a court for an interim measure of protection.",
        "explanation": "Equips commercial litigants with injunctive safeguards to preserve disputed assets or status quo before or during arbitration proceedings."
    },

    # 7. Protection of Children from Sexual Offences Act, 2012
    {
        "act_code": "POCSO",
        "act_title": "POCSO Act, 2012",
        "section_no": "29",
        "section_title": "Presumption as to Certain Offences",
        "bare_text": "Where a person is prosecuted for committing or abetting or attempting to commit any offence under sections 3, 5, 7 and section 9 of this Act, the Special Court shall presume, that such person has committed or abetted or attempted to commit the offence, as the case may be unless the contrary is proved.",
        "explanation": "Statutory presumption of guilt once foundational facts of sexual assault against a minor are proven by the prosecution, placing reverse burden on the defence."
    },

    # 8. Prevention of Money Laundering Act, 2002
    {
        "act_code": "PMLA",
        "act_title": "Prevention of Money Laundering Act, 2002",
        "section_no": "45",
        "section_title": "Offences to be Cognizable and Non-Bailable",
        "bare_text": "(1) Notwithstanding anything contained in the Code of Criminal Procedure, 1973, no person accused of an offence under this Act shall be released on bail or on his own bond unless the Public Prosecutor has been given an opportunity to oppose the application for such release.",
        "explanation": "Requires court satisfaction that the accused is not guilty of money laundering and not likely to commit any offence while on bail (Twin Conditions upheld in Vijay Madanlal Choudhary)."
    },

    # 9. Specific Relief Act, 1963
    {
        "act_code": "SRA",
        "act_title": "Specific Relief Act, 1963",
        "section_no": "16",
        "section_title": "Personal Bars to Relief",
        "bare_text": "Specific performance of a contract cannot be enforced in favour of a person who has failed to prove that he has performed or has always been ready and willing to perform the essential terms of the contract which were to be performed by him.",
        "explanation": "Requires the plaintiff seeking execution of sale deed to continuously aver and prove continuous readiness and financial willingness from date of agreement until date of decree."
    },

    # 10. Code of Civil Procedure, 1908
    {
        "act_code": "CPC",
        "act_title": "Code of Civil Procedure, 1908",
        "section_no": "100",
        "section_title": "Second Appeal to High Court",
        "bare_text": "(1) Save as otherwise expressly provided in the body of this Code or by any other law for the time being in force, an appeal shall lie to the High Court from every decree passed in appeal by any Court subordinate to the High Court, if the High Court is satisfied that the case involves a substantial question of law.",
        "explanation": "Second appeals are strictly limited to substantial questions of law, barring High Courts from re-appreciating pure questions of concurrent factual finding."
    },

    # 11. Prevention of Corruption Act, 1988
    {
        "act_code": "PCA",
        "act_title": "Prevention of Corruption Act, 1988",
        "section_no": "19",
        "section_title": "Previous Sanction Necessary for Prosecution",
        "bare_text": "(1) No court shall take cognizance of an offence punishable under sections 7, 11, 13 and 15 alleged to have been committed by a public servant, except with the previous sanction of the competent authority.",
        "explanation": "Protects public servants against vexatious prosecution for bona fide official decisions, requiring prior independent appraisal by the sanctioning authority."
    },

    # 12. Indian Evidence Act, 1872
    {
        "act_code": "IEA",
        "act_title": "Indian Evidence Act, 1872",
        "section_no": "65B",
        "section_title": "Admissibility of Electronic Records",
        "bare_text": "(1) Notwithstanding anything contained in this Act, any information contained in an electronic record which is printed on a paper, stored, recorded or copied in optical or magnetic media... shall be deemed to be also a document.",
        "explanation": "Governed by the Supreme Court ruling in Arjun Panditrao, making production of a Section 65B(4) certificate mandatory condition precedent for admitting secondary electronic evidence (CCTV, CDR, WhatsApp)."
    }
]

def seed_statutes():
    print("=" * 65)
    print("SEEDING TOP 12 CODIFIED INDIAN STATUTES INTO DATABASE")
    print("=" * 65)

    conn = psycopg2.connect(DB_URI)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # 1. Create table if not exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS statute_sections (
                id VARCHAR(36) PRIMARY KEY,
                act_code VARCHAR(20) NOT NULL,
                act_title VARCHAR(150) NOT NULL,
                section_no VARCHAR(20) NOT NULL,
                section_title VARCHAR(200) NOT NULL,
                bare_text TEXT NOT NULL,
                explanation TEXT,
                case_count INTEGER DEFAULT 0 NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_statute_sections_act_code ON statute_sections (act_code);
            CREATE INDEX IF NOT EXISTS ix_statute_sections_section_no ON statute_sections (section_no);
        """)
        print(" [+] Ensured 'statute_sections' table exists.")

        inserted = 0
        updated = 0
        import uuid

        for item in STATUTES_DATA:
            cur.execute("""
                SELECT id FROM statute_sections WHERE act_code = %s AND section_no = %s;
            """, (item["act_code"], item["section_no"]))
            existing = cur.fetchone()

            # Count cases in database that reference this section
            sec_query = f"%{item['section_no']}%"
            cur.execute("""
                SELECT count(*) FROM cases 
                WHERE section_tags::text ILIKE %s OR act_tags::text ILIKE %s;
            """, (sec_query, f"%{item['act_code']}%"))
            c_count = cur.fetchone()[0]

            if existing:
                cur.execute("""
                    UPDATE statute_sections
                    SET act_title = %s,
                        section_title = %s,
                        bare_text = %s,
                        explanation = %s,
                        case_count = %s
                    WHERE id = %s;
                """, (item["act_title"], item["section_title"], item["bare_text"], item["explanation"], c_count, existing[0]))
                updated += 1
            else:
                new_id = str(uuid.uuid4())
                cur.execute("""
                    INSERT INTO statute_sections (id, act_code, act_title, section_no, section_title, bare_text, explanation, case_count)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """, (new_id, item["act_code"], item["act_title"], item["section_no"], item["section_title"], item["bare_text"], item["explanation"], c_count))
                inserted += 1

        conn.commit()
        print(f" [+] Seeding finished! Inserted: {inserted}, Updated: {updated}.")
        print("=" * 65)

    except Exception as e:
        conn.rollback()
        print(" [-] Seeding failed:", e)
        raise e
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    seed_statutes()
