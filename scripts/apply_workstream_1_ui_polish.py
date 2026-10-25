"""
Workstream 1: UI Terminology Cleanup & Professionalization.
Modifies frontend HTML and JS files in both Lexguard and LexGuard-HTML repositories.
Preserves all required DOM element IDs.
"""
import os
import re

LEXGUARD_DIR = "e:/SEM 5 PROJECT/Lexguard"
HTML_REPO_DIR = "e:/SEM 5 PROJECT/LexGuard-HTML"

def clean_file(filepath: str, replacements: list):
    if not os.path.exists(filepath):
        print(f" [!] File not found: {filepath}")
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    original = content
    for pattern, repl in replacements:
        if callable(repl):
            content = re.sub(pattern, repl, content)
        else:
            content = content.replace(pattern, repl)

    if content != original:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f" [+] Updated: {filepath}")
    else:
        print(f" [i] No changes needed: {filepath}")


def run_ui_polish():
    print("=" * 65)
    print("APPLYING WORKSTREAM 1: UI POLISH & TERMINOLOGY CLEANUP")
    print("=" * 65)

    # 1. Update lexguard-nav.js in both repositories
    nav_replacements = [
        # Academic comment
        ("* Semester 5 Project · ", "* "),
        # Top government bar text
        ("HIGH COURT OF JUDICATURE AT MADRAS • Chennai Principal Seat & Madurai Bench", "JUDICIAL DIGITAL ARCHIVE • High Court & Supreme Court Judgments"),
        ("PostgreSQL 17 Active", "System Status: Online"),
        ("CIS Version 3.2 Standard", "Certified Digital Repository"),
        # Subtitle
        ("JUDICIAL REPOSITORY &bull; OPEN LEGAL INFORMATION SYSTEM", "JUDICIAL CASE REPOSITORY"),
        ("JUDICIAL REPOSITORY • OPEN LEGAL INFORMATION SYSTEM", "JUDICIAL CASE REPOSITORY"),
        # Remove 0-byte badge
        ('<span class="lg-sidebar-badge">0-byte</span>', ''),
        # Sidebar footer
        ('<span class="text-light fw-semibold">LexGuard v2.4</span> · Madras HC &amp; SC', '<span class="text-light fw-semibold">LexGuard Judicial Archive</span>'),
        ('<span class="text-light fw-semibold">LexGuard v2.4</span> · Madras HC & SC', '<span class="text-light fw-semibold">LexGuard Judicial Archive</span>'),
    ]

    for base in [LEXGUARD_DIR, HTML_REPO_DIR]:
        sub_path = "lexguard-html/js/lexguard-nav.js" if base == LEXGUARD_DIR else "frontend/js/lexguard-nav.js"
        fpath = os.path.join(base, sub_path)
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                c = f.read()
            # Remove Visual Showcase nav item from sidebar
            c = re.sub(r'<li>\s*<a href="screenshots-gallery\.html".*?</li>', '', c, flags=re.DOTALL)
            for p, r in nav_replacements:
                c = c.replace(p, r)
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(c)
            print(f" [+] Polished: {fpath}")

    # 2. Update lexguard-auth.js and lexguard-crypto.js
    for base in [LEXGUARD_DIR, HTML_REPO_DIR]:
        for fname in ["lexguard-auth.js", "lexguard-crypto.js"]:
            sub_path = f"lexguard-html/js/{fname}" if base == LEXGUARD_DIR else f"frontend/js/{fname}"
            fpath = os.path.join(base, sub_path)
            clean_file(fpath, [("* Semester 5 Project · ", "* ")])

    # 3. Update index.html (landing page) across all locations
    index_files = [
        os.path.join(LEXGUARD_DIR, "lexguard-html", "index.html"),
        os.path.join(HTML_REPO_DIR, "index.html"),
        os.path.join(HTML_REPO_DIR, "frontend", "index.html"),
    ]

    old_trust_row = """        <div class="col-md-3 col-sm-6">
          <div class="trust-stat-card text-center">
            <div class="h3 fw-bold text-dark font-serif mb-1">Madras HC</div>
            <div class="small text-secondary">Principal Seat &amp; Madurai Bench</div>
          </div>
        </div>
        <div class="col-md-3 col-sm-6">
          <div class="trust-stat-card text-center">
            <div class="h3 fw-bold text-danger font-serif mb-1">208 Verified</div>
            <div class="small text-secondary">Precedents in PostgreSQL 17</div>
          </div>
        </div>
        <div class="col-md-3 col-sm-6">
          <div class="trust-stat-card text-center">
            <div class="h3 fw-bold text-success font-serif mb-1">916 Blocks</div>
            <div class="small text-secondary">SHA-256 Chained Merkle Ledger</div>
          </div>
        </div>
        <div class="col-md-3 col-sm-6">
          <div class="trust-stat-card text-center">
            <div class="h3 fw-bold text-dark font-serif mb-1">Zero-Tamper</div>
            <div class="small text-secondary">Public Verification Engine</div>
          </div>
        </div>"""

    new_trust_row = """        <div class="col-md-3 col-sm-6">
          <div class="trust-stat-card text-center">
            <div class="h3 fw-bold text-dark font-serif mb-1" id="stat-courts-count">Appellate &amp; Writ</div>
            <div class="small text-secondary">Full Bench &amp; Division Bench Judgments</div>
          </div>
        </div>
        <div class="col-md-3 col-sm-6">
          <div class="trust-stat-card text-center">
            <div class="h3 fw-bold text-danger font-serif mb-1" id="stat-cases-count">130 Verified</div>
            <div class="small text-secondary">Authenticated Judicial Orders</div>
          </div>
        </div>
        <div class="col-md-3 col-sm-6">
          <div class="trust-stat-card text-center">
            <div class="h3 fw-bold text-success font-serif mb-1" id="stat-audit-count">Audit Register</div>
            <div class="small text-secondary">Tamper-Evident Access Log</div>
          </div>
        </div>
        <div class="col-md-3 col-sm-6">
          <div class="trust-stat-card text-center">
            <div class="h3 fw-bold text-dark font-serif mb-1">Certified Copies</div>
            <div class="small text-secondary">Instant Document Authenticity Check</div>
          </div>
        </div>"""

    old_footer = """  <!-- Footer -->
  <footer class="py-4 bg-white border-top border-danger border-opacity-15 text-center text-secondary small">
    <div class="container d-flex flex-column flex-md-row align-items-center justify-content-between gap-2">
      <div class="d-flex align-items-center gap-2 text-dark font-serif">
        <i class="bi bi-shield-shaded text-danger"></i>
        <span>LexGuard Judicial Case Repository &bull; Open Legal Information System</span>
      </div>
      <div>
        Secured with HttpOnly Cryptographic Tokens &bull; <a href="screenshots-gallery.html" class="text-danger text-decoration-none fw-semibold">Visual Showcase</a>
      </div>
    </div>
  </footer>"""

    new_footer = """  <!-- Footer -->
  <footer class="py-4 bg-white border-top border-danger border-opacity-15 text-center text-secondary small">
    <div class="container d-flex flex-column flex-md-row align-items-center justify-content-between gap-2">
      <div class="d-flex align-items-center gap-2 text-dark font-serif">
        <i class="bi bi-shield-shaded text-danger"></i>
        <span>&copy; LexGuard Judicial Repository &bull; Official Case Information System</span>
      </div>
      <div>
        <a href="verify.html" class="text-secondary text-decoration-none me-3"><i class="bi bi-patch-check me-1"></i>Verify a Certified Copy</a>
        <span class="text-muted">Terms of Access &bull; Certified Archive</span>
      </div>
    </div>
  </footer>"""

    for ifile in index_files:
        if not os.path.exists(ifile):
            continue
        with open(ifile, "r", encoding="utf-8") as f:
            ic = f.read()

        ic = ic.replace("HIGH COURT OF JUDICATURE AT MADRAS", "JUDICIAL DIGITAL ARCHIVE")
        ic = ic.replace("Chennai Principal Seat &amp; Madurai Bench", "High Court &amp; Supreme Court Judgments")
        ic = ic.replace("PostgreSQL 17 Live", "Certified Digital Repository")
        ic = ic.replace("PostgreSQL 17", "Certified Repository")
        ic = ic.replace(old_trust_row, new_trust_row)
        ic = ic.replace(old_footer, new_footer)
        # Also clean brand subtitle
        ic = ic.replace("JUDICIAL REPOSITORY &bull; OPEN LEGAL INFORMATION SYSTEM", "JUDICIAL CASE REPOSITORY")

        with open(ifile, "w", encoding="utf-8") as f:
            f.write(ic)
        print(f" [+] Polished landing page: {ifile}")

    # 4. Update case-viewer.html: Wrap hash in details toggle
    for base in [LEXGUARD_DIR, HTML_REPO_DIR]:
        sub_path = "lexguard-html/case-viewer.html" if base == LEXGUARD_DIR else "frontend/case-viewer.html"
        cv_path = os.path.join(base, sub_path)
        if not os.path.exists(cv_path):
            continue
        with open(cv_path, "r", encoding="utf-8") as f:
            cv = f.read()

        # Update title text
        cv = cv.replace("Cryptographically Verified Judicial Record", "Authenticated Judicial Record &bull; Verified Copy")

        # Wrap #case-seal-hash inside <details> if not already wrapped
        if '<summary' not in cv and 'id="case-seal-hash"' in cv:
            old_hash_div = '<div class="small font-mono text-secondary text-break" style="font-size: 0.76rem;" id="case-seal-hash">\n              SHA-256: Computing...\n            </div>'
            old_hash_div2 = '<div class="small font-mono text-secondary text-break" style="font-size: 0.76rem;" id="case-seal-hash">SHA-256: Computing...</div>'
            
            new_hash_details = """<details class="small text-secondary mt-1">
              <summary style="cursor: pointer; font-size: 0.78rem;">View Digital Seal Details</summary>
              <div class="small font-mono text-secondary text-break mt-1" style="font-size: 0.76rem;" id="case-seal-hash">
                SHA-256: Computing...
              </div>
            </details>"""

            if old_hash_div in cv:
                cv = cv.replace(old_hash_div, new_hash_details)
            elif old_hash_div2 in cv:
                cv = cv.replace(old_hash_div2, new_hash_details)
            else:
                cv = re.sub(
                    r'<div[^>]*id="case-seal-hash"[^>]*>.*?</div>',
                    new_hash_details,
                    cv,
                    flags=re.DOTALL
                )

        with open(cv_path, "w", encoding="utf-8") as f:
            f.write(cv)
        print(f" [+] Polished Case Viewer seal ribbon: {cv_path}")

    # 5. Update login.html (gate demo test accounts and polish disclaimers)
    for base in [LEXGUARD_DIR, HTML_REPO_DIR]:
        sub_path = "lexguard-html/login.html" if base == LEXGUARD_DIR else "frontend/login.html"
        lp = os.path.join(base, sub_path)
        if not os.path.exists(lp):
            continue
        with open(lp, "r", encoding="utf-8") as f:
            lc = f.read()

        # Wrap test accounts in #demo-accounts-card with d-none
        if 'id="demo-accounts-card"' not in lc and '<!-- Quick-Fill Test Accounts -->' in lc:
            lc = lc.replace(
                '<!-- Quick-Fill Test Accounts -->\n        <div class="mt-4 pt-3 border-top border-secondary border-opacity-15">',
                '<!-- Quick-Fill Test Accounts (Gated by ?demo=1) -->\n        <div id="demo-accounts-card" class="mt-4 pt-3 border-top border-secondary border-opacity-15 d-none">'
            )

        # Polish disclaimers
        lc = lc.replace('Protected by Merkle Audit Log &amp; CIS Extraction Verification', 'Authorized Judicial &amp; Bar Portal &bull; Access is logged for compliance')
        lc = lc.replace('Protected by Merkle Audit Log & CIS Extraction Verification', 'Authorized Judicial &amp; Bar Portal &bull; Access is logged for compliance')
        lc = lc.replace('Madras High Court (Principal &amp; Madurai Bench) · Supreme Court of India', 'Official Case Information System &bull; Certified Judicial Digital Repository')
        lc = lc.replace('Madras High Court (Principal & Madurai Bench) · Supreme Court of India', 'Official Case Information System &bull; Certified Judicial Digital Repository')

        with open(lp, "w", encoding="utf-8") as f:
            f.write(lc)
        print(f" [+] Polished Login page: {lp}")

    # 6. Update login.js to unhide demo accounts if ?demo=1
    for base in [LEXGUARD_DIR, HTML_REPO_DIR]:
        sub_path = "lexguard-html/js/pages/login.js" if base == LEXGUARD_DIR else "frontend/js/pages/login.js"
        ljp = os.path.join(base, sub_path)
        if not os.path.exists(ljp):
            continue
        with open(ljp, "r", encoding="utf-8") as f:
            lj = f.read()

        demo_check = """  // Unhide demo test accounts if ?demo=1 or stored in localStorage
  if (window.location.search.includes('demo=1') || window.location.search.includes('test=1') || localStorage.getItem('lexguard_demo') === '1') {
    $('#demo-accounts-card').removeClass('d-none');
  }
"""
        if 'demo-accounts-card' not in lj:
            lj = lj.replace("$(document).ready(function () {", "$(document).ready(function () {\n" + demo_check)

        with open(ljp, "w", encoding="utf-8") as f:
            f.write(lj)
        print(f" [+] Updated Login JS demo gating: {ljp}")

    print("=" * 65)
    print("WORKSTREAM 1 COMPLETED SUCCESSFULLY")
    print("=" * 65)

if __name__ == "__main__":
    run_ui_polish()
