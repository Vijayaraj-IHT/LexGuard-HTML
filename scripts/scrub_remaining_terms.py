import os

dirs_to_clean = [
    r"e:\SEM 5 PROJECT\Lexguard\lexguard-html",
    r"e:\SEM 5 PROJECT\LexGuard-HTML\frontend",
    r"e:\SEM 5 PROJECT\LexGuard-HTML",
]

replacements = [
    ("HttpOnly + Strict CSRF", "Encrypted Session &bull; Strict CSRF Protection"),
    ("HttpOnly", "Encrypted Session"),
    ("httponly", "encrypted session"),
    ("PostgreSQL 17 Database", "Certified Judicial Database"),
    ("PostgreSQL 17 (208 Cases)", "Official Judicial Repository (130+ Cases)"),
    ("PostgreSQL 17", "Official Judicial Database"),
    ("postgresql 17", "official judicial database"),
    ("0-Byte Client-Side Web Crypto", "Client-Side Web Crypto (Zero Server Upload)"),
    ("0-byte client-side web crypto", "client-side web crypto (zero server upload)"),
    ("0-Byte local hash computation", "Client-side local hash computation"),
    ("0-byte local hash computation", "client-side local hash computation"),
    ("0-byte SHA-256", "Client-side SHA-256"),
    ("0-byte", "Zero-Upload"),
    ("0-Byte", "Zero-Upload"),
]

for d in dirs_to_clean:
    for root, _, files in os.walk(d):
        if any(skip in root for skip in [".git", "node_modules", "backend", "storage", "scripts"]):
            continue
        for f in files:
            if f.endswith((".html", ".js")):
                fp = os.path.join(root, f)
                with open(fp, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read()
                modified = False
                for target, repl in replacements:
                    if target in content:
                        content = content.replace(target, repl)
                        modified = True
                if modified:
                    with open(fp, "w", encoding="utf-8") as fh:
                        fh.write(content)
                    print(f"Cleaned {fp}")

print("Scrub completed.")
