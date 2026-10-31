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
