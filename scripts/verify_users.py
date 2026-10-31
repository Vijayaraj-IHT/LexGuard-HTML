import sqlite3, re

# 1. SQLite users
conn = sqlite3.connect('backend/lexguard.db')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM users')
sqlite_user_count = cur.fetchone()[0]

cur.execute('SELECT id, email, name, role, status, credential_id, created_at FROM users ORDER BY role, name')
sqlite_users = cur.fetchall()
conn.close()

# 2. PostgreSQL Dump users
with open('database/database_dump.sql', 'r', encoding='utf-8') as f:
    sql = f.read()

m = re.search(r'COPY public\.users \((.*?)\) FROM stdin;\n(.*?)\n\\\.', sql, re.DOTALL)
if m:
    cols = [c.strip().strip('"') for c in m.group(1).split(',')]
    lines = m.group(2).strip().split('\n')
    pg_user_count = len(lines)
    pg_email_idx = cols.index('email') if 'email' in cols else 0
    pg_emails = set(l.split('\t')[pg_email_idx] for l in lines)
else:
    pg_user_count = 0
    pg_emails = set()

sqlite_emails = set(u[1] for u in sqlite_users)

print('=' * 115)
print('USER TABLE CROSS-VERIFICATION AUDIT')
print('=' * 115)
print(f'SQLite Users Count:       {sqlite_user_count}')
print(f'PostgreSQL Dump Users:    {pg_user_count}')
print(f'Count Match:              {"EXACT MATCH [100%]" if sqlite_user_count == pg_user_count else "MISMATCH"}')
print(f'Email Set Parity:         {"EXACT MATCH [100%]" if sqlite_emails == pg_emails else "MISMATCH"}')
print('-' * 115)
print(f'{"ROLE":<16} | {"EMAIL":<36} | {"NAME":<28} | {"STATUS":<10} | {"CREDENTIAL ID"}')
print('-' * 115)
for u in sqlite_users:
    uid, email, name, role, status, cred_id, created = u
    cred_str = cred_id if cred_id else '-'
    print(f'{role:<16} | {email:<36} | {name:<28} | {status:<10} | {cred_str}')
print('=' * 115)
