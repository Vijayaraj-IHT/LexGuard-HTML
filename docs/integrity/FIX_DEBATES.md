# LexGuard Integrity Fixes — Three-Role Review

Each proposed fix was reviewed by three roles before any code was changed:

- **Agent 1 — Advocate (why suitable):** argues for the fix, citing evidence.
- **Agent 2 — Challenger (why not suitable):** argues against it: risk, breakage, better alternatives.
- **Agent 3 — Judge:** weighs both and returns a verdict: `ACCEPT`, `ACCEPT WITH CHANGES`, `DEFER` (needs a human decision), or `REJECT`.

All three roles were run in one working session. They are separate lines of reasoning, not independent reviewers. Anything marked `DEFER` was not changed.

Evidence references (`lexguard.db`, read-only checks) come from the integrity audit recorded earlier in this branch.

---

## F0 — Application does not import on Python 3.11

**Problem.** `backend/app/api/v1/endpoints/bookmarks.py:247` uses a backslash inside an f-string expression (`{c.judge or 'Hon\'ble Bench'}`). That is only legal on Python 3.12+. The README advertises Python 3.10–3.12, and `py_compile` on 3.11 fails for this one file.

**Agent 1 (for).** The fix is a one-line change: move the literal out of the f-string. It is valid on all supported versions and removes a hard import failure that blocks the whole API.

**Agent 2 (against).** One could instead declare Python 3.12 the minimum. But that breaks the README's stated support matrix for no real gain. Also, other f-strings might hide similar issues. A full `py_compile` pass across the repo found only this file.

**Agent 3 (judge).** `ACCEPT`. The alternative is worse and the change has no behavioural effect. The compile scan covers every tracked `.py` file.

---

## F1 — One audit-chain writer; fix every writer that breaks the chain

**Problem.** Chain breaks in `lexguard.db` have four causes:

1. `scripts/seed_35_*`, `seed_55_*`, `seed_final_20_*`, `seed_landmark_precedents.py` store `current_hash = file_hash` and never link to the previous entry. This accounts for 148 rows, all failing.
2. `scripts/batch_ingest_judgments.py` uses `sha256(action:details:prev)`, not the canonical formula.
3. `scripts/sync_all_cases_to_db.py` hashes the raw timestamp string. All 33 `AUTO_INGEST_PDF` rows fail.
4. `backend/batch_ingest_1000.py` hashes one `details` string but stores a different one. All 110 `CASE_BATCH_*` rows fail.

Also, `normalize_timestamp` treats a naive datetime as **server-local** time. Measured result: the chain check reports 720 mismatches under `TZ=UTC` and 755 under `TZ=Asia/Kolkata`. Verification therefore depends on the machine it runs on.

**Agent 1 (for).** Add one helper in `audit_service.py` (`get_chain_head_hash`, `build_audit_entry`). Route every writer through it. Make naive timestamps UTC so the result is the same on every machine. This removes the root cause rather than patching each symptom.

**Agent 2 (against).**
- Rebuilding the chain would be easier, but it rewrites history and destroys evidence. Reject that.
- Changing `normalize_timestamp` could break the 35 naive rows that verify today. Mitigation: the rows verify under the UTC interpretation in the sandbox, and the sandbox is UTC. So the UTC interpretation is the one the writers used.
- The seed and ingest scripts run against Postgres or SQLite with raw SQL. A helper written for SQLAlchemy won't serve them. Mitigation: the helper is pure Python. The raw-SQL scripts only need the head hash and the canonical hash function.
- Fixing writers does not repair the existing 720 bad rows. True — that is a separate decision (see D1).

**Agent 3 (judge).** `ACCEPT WITH CHANGES`:
- Writers only. Do not modify stored rows. Repair of existing data is deferred (D1).
- Naive timestamps are treated as UTC. Document this and test it.
- Scripts that write raw SQL get the same canonical formula. Only compile-check and the helper unit test are required, because running them needs live databases.

---

## F2 — Test script writes to the live database and forks the chain

**Problem.** `backend/tests/test_7_tables.py` inserts a `TEST_VERIFY_ACTION` row into whatever database `settings` points to. It uses the genesis hash as its parent, not the current head, so it forks the chain at record 31.

**Agent 1 (for).** Require an explicit `LEXGUARD_ALLOW_TEST_WRITES=1` before it writes anything. When it does write, chain from the real head via the shared helper. Nothing is lost, and accidental writes stop.

**Agent 2 (against).** Skipping the test entirely would be simpler, but it also removes coverage of the seven tables. Mitigation: keep the test; only gate the writes.

