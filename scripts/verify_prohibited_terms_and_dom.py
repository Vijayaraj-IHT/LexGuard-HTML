import os

prohibited = [
    "PostgreSQL 17",
    "HttpOnly",
    "0-byte",
    "Visual Showcase",
    "916 Blocks",
    "Zero-Tamper",
    "Official Legal Tech Prototype",
    "Semester 5 Project",
]

dirs_to_check = [
    r"e:\SEM 5 PROJECT\Lexguard\lexguard-html",
    r"e:\SEM 5 PROJECT\LexGuard-HTML\frontend",
    r"e:\SEM 5 PROJECT\LexGuard-HTML",
]

print("=== PROHIBITED TERMS GREP ===")
violations = 0
checked_files = 0
for d in dirs_to_check:
    for root, _, files in os.walk(d):
        if any(skip in root for skip in [".git", "node_modules", "backend", "storage", "scripts"]):
            continue
        for f in files:
            if f.endswith((".html", ".js")):
                fp = os.path.join(root, f)
                checked_files += 1
                with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                    txt = fh.read()
                for p in prohibited:
                    if p.lower() in txt.lower():
                        print(f'VIOLATION in {fp}: found "{p}"')
                        violations += 1

print(f"Checked {checked_files} files. Total violations found: {violations}")

print("\n=== REQUIRED DOM IDS CHECK ===")
required_ids = ["case-seal-ribbon", "case-seal-hash"]
for hp in [r"e:\SEM 5 PROJECT\Lexguard\lexguard-html\case-viewer.html", r"e:\SEM 5 PROJECT\LexGuard-HTML\frontend\case-viewer.html"]:
    with open(hp, "r", encoding="utf-8") as f:
        c = f.read()
    for rid in required_ids:
        has_id = f'id="{rid}"' in c or f"id='{rid}'" in c
        print(f"{os.path.basename(hp)} -> {rid}: {'OK' if has_id else 'MISSING!'}")

for sp in [r"e:\SEM 5 PROJECT\Lexguard\lexguard-html\search.html", r"e:\SEM 5 PROJECT\LexGuard-HTML\frontend\search.html"]:
    if os.path.exists(sp):
        with open(sp, "r", encoding="utf-8") as f:
            c = f.read()
        print(f"{os.path.basename(sp)} -> results-container: {'OK' if 'results-container' in c else 'MISSING!'}")
