"""
Thorough scrubber for all prohibited terms across HTML and JS files in both repositories.
"""
import os
import re

LEXGUARD_DIR = "e:/SEM 5 PROJECT/Lexguard"
HTML_REPO_DIR = "e:/SEM 5 PROJECT/LexGuard-HTML"

TARGET_DIRS = [
    os.path.join(LEXGUARD_DIR, "lexguard-html"),
    os.path.join(HTML_REPO_DIR, "frontend"),
    HTML_REPO_DIR,
]

REPLACEMENTS = [
    # Academic project comments in JS
    (r"\* Semester 5 Project · LexGuard Judicial Repository & Verification Platform", "* LexGuard Judicial Repository & Verification Platform"),
    (r"Semester 5 Project · ", ""),
    (r"Semester 5 Project", "LexGuard Platform"),
    
    # Tech stack / database leaking
    (r"PostgreSQL 17 Live", "Certified Digital Repository"),
    (r"PostgreSQL 17 Active", "System Status: Online"),
    (r"Precedents in PostgreSQL 17", "Authenticated Judicial Orders"),
    (r"in PostgreSQL 17", "in Judicial Archive"),
    (r"PostgreSQL 17", "Certified Repository"),
    
    # Internal blockchain / crypto jargon
    (r"916 Blocks", "Audit Register"),
    (r"SHA-256 Chained Merkle Ledger", "Tamper-Evident Access Log"),
    (r"Zero-Tamper", "Certified Copies"),
    (r"Public Verification Engine", "Instant Document Authenticity Check"),
    
    # Security tokens in footer
    (r"Secured with HttpOnly Cryptographic Tokens &bull; <a href=\"screenshots-gallery\.html\"[^>]*>Visual Showcase</a>", "<a href=\"verify.html\" class=\"text-secondary text-decoration-none me-3\"><i class=\"bi bi-patch-check me-1\"></i>Verify a Certified Copy</a><span class=\"text-muted\">Terms of Access &bull; Certified Archive</span>"),
    (r"Secured with HttpOnly Cryptographic Tokens", "Secured Judicial Repository"),
    
    # 0-byte badge
    (r'<span class="lg-sidebar-badge">0-byte</span>', ''),
    (r'<span class="badge bg-secondary[^"]*">0-byte</span>', ''),
    
    # Visual Showcase in public nav
    (r'<li>\s*<a href="screenshots-gallery\.html".*?</li>', ''),
    
    # Prototype disclaimers
    (r"Protected by Merkle Audit Log &amp; CIS Extraction Verification", "Authorized Judicial &amp; Bar Portal &bull; Access is logged for compliance"),
    (r"Protected by Merkle Audit Log & CIS Extraction Verification", "Authorized Judicial &amp; Bar Portal &bull; Access is logged for compliance"),
    (r"Official Legal Tech Prototype", "Official Case Information System"),
    
    # Subtitle
    (r"JUDICIAL REPOSITORY &bull; OPEN LEGAL INFORMATION SYSTEM", "JUDICIAL CASE REPOSITORY"),
    (r"JUDICIAL REPOSITORY • OPEN LEGAL INFORMATION SYSTEM", "JUDICIAL CASE REPOSITORY"),
]

def scrub_files():
    print("=" * 65)
    print("SCRUBBING ALL PROHIBITED TERMS PROJECT-WIDE")
    print("=" * 65)

    modified_count = 0
    for target in TARGET_DIRS:
        for root, dirs, files in os.walk(target):
            # Skip .git directory and screenshots folder
            if ".git" in root or "screenshots" in root or "backend" in root or "node_modules" in root:
                continue
            for f in files:
                if f.endswith((".html", ".js")) and f != "screenshots-gallery.html":
                    fpath = os.path.join(root, f)
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as fp:
                        content = fp.read()

                    original = content
                    for pattern, repl in REPLACEMENTS:
                        content = re.sub(pattern, repl, content)

                    if content != original:
                        with open(fpath, "w", encoding="utf-8") as fp:
                            fp.write(content)
                        print(f" [+] Scrubbed: {fpath}")
                        modified_count += 1

    print(f"\nTotal files cleaned: {modified_count}")
    print("=" * 65)

if __name__ == "__main__":
    scrub_files()