**Agent 3 (judge).** `ACCEPT`. Gate the write and use the shared helper.

---

## F3 — File-hash cache can approve a tampered file

**Problem.** `crypto_service.compute_sha256_stream` caches digests keyed by `(path, mtime_ns, size)`. Demonstrated: a same-size byte edit followed by restoring the mtime (`os.utime`) makes `verify_sha256_stream` return **True** for the tampered file.

**Agent 1 (for).** Remove the cache. Integrity checks must read the bytes every time. The cache gives no security value and makes verification lie.

**Agent 2 (against).** Re-hashing a 20 MB PDF on every stream costs time. Mitigation: a judicial PDF is read once per request, and hashing costs roughly 20 ms. An alternative keyed on `ctime`/inode was considered and rejected: it is still spoofable by anyone who controls the clock, and it adds complexity.

**Agent 3 (judge).** `ACCEPT`. Remove the cache. The added cost is small.

---

## F4 — `/cases/{id}/download` sends `X-Lexguard-Verified: true` without checking

**Problem.** `cases.py` (`download_case`) serves the file and sets `X-Lexguard-Verified: true`. It never hashes the file. The stream endpoint does check, but download does not.

**Agent 1 (for).** Hash the file (streamed) before serving. On mismatch: quarantine the case, write an `INTEGRITY_VIOLATION` audit entry, and return 409. Set the header only after a real match. This makes the header true.

**Agent 2 (against).** This changes a download path that users depend on. A 409 on a stored mismatch is the intended behaviour, so the risk is limited to real corruption.

**Agent 3 (judge).** `ACCEPT`. Mirror the stream endpoint's behaviour.

---

## F5 — Lookup labels claim checks that never run

**Problem.** `verification.py` hard-codes `audit_label="Audit chain verified"` and returns `integrity_status="VERIFIED_OFFICIAL_RECORD"` on a DB hash match alone, without reading the file or the chain. The frontend (`verify.js`) reads `res.audit_trail`, which the backend never returns, so the audit table always shows "no records". Its per-row "Verified" badge is static text.

**Agent 1 (for).** Compute what the label says:
- Return `audit_trail`: the last 10 entries for the case. Each one carries `recomputed_ok` (its own hash recomputes) and `link_ok` (its parent exists).
- Set `audit_label` from those results.
- Rename the status to `REGISTRY_MATCH`, which says what was checked. Nothing in the frontend reads the old value.
- Render per-row badges from the real result.

**Agent 2 (against).** Full-chain verification on every lookup is expensive, so the per-lookup check is only local. The label must not claim more than that. Mitigation: label it "latest entries verified", and keep full-chain verification on the audit-ledger page.

**Agent 3 (judge).** `ACCEPT WITH CHANGES`. Use the honest, narrower wording. Do not call the lookup a full-chain verification.

---

## F6 — Judicial seal cannot be checked, and redaction branch misuses it

**Problem.**
- `admin.py` computes the seal (Φ_case) on approval. Nothing recomputes it later. Measured: of 84 sealed cases, 2 reproduce from current data. 75 have no approval log at all, and 7 changed metadata after sealing.
- `verification.py` (stream) uses `case.redacted_file_hash` as the expected **file** hash. That column holds the seal. Redaction never existed (`redacted_file_path` is empty for every case). If it were ever set, every scholar or public stream would fail and quarantine the case.

**Agent 1 (for).** Move the seal formula into one function and use it on approval. Add a staff endpoint that recomputes the seal and reports whether it reproduces. Stop using the seal as a file hash. Refuse with 501 when a redacted path is set, since that feature is not built.

**Agent 2 (against).**
- Changing the seal formula would invalidate the two seals that reproduce today. Mitigation: keep the formula byte-for-byte identical.
- Refusing with 501 is a behaviour change for any future redacted case. Mitigation: no such case exists.
- Existing broken seals are not repaired by this change. True — that is deferred (D1).

**Agent 3 (judge).** `ACCEPT WITH CHANGES`. Formula unchanged. Add the staff check. Replace the misuse with an explicit 501. No stored seal is rewritten.

---

## F7 — Published records can be edited, and uploaders can approve their own uploads

**Problem.**
- `PATCH /cases/{id}` and `POST /cases/{id}/re-extract` have no status guard. The code comment says edits happen "prior to judicial seal approval", but nothing enforces it. Re-extraction overwrites `full_text` and identity fields after publication.
- `POST /admin/approve/{id}` has no maker-checker rule. Measured: 573 of 606 published cases were approved by the same account that uploaded them.

