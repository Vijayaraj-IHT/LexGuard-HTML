import os
import re

html_dir = 'lexguard-html'
existing_files = set(os.listdir(html_dir))

print("=== Existing HTML Files in lexguard-html ===")
for f in sorted([f for f in existing_files if f.endswith('.html')]):
    print("  ", f)

# Scan for referenced .html files
referenced_html = set()
script_refs = set()
link_refs = set()

for root, dirs, files in os.walk(html_dir):
    for f in files:
        if f.endswith(('.html', '.js')):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8', errors='ignore') as fp:
                content = fp.read()
                # find .html files
                for m in re.finditer(r'([a-zA-Z0-9_\-]+\.html)', content):
                    referenced_html.add(m.group(1))
                # find script src
                for m in re.finditer(r'src=[\'"]([^\'"]+)[\'"]', content):
                    script_refs.add((os.path.relpath(path, '.'), m.group(1)))
                # find link href
                for m in re.finditer(r'href=[\'"]([^\'"]+\.css)[\'"]', content):
                    link_refs.add((os.path.relpath(path, '.'), m.group(1)))

print("\n=== Referenced HTML Files ===")
for f in sorted(referenced_html):
    status = "EXISTS" if f in existing_files else "MISSING (404!)"
    print(f"   {f:<28} [{status}]")

print("\n=== Checking Script/CSS Assets ===")
for page, src in sorted(script_refs):
    if not src.startswith(('http', '//')):
        # local file
        target_path = os.path.normpath(os.path.join(html_dir, src.lstrip('/')))
        if not os.path.exists(target_path):
            print(f"   [MISSING JS 404] In {page} -> {src} (not found at {target_path})")

for page, href in sorted(link_refs):
    if not href.startswith(('http', '//')):
        target_path = os.path.normpath(os.path.join(html_dir, href.lstrip('/')))
        if not os.path.exists(target_path):
            print(f"   [MISSING CSS 404] In {page} -> {href} (not found at {target_path})")
