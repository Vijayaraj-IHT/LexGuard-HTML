import os
import datetime

now = datetime.datetime.now()
recent = now - datetime.timedelta(hours=12)

scan_roots = [
    r"E:\SEM 5 PROJECT",
    r"C:\Users\Vijay Raj\Downloads",
]

print("=== Scanning specific roots for PDFs modified in last 12 hours ===")
found = []
for base in scan_roots:
    if not os.path.exists(base):
        continue
    for root, dirs, files in os.walk(base):
        # Skip git and node_modules
        if any(x in root for x in [".git", "node_modules", "venv", "__pycache__"]):
            continue
        for f in files:
            if f.lower().endswith(".pdf"):
                fp = os.path.join(root, f)
                try:
                    st = os.stat(fp)
                    mtime = datetime.datetime.fromtimestamp(st.st_mtime)
                    if mtime >= recent:
                        found.append((mtime, st.st_size, fp))
                except Exception:
                    pass

found.sort(key=lambda x: x[0], reverse=True)
print(f"Total matching PDFs found: {len(found)}")
for mtime, sz, fp in found:
    print(f"[{mtime.strftime('%Y-%m-%d %H:%M:%S')}] {sz:>9} bytes | {fp}")