**Agent 1 (for).** Return 409 for PATCH and re-extract on published records, which is what the comment already says. Return 403 when an uploader tries to approve their own published submission.

**Agent 2 (against).**
- Blocking edits breaks staff workflows that correct published metadata. Mitigation: the workflow is reject, edit, resubmit. This is a documented breaking change and the UI needs a message.
- The maker-checker rule blocks solo staff. Mitigation: the rule only applies to publishing, and the repo has a second senior-staff account.
- Existing self-approved records remain. True, and they are not touched by this change.

**Agent 3 (judge).** `ACCEPT WITH CHANGES`. Apply both rules to `published` only. Surface the breaking change in the response message. Leave existing data alone.

---

## F8 — No read-only way to see the integrity state

**Problem.** Every check above was done by hand. There is no repeatable report.

**Agent 1 (for).** A read-only report script that counts chain breaks by action, checks seal reproducibility, self-approvals, published-without-seal, and file hashes on disk.

**Agent 2 (against).** A report script is not a fix. Mitigation: it is the evidence base for D1. It can also run in CI.

**Agent 3 (judge).** `ACCEPT`. It must open the database read-only.

---

## Deferred — need a human decision

| ID | Item | Why deferred |
|----|------|--------------|
| D1 | Repair existing data in `backend/lexguard.db` (rebuild the chain as a new sealed segment, re-seal or flag cases) | Rewrites tracked data and destroys the current evidence trail. Needs an explicit go-ahead and a backup decision. |
| D2 | Stop tracking `lexguard.db` and the SQL dumps; rewrite git history to remove them | History rewrite affects every clone. Needs the owner's approval. |
| D3 | Rotate the bcrypt hashes and personal email addresses present in the dumps | Credential rotation is outside code changes. |
| D4 | HMAC-sign the audit chain with a server-held key and anchor the head externally | Needs key management and a choice of anchor location. |
| D5 | Hard-coded `API_BASE = http://127.0.0.1:8000` in `lexguard-core.js` | Deployment choice; the right value depends on where the app is hosted. |

---

## Implementation record (what was actually done)

Roles were played by one session, not by independent reviewers. The verdicts above were applied as written, except where the notes below record a correction found by testing.

**Corrections found during implementation**

- **F1, SQLite timezone.** SQLite drops tzinfo on write. An aware `+05:30` timestamp written through the ORM reads back as wall-clock naive and is then hashed as UTC, so the chain breaks. `build_audit_entry` now converts every timestamp to aware UTC before hashing and storing. Measured before the change: `2026-10-12 05:44:10+05:30` read back as naive, and its hash did not match.
- **F1, naive-as-UTC is confirmed by data.** All 35 naive rows in `lexguard.db` match when read as UTC and none match as IST, so the stated convention matches the stored data.
- **F1, existing failures are not timestamp artifacts.** Against the current code, 505 of 1661 rows fail hash recomputation (all timezone-aware rows; no normalization variant recovers them). The earlier figure of 720 came from an ad-hoc script with a different method. The `integrity_report.py` figure is the authoritative one. Writers can be fixed; these rows can only be repaired under D1.
- **F1, extra writers found.** `scripts/ingest_30_new_cases.py` (custom hash over `NOW()`, plus a seal that could never reproduce) and `scripts/remove_cases_lacking_pdfs.py` (hard-coded genesis parent, custom hash) were not in the original list. Both now use the shared builder. The ingest script also records one `approved_at` instant and computes the seal from that same instant.
- **F7, existing tests updated.** Three tests encoded the old behaviour: a PATCH on a published record, a self-approval, and a self-approval in the end-to-end test. They now use an unpublished record, a different approver, and a separate client for the second login. The end-to-end test also asserts the new 403 for the uploader.
- **F7, frontend messages.** The PATCH, re-extract, and approve handlers in `case-review.js` now show the server's `detail` (the 409 and 403 explanations) instead of a generic error.
- **Frontend wording.** `audit-ledger.js` said "Merkle … 100% Verified" in its success branch. The chain is linear, so the wording now says "Audit hash chain: full chain verified". The logic (driven by `is_valid`) is unchanged.

**Tests**

