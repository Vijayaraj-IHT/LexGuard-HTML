import os
import pptx
from pptx.util import Inches, Pt
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

def create_presentation():
    prs = pptx.Presentation()
    prs.slide_width = Inches(10)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    # Palette
    CRIMSON = RGBColor(153, 27, 27)    # #991b1b
    MAROON = RGBColor(127, 29, 29)     # #7f1d1d
    LIGHT_BG = RGBColor(248, 250, 252) # #f8fafc
    SLATE = RGBColor(15, 23, 42)       # #0f172a
    BORDER = RGBColor(185, 28, 28)     # #b91c1c
    BLUE_ACCENT = RGBColor(30, 58, 138)
    GREEN_ACCENT = RGBColor(22, 101, 52)

    def add_header(slide, title, figure_tag):
        # Header Box
        header_box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(0.4), Inches(9.0), Inches(0.8))
        header_box.fill.solid()
        header_box.fill.fore_color.rgb = CRIMSON
        header_box.line.color.rgb = MAROON
        tf = header_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = f"{figure_tag}: {title}"
        p.font.size = Pt(16)
        p.font.bold = True
        p.font.color.rgb = RGBColor(255, 255, 255)
        p.alignment = PP_ALIGN.CENTER

    # -------------------------------------------------------------
    # SLIDE 1: FIGURE 3.1 - USE CASE DIAGRAM
    # -------------------------------------------------------------
    s1 = prs.slides.add_slide(blank_layout)
    add_header(s1, "Use Case Diagram for Lexguard Platform", "Figure 3.1")

    # Boundary Box
    b_box = s1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(2.8), Inches(1.5), Inches(4.4), Inches(5.5))
    b_box.fill.solid()
    b_box.fill.fore_color.rgb = LIGHT_BG
    b_box.line.color.rgb = BORDER
    b_box.line.width = Pt(2)
    tf = b_box.text_frame
    p = tf.paragraphs[0]
    p.text = "LexGuard High Court Platform Boundary"
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = CRIMSON
    p.alignment = PP_ALIGN.CENTER

    # Actors Left
    actors_left = [
        ("Court Staff\n(Junior Registry)", Inches(0.6), Inches(2.0)),
        ("Senior Registrar\n(Approval)", Inches(0.6), Inches(3.6)),
        ("Advocate /\nLegal Practitioner", Inches(0.6), Inches(5.2))
    ]
    for name, left, top in actors_left:
        act = s1.shapes.add_shape(MSO_SHAPE.OVAL, left, top, Inches(1.8), Inches(1.0))
        act.fill.solid()
        act.fill.fore_color.rgb = RGBColor(224, 231, 255)
        act.line.color.rgb = BLUE_ACCENT
        tf = act.text_frame
        p = tf.paragraphs[0]
        p.text = name
        p.font.size = Pt(10)
        p.font.bold = True
        p.font.color.rgb = BLUE_ACCENT
        p.alignment = PP_ALIGN.CENTER

    # Use Cases (Ovals in Boundary)
    use_cases = [
        ("(Upload PDF Case Document)", Inches(3.2), Inches(2.0)),
        ("(Compute Streaming SHA-256)", Inches(3.2), Inches(2.7)),
        ("(Review Docket & Approve / Reject)", Inches(3.2), Inches(3.4)),
        ("(Precedent Hybrid Search & RRF)", Inches(3.2), Inches(4.1)),
        ("(AI Draft Studio Gap Analysis)", Inches(3.2), Inches(4.8)),
        ("(Multi-Precedent Comparator Matrix)", Inches(3.2), Inches(5.5)),
        ("(Verify Tamper-Evident SHA-256)", Inches(3.2), Inches(6.2))
    ]
    for text, left, top in use_cases:
        uc = s1.shapes.add_shape(MSO_SHAPE.OVAL, left, top, Inches(3.6), Inches(0.55))
        uc.fill.solid()
        uc.fill.fore_color.rgb = RGBColor(254, 242, 242)
        uc.line.color.rgb = CRIMSON
        tf = uc.text_frame
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(9.5)
        p.font.bold = True
        p.font.color.rgb = SLATE
        p.alignment = PP_ALIGN.CENTER

    # Actors Right
    actors_right = [
        ("Legal Scholar /\nResearcher", Inches(7.6), Inches(2.5)),
        ("Citizen /\nPublic Litigant", Inches(7.6), Inches(4.2)),
        ("System Cryptographic\nLedger (Automated)", Inches(7.6), Inches(5.8))
    ]
    for name, left, top in actors_right:
        act = s1.shapes.add_shape(MSO_SHAPE.OVAL, left, top, Inches(1.8), Inches(1.0))
        act.fill.solid()
        act.fill.fore_color.rgb = RGBColor(240, 253, 244)
        act.line.color.rgb = GREEN_ACCENT
        tf = act.text_frame
        p = tf.paragraphs[0]
        p.text = name
        p.font.size = Pt(10)
        p.font.bold = True
        p.font.color.rgb = GREEN_ACCENT
        p.alignment = PP_ALIGN.CENTER

    # -------------------------------------------------------------
    # SLIDE 2: FIGURE 3.2 - ACTIVITY DIAGRAM
    # -------------------------------------------------------------
    s2 = prs.slides.add_slide(blank_layout)
    add_header(s2, "Activity Diagram: Ingestion & Integrity Verification", "Figure 3.2")

    steps_act = [
        ("[Start] Staff Selects Judgment PDF", Inches(1.5), Inches(1.6), RGBColor(224, 231, 255)),
        ("Web Crypto API Computes Client SHA-256", Inches(1.5), Inches(2.4), RGBColor(248, 250, 252)),
        ("<Duplicate Check in PostgreSQL 17?>", Inches(1.5), Inches(3.2), RGBColor(254, 243, 199)),
        ("PyMuPDF Extracts Text & Legal NER Metadata", Inches(1.5), Inches(4.0), RGBColor(248, 250, 252)),
        ("InLegalBERT Dense Embedding Engine (384-d)", Inches(1.5), Inches(4.8), RGBColor(248, 250, 252)),
        ("Senior Registrar Reviews Metadata & Preview", Inches(1.5), Inches(5.6), RGBColor(254, 243, 199)),
        ("[Published] Hash-Chained Audit Ledger Logged", Inches(1.5), Inches(6.4), RGBColor(220, 252, 231))
    ]
    for text, left, top, bg_color in steps_act:
        shape = s2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, Inches(7.0), Inches(0.6))
        shape.fill.solid()
        shape.fill.fore_color.rgb = bg_color
        shape.line.color.rgb = CRIMSON
        shape.line.width = Pt(1.5)
        tf = shape.text_frame
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(10.5)
        p.font.bold = True
        p.font.color.rgb = SLATE
        p.alignment = PP_ALIGN.CENTER

    # -------------------------------------------------------------
    # SLIDE 3: FIGURE 3.3 - STATE DIAGRAM
    # -------------------------------------------------------------
    s3 = prs.slides.add_slide(blank_layout)
    add_header(s3, "State Diagram: Judgment Document Status Lifecycle", "Figure 3.3")

    states = [
        ("INITIAL\nUPLOAD", Inches(0.8), Inches(3.0), RGBColor(224, 231, 255), BLUE_ACCENT),
        ("PENDING_APPROVAL\n(CIS Review Queue)", Inches(2.8), Inches(3.0), RGBColor(254, 243, 199), RGBColor(180, 83, 9)),
        ("PUBLISHED\n(Searchable & Live)", Inches(5.2), Inches(3.0), RGBColor(220, 252, 231), GREEN_ACCENT),
        ("VERIFIED_ACTIVE\n(SHA-256 Match Badge)", Inches(7.6), Inches(2.0), RGBColor(209, 250, 229), GREEN_ACCENT),
        ("QUARANTINED_ALERT\n(Byte Tamper Mismatch)", Inches(7.6), Inches(4.2), RGBColor(254, 226, 226), CRIMSON),
        ("REJECTED\n(Archived / Dismissed)", Inches(2.8), Inches(5.2), RGBColor(241, 245, 249), RGBColor(71, 85, 105))
    ]
    for text, left, top, fill_c, line_c in states:
        box = s3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, Inches(1.9), Inches(1.1))
        box.fill.solid()
        box.fill.fore_color.rgb = fill_c
        box.line.color.rgb = line_c
        box.line.width = Pt(2)
        tf = box.text_frame
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(10)
        p.font.bold = True
        p.font.color.rgb = line_c
        p.alignment = PP_ALIGN.CENTER

    # -------------------------------------------------------------
    # SLIDE 4: FIGURE 3.4 - SEQUENCE DIAGRAM
    # -------------------------------------------------------------
    s4 = prs.slides.add_slide(blank_layout)
    add_header(s4, "Sequence Diagram: Search & Real-Time Verification", "Figure 3.4")

    actors_seq = [
        ("User (Advocate)", Inches(0.8)),
        ("Zero-Build Client", Inches(2.8)),
        ("FastAPI Gateway", Inches(4.8)),
        ("AI Microservice", Inches(6.8)),
        ("PostgreSQL 17", Inches(8.5))
    ]
    for name, left in actors_seq:
        col = s4.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, Inches(1.5), Inches(1.5), Inches(0.6))
        col.fill.solid()
        col.fill.fore_color.rgb = CRIMSON
        col.line.color.rgb = MAROON
        tf = col.text_frame
        p = tf.paragraphs[0]
        p.text = name
        p.font.size = Pt(9.5)
        p.font.bold = True
        p.font.color.rgb = RGBColor(255, 255, 255)
        p.alignment = PP_ALIGN.CENTER

        # Lifeline
        line = s4.shapes.add_shape(MSO_SHAPE.RECTANGLE, left + Inches(0.7), Inches(2.2), Inches(0.1), Inches(4.8))
        line.fill.solid()
        line.fill.fore_color.rgb = RGBColor(226, 232, 240)
        line.line.color.rgb = RGBColor(203, 213, 225)

    seq_messages = [
        ("1. Enter Query ('anticipatory bail') ->", Inches(0.8), Inches(2.5), Inches(3.5)),
        ("2. Forward Search Request ->", Inches(2.8), Inches(3.2), Inches(3.5)),
        ("3. Dense Embedding (InLegalBERT) ->", Inches(4.8), Inches(3.9), Inches(3.5)),
        ("<- 4. Return 384-d Vector Payload", Inches(4.8), Inches(4.6), Inches(3.5)),
        ("5. RRF Fusion (Cosine + Full-Text) ->", Inches(4.8), Inches(5.3), Inches(4.7)),
        ("<- 6. Stream Case Bytes & Recompute SHA-256", Inches(2.8), Inches(6.0), Inches(4.0))
    ]
    for msg, left, top, width in seq_messages:
        mbox = s4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, Inches(0.45))
        mbox.fill.solid()
        mbox.fill.fore_color.rgb = RGBColor(255, 255, 255)
        mbox.line.color.rgb = BLUE_ACCENT
        mbox.line.width = Pt(1)
        tf = mbox.text_frame
        p = tf.paragraphs[0]
        p.text = msg
        p.font.size = Pt(9)
        p.font.bold = True
        p.font.color.rgb = SLATE
        p.alignment = PP_ALIGN.LEFT

    # -------------------------------------------------------------
    # SLIDE 5: FIGURE 3.5 - ER DIAGRAM
    # -------------------------------------------------------------
    s5 = prs.slides.add_slide(blank_layout)
    add_header(s5, "Entity Relationship Diagram for LexGuard Schema", "Figure 3.5")

    entities = [
        ("USERS\nPK: id\nemail, password_hash\nrole, credential_id", Inches(0.8), Inches(1.8), RGBColor(224, 231, 255)),
        ("CASES (208 Master Records)\nPK: id, cnr_number\ntitle, court, year, judge\nsection_tags, act_tags, ratio\nfile_path, file_hash (SHA-256)", Inches(3.6), Inches(1.8), RGBColor(254, 242, 242)),
        ("AUDIT_LOGS (989 Blocks)\nPK: id\nFK: user_id, case_id\naction, timestamp, ip_address\nprevious_log_hash, current_hash", Inches(6.8), Inches(1.8), RGBColor(240, 253, 244)),
        ("APPROVAL_QUEUE\nPK: id\nFK: case_id\nsubmitted_by, reviewed_by\nstatus, review_note", Inches(0.8), Inches(4.6), RGBColor(254, 243, 199)),
        ("BOOKMARKS & BINDERS\nPK: id\nFK: user_id, case_id\nfolder_name, notes", Inches(3.6), Inches(4.6), RGBColor(243, 232, 255)),
        ("DRAFT_SESSIONS\nPK: id\nFK: user_id\ntitle, draft_text, citations", Inches(6.8), Inches(4.6), RGBColor(224, 242, 254))
    ]
    for text, left, top, fill_c in entities:
        box = s5.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, Inches(2.6), Inches(2.2))
        box.fill.solid()
        box.fill.fore_color.rgb = fill_c
        box.line.color.rgb = CRIMSON
        box.line.width = Pt(1.5)
        tf = box.text_frame
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(9.5)
        p.font.bold = True
        p.font.color.rgb = SLATE
        p.alignment = PP_ALIGN.LEFT

    # -------------------------------------------------------------
    # SLIDE 6: FIGURE 3.6 - DATA FLOW DIAGRAM
    # -------------------------------------------------------------
    s6 = prs.slides.add_slide(blank_layout)
    add_header(s6, "Data Flow Diagram: Level 0 Context & Level 1 Detailed", "Figure 3.6")

    # DFD Level 0 Box
    dfd0 = s6.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(1.6), Inches(8.4), Inches(2.2))
    dfd0.fill.solid()
    dfd0.fill.fore_color.rgb = LIGHT_BG
    dfd0.line.color.rgb = BLUE_ACCENT
    dfd0.line.width = Pt(1.5)
    tf = dfd0.text_frame
    p = tf.paragraphs[0]
    p.text = "LEVEL 0: CONTEXT DIAGRAM\n" \
             "[Court Staff] ---> (Case PDF + Metadata) ---> [ LEXGUARD PLATFORM ] ---> (Verified Case Views) ---> [Advocates]\n" \
             "[Public User] ---> (CNR Case Search)     ---> [ SYSTEM BOUNDARY   ] ---> (BNS Concordance)    ---> [Advocates]\n" \
             "[Court Staff] <--- (Audit Trail Records) <--- [ 989-Block Ledger ] <--- (Draft Gap Check)     <--- [Advocates]"
    p.font.size = Pt(10)
    p.font.bold = True
    p.font.color.rgb = SLATE
    p.alignment = PP_ALIGN.LEFT

    # DFD Level 1 Box
    dfd1 = s6.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(4.2), Inches(8.4), Inches(2.8))
    dfd1.fill.solid()
    dfd1.fill.fore_color.rgb = LIGHT_BG
    dfd1.line.color.rgb = CRIMSON
    dfd1.line.width = Pt(1.5)
    tf1 = dfd1.text_frame
    p1 = tf1.paragraphs[0]
    p1.text = "LEVEL 1: FUNCTIONAL DECOMPOSITION\n" \
              "1.0 Authentication: User Credentials --> Users DB (BCrypt Cost 12) --> JWT HttpOnly Cookie + Double CSRF\n" \
              "2.0 Ingestion & Hashing: Upload PDF --> Web Crypto API & SHA-256 --> NER Extractor --> Pending CIS Queue\n" \
              "3.0 CIS Workstation: Review Docket --> Senior Registrar Approval --> Update 'Published' --> Audit Ledger\n" \
              "4.0 Precedent Discovery: Legal Query --> InLegalBERT Vectors + Full-Text tsvector --> Reciprocal Rank Fusion\n" \
              "5.0 Integrity Viewer: Case View Request --> Real-Time Byte Re-Hash --> Compare Stored Hash --> Serve Badge\n" \
              "6.0 AI Draft Studio: Draft Paragraphs --> Extract Sections --> Concordance Mapper --> Return Missing Grounds"
    p1.font.size = Pt(9.5)
    p1.font.bold = True
    p1.font.color.rgb = SLATE
    p1.alignment = PP_ALIGN.LEFT

    # -------------------------------------------------------------
    # SLIDE 7: FIGURE 3.7 - SYSTEM ARCHITECTURE
    # -------------------------------------------------------------
    s7 = prs.slides.add_slide(blank_layout)
    add_header(s7, "System Architecture: Decoupled Zero-Build Services", "Figure 3.7")

    tiers = [
        ("PRESENTATION TIER (Zero-Build Pure HTML5 + Bootstrap 5 + jQuery + PDF.js + Chart.js)\n"
         "High Court Crimson & White Theme | Native Browser Web Crypto API SHA-256 Calculator", Inches(1.5), RGBColor(254, 242, 242), CRIMSON),
        ("SECURITY & APPLICATION GATEWAY TIER (FastAPI ASGI Server :8000)\n"
         "OWASP SecurityHeadersMiddleware | Double-Submit CSRF | HttpOnly Session Cookies | Role-Based Access Control", Inches(2.8), RGBColor(224, 231, 255), BLUE_ACCENT),
        ("DOMAIN AI & LEGAL INTELLIGENCE MICROSERVICE TIER (:8001)\n"
         "InLegalBERT Embedding Pipeline (384-d) | Reciprocal Rank Fusion | BNS / BNSS 2023 Concordance Engine", Inches(4.1), RGBColor(243, 232, 255), RGBColor(126, 34, 206)),
        ("ENTERPRISE PERSISTENCE & REPOSITORY TIER (PostgreSQL 17)\n"
         "208 Precedent Records | 989 Immutable Hash-Chained Audit Ledger Blocks | File Storage | Relational Indexes", Inches(5.4), RGBColor(240, 253, 244), GREEN_ACCENT)
    ]
    for text, top, fill_c, line_c in tiers:
        box = s7.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), top, Inches(8.4), Inches(1.0))
        box.fill.solid()
        box.fill.fore_color.rgb = fill_c
        box.line.color.rgb = line_c
        box.line.width = Pt(2)
        tf = box.text_frame
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(10)
        p.font.bold = True
        p.font.color.rgb = SLATE
        p.alignment = PP_ALIGN.CENTER

    ppt_path = r"E:\SEM 5 PROJECT\LexGuard-HTML\report_builder\LexGuard_UML_Architecture_Diagrams.pptx"
    prs.save(ppt_path)
    print(f"PowerPoint UML slides successfully saved to: {ppt_path}")

if __name__ == "__main__":
    create_presentation()