- `backend/tests/test_integrity_fixes.py`: 12 tests covering F0–F8. Mutation check: reverting the UTC conversion fails 2 F1 tests; disabling the download hash check fails F4; disabling the maker-checker check fails F7. The restored code passes all 12.
- Full suite on a pristine copy of the committed `lexguard.db`: 53 passed, 1 failed, 7 skipped. The failure is `test_milestone1` search ranking. The HEAD code (with only the F0 import fix) fails the same assertion, so it predates these changes and comes from the missing `sentence_transformers` model in this venv.
- Full suite on an empty temporary DB: 6 fail. All need seeded users or published cases from `lexguard.db` (login and published-case fixtures).
- `tests/test_7_tables.py` is excluded from the runs; it now refuses to write without `LEXGUARD_ALLOW_TEST_WRITES=1`.

**Not done (not in F0–F8, not yet reviewed)**

From the audit's remaining findings, these have no debate record and were not changed: the `SECRET_KEY`, `CSRF_SECRET`, and DB-password defaults in `config.py`; the `COOKIE_SECURE` default; dev seeding with known passwords in `main.py`; the CSP `'unsafe-inline'`; the in-memory rate limiter; the bare `except` in `upload-auto`; the static "verified" badge in `case-viewer.html` and the `integrity_status="verified"` default in `schemas/case.py`; the README claims (208 cases, 989 records, "Merkle"); and the `database/*.sql` dumps containing personal data. Each needs its own three-role review before any change.

---

# Round 2 — audit items without a prior debate record

Facts gathered before the review:

- The backend serves no HTML. `run_lexguard.sh` serves the frontend with `python -m http.server 8888`, so **no CSP applies to any page**. The CSP header exists only on uvicorn JSON responses.
- Six pages contain inline `<script>` blocks, two use inline `on*=` handlers, and 104 elements use `style="..."`.
- `CSRF_SECRET` is defined in `config.py` and `.env.example` and is never read.
- Demo seeding runs when `ENVIRONMENT == "development"`, which is the default. The known credentials also appear in `login.html` quick-fill buttons, `README.md`, and several scripts.
- `/cases/{id}/view` computes `integrity_status` at runtime (verified / tampered / file_missing), so the schema default `"verified"` is always overwritten before a client sees it.
- `case-viewer.html` has a static "VERIFIED UNALTERED RECORD" badge in the Digital Seal Certificate modal. No JavaScript fills the certificate fields (`cert-*` ids), so the sheet shows dashes plus the badge. Line 120 has a static "Verified Copy" line in the page header.
- Upload-auto (`cases.py` ~318-330): the file is renamed on disk, then the DB is committed. If the commit fails, the file is at the new path while the DB still points at the old one. The `except Exception: pass` hides this.
- `rate_limit.py`: `_request_history` never removes keys. Every window in use is 60 s.

---

## G1 — Config defaults: secrets, unused CSRF secret, production gating

**Proposer.** Remove the unused `CSRF_SECRET`. Warn at startup when the default `SECRET_KEY` is in use. Make the production check in `lifespan` use the same rule as the validator (`!= "development"`).

**Skeptic.** Changing defaults breaks local setups. A warning is noise. `DATABASE_URL` carries a local password, and that is a development default, so it should stay. The validator already refuses the default key and `COOKIE_SECURE=False` outside development.

**Judge.** `ACCEPT WITH CHANGES`.
- Remove `CSRF_SECRET` from `config.py` and `.env.example`. It is dead configuration with a hardcoded value.
- Log a warning (not an error) in development when the default `SECRET_KEY` is used.
- Align the `lifespan` condition with the validator.
- Leave `DATABASE_URL` and `ENVIRONMENT` defaults as they are. Changing them is a deployment decision.

## G2 — Demo accounts with known passwords are seeded by default

**Proposer.** Gate demo seeding behind `SEED_DEMO_ACCOUNTS`, default `False`. `.env.example` turns it on for local development.

**Skeptic.** Fresh clones without a `.env` lose the quick-fill logins. The tracked `lexguard.db` and the dumps still contain these accounts, so the flag does not remove the credentials (that is D3). Some local scripts assume the seeded users exist.

**Judge.** `ACCEPT WITH CHANGES`. Default off, and `.env.example` on. The README must document the flag. D3 stays deferred, and the report must say that the tracked data still holds the accounts.

## G3 — CSP `'unsafe-inline'` in script-src

**Proposer.** Remove `'unsafe-inline'` from `script-src`.

**Skeptic.** The header covers only JSON responses, which contain no scripts. The pages have no CSP at all because `http.server` sets none. Making the pages CSP-safe means moving the inline scripts and handlers out of six pages and two handlers, and the 104 inline style attributes still need `style-src 'unsafe-inline'`. That is a change to every page.

**Judge.** `ACCEPT` for the header only. Removing `'unsafe-inline'` from the API `script-src` is zero-risk. The actual gap is that **pages have no CSP**. Fixing it needs inline-script extraction and a page-level policy, which touches every page. This is recorded as **D6** and needs your approval.

## G4 — In-memory rate limiter

**Proposer.** Prune stale keys so memory stays bounded. Document the limits.

**Skeptic.** The limiter is not an integrity control. Behind a reverse proxy every client shares one IP. It is per process. Trusting `X-Forwarded-For` would let clients spoof their IP.

**Judge.** `ACCEPT WITH CHANGES`. Bound memory only. Do not trust forwarded headers. State the per-process, per-IP limits in the code. A shared limiter (for example Redis) is a new dependency and is out of scope.

## G5 — Bare `except` around post-persist rename in upload-auto

**Proposer.** Replace the silent `pass`. If the rename fails, keep the file where it is. If the DB commit fails after the rename, roll back, move the file back, and log.

**Skeptic.** The rename is cosmetic, so logging alone would be enough.

**Judge.** `ACCEPT`. Logging alone leaves the file/DB mismatch in place. Roll back and restore the file so the record stays consistent.

## G6 — Static "verified" claims in the UI and schema

**Proposer.** Use neutral text for the header and certificate. When the certificate opens, call `verifyIntegrity` and set the badge and hash from the response. Change the schema default to `"not_checked"`.

**Skeptic.** Filling certificate fields is scope creep and needs design work. The schema default is never sent, so changing it has no effect.

**Judge.** `ACCEPT WITH CHANGES`. Set only the integrity badge and hash from the verify response. Do not add new certificate fields. Change the schema default for consistency; it does not change behaviour.

## G7 — README claims

**Proposer.** Replace "Merkle" with "hash-chained". Replace hardcoded counts with the measured values for the tracked `lexguard.db` (607 cases, 1661 audit records, 505 failing hash recomputation), and point to `integrity_report.py`.

**Skeptic.** The counts may describe the SQL dumps, not `lexguard.db`. Removing them loses information.

**Judge.** `ACCEPT WITH CHANGES`. Describe `lexguard.db` only with measured numbers. Make no claims about the dumps, which were not verified in this round.

---

## Round 2 deferred

| ID | Item | Why deferred |
|----|------|--------------|
| D6 | Page-level CSP for the frontend (move 6 inline scripts and 2 inline handlers out of HTML; decide on style-src) | Touches every page; needs your approval. |

## Round 2 implementation record

- **G1 done.** `CSRF_SECRET` removed from `config.py` and `.env.example`. Startup logs a warning when the default development `SECRET_KEY` is in use. The lifespan production check now uses the validator's rule (`!= "development"`). `DATABASE_URL` and `ENVIRONMENT` defaults are unchanged.
- **G2 done.** New setting `SEED_DEMO_ACCOUNTS` (default `False`). Demo seeding requires `ENVIRONMENT=development` and the flag. `.env.example` sets it to `True`. README documents it. The credentials still exist in the tracked `lexguard.db` and the dumps (D3).
- **G3 done (header only).** API responses no longer allow `'unsafe-inline'` scripts. `style-src` is unchanged. The frontend pages have no CSP; that gap is **D6**.
- **G4 done.** Stale keys are pruned once the table exceeds 5000 keys. A lock guards the shared dict, because sync dependencies run in the thread pool. X-Forwarded-For is not trusted. Limits are documented in the module.
- **G5 done.** The rename is wrapped separately from the DB commit. A rename failure keeps the file where the row points. A commit failure rolls back, moves the file back, and logs. No silent `pass`. **Test coverage:** the rename-failure branch is tested. The commit-failure branch is not covered by a test.
- **G6 done.** The viewer's "Verified Copy" line and the static "VERIFIED UNALTERED RECORD" badge are gone. The certificate badge starts as "INTEGRITY NOT CHECKED". It is set from `verify-integrity` when the sheet opens. The schema default is now `"not_checked"`. Nothing else in the certificate was filled in.
- **G7 done.** "Merkle" and the hardcoded case counts are replaced. The README gives the measured `lexguard.db` numbers (607 cases, 1661 audit records, 505 hash failures), taken from a read-only run of `integrity_report.py`. The dumps were not verified, so no claims are made about them.

**Tests.** `test_integrity_fixes.py` now has 19 tests (G1–G7 added). Full suite on a copy of the committed `lexguard.db`: 60 passed, 1 failed, 7 skipped. The failure is the known search-ranking test, which needs `sentence_transformers`.
