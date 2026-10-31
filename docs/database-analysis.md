# LexGuard database analysis: case handling

## 1. Executive summary

LexGuard is currently a **judgment/document repository with a staff publication workflow**, not a full live court case-management system. It stores case metadata, extracted judgment text, document hashes, approval state, bookmarks, draft sessions, and audit events. It does **not** store normalized hearings, cause-list entries, orders, litigation lifecycle events, or party roles as first-class tables.

The intended production database is **PostgreSQL**, accessed through **SQLAlchemy** from FastAPI. However, the backend silently falls back to a checked-in **SQLite** database when PostgreSQL cannot be reached. The supplied SQLite file, the two PostgreSQL dumps, and the ORM models are not schema-equivalent.

Most important findings:

1. **Database identity is ambiguous.** PostgreSQL is configured, SQLite is shipped, and the README points to a dump whose case count does not match the README text.
2. **The SQLite fallback is partially broken.** Bookmark queries fail because `bookmarks.binder_name` is missing; most case/audit indexes are absent.
3. **Referential integrity is not reliable.** The SQLite case table lacks foreign keys, and the newer PostgreSQL dump contains 327 case rows referencing a missing placeholder user as uploader and approver.
4. **The audit chain does not pass the application’s own verifier.** The first chain-link failure occurs at chronological index 31; a full replay found 215 link breaks and 505 hash mismatches.
5. **The approval workflow has gaps.** Auto-ingested cases do not create approval-queue entries, the shared frontend approval helper sends an invalid payload, and publication does not re-verify the document.
6. **Integrity/provenance labels are stronger than the checks behind them.** Download responses claim verification without hashing; hash lookup does not re-hash the file or recomposite the seal; “verified” source state can be set from a URL/watermark heuristic.
7. **Search is application-side, not database-native hybrid search.** Embeddings are JSON in the supplied dumps, only 132/607 SQLite cases have embeddings, and search loads candidates into Python before ranking/pagination.

Overall: the design is a reasonable prototype for a legal document repository, but it needs schema consolidation, integrity repair, workflow hardening, and clearer provenance before it can be treated as a trustworthy case system of record.

---

## 2. Scope and method

This analysis inspected:

- SQLAlchemy models, schemas, endpoints, services, startup scripts, migration scripts, ingestion scripts, and frontend API callers.
- The supplied SQLite database: `backend/lexguard.db`.
- The supplied PostgreSQL dumps: `database/database_dump.sql` and `database/lexguard_dump.sql`.
- Physical PDF references under `storage/cases/`.

Checks performed:

- Read-only SQLite profiling with `mode=ro`.
- SQLite `PRAGMA quick_check`, schema/index inspection, foreign-key inspection, orphan counts, duplicate counts, JSON/embedding profiling, and query-plan inspection.
- SHA-256 recomputation for all resolvable case PDFs.
- Parsing of PostgreSQL `COPY` sections for row counts, schema comparison, and foreign-key validation.
- Running the application’s audit-chain verifier against the SQLite database through SQLAlchemy 2.0.30 in read-only mode.
- Pydantic validation of the frontend approval payload and review metadata payload.

Not performed:

- No live PostgreSQL server was connected to or restored.
- No full application server or AI extraction pipeline was run.
- No database rows, PDFs, or application source files were modified.

---

## 3. Runtime database architecture

### 3.1 Connection selection

Relevant code:

- `backend/app/core/config.py`
- `backend/app/core/database.py`
- `backend/app/main.py`

Default configured URL:

```text
postgresql+psycopg2://lexguard:***@localhost:5432/lexguard
```

Runtime behavior:

```text
Settings.DATABASE_URL
        |
        v
SQLAlchemy create_engine()
        |
        +-- PostgreSQL reachable --> PostgreSQL engine
        |
        +-- PostgreSQL fails -----> sqlite:///./lexguard.db
                                      relative to process working directory
        |
        v
SessionLocal -> get_db() -> FastAPI endpoints
```

Important consequences:

- The fallback is automatic and only logged as a warning.
- The SQLite path is relative to the process working directory, so launching from a different directory can select or create a different database.
- The fallback warning includes the full target URL, which may expose credentials in logs.
- `/health` always returns `database_connected: true`; it does not probe the active engine.
- Startup uses `Base.metadata.create_all(bind=engine)`. This creates missing tables but does not migrate existing tables.
- In development, startup seeds demo users if absent.

### 3.2 PostgreSQL versus SQLite behavior

| Area | PostgreSQL path | SQLite fallback |
|---|---|---|
| Connection pooling | pool size 10, overflow 20, recycle 1800s | `check_same_thread=False` |
| JSON | JSON/JSONB columns in dumps | JSON stored as text |
| Embeddings | dumps use `json`, ORM may declare `VECTOR(384)` when `pgvector` is installed | JSON/list behavior in supplied file |
| Foreign keys | dump defines FKs | case/audit tables in supplied file lack FKs; SQLite enforcement is off by default |
| Indexes | dump defines many case/audit indexes | supplied SQLite file lacks most of them |
| Audit concurrency | attempts row lock on latest audit row | in-process mutex only |
| Migrations | ad hoc scripts, no Alembic | same ad hoc scripts, some PostgreSQL-specific |

---

## 4. Logical data model

The application has seven core tables plus a statute table.

| Table | Purpose | Key fields | Relationships |
|---|---|---|---|
| `users` | Accounts and RBAC | `id`, `email`, `password_hash`, `role`, `status`, `credential_id` | uploads/approvals, audit logs, bookmarks, drafts, approval queue |
| `cases` | Central judgment/case record | case number, CNR, court, year, judge, parties, tags, summary, ratio, full text, file path/hash, status, embeddings | uploader/approver users, versions, audit logs, bookmarks, approval queue |
| `document_versions` | Document version history | `case_id`, `version_no`, `file_path`, `file_hash`, `changed_by_id` | case, changing user |
| `approval_queue` | Staff review workflow | `case_id`, `submitted_by_id`, `reviewed_by_id`, `status`, review note/timestamps | case, submitter, reviewer |
| `audit_logs` | Hash-chained event ledger | user/case IDs, action, details, IP, user agent, timestamp, previous/current hash | optional user/case |
| `bookmarks` | User research binders | `user_id`, `case_id`, `binder_name`, notes | user, case; unique user/case pair |
| `draft_sessions` | Saved petition drafts | `user_id`, title, draft text, citations JSON, gap-analysis JSON | user |
| `statute_sections` | Bare-act sections | act code/title, section number/title, bare text, explanation, case count | no formal FK to cases |

### 4.1 Entity relationship overview

```mermaid
erDiagram
    users ||--o{ cases : uploads
    users ||--o{ cases : approves
    cases ||--o{ document_versions : has
    cases ||--o{ approval_queue : reviewed_through
    users ||--o{ approval_queue : submits
    users ||--o{ approval_queue : reviews
    cases ||--o{ audit_logs : referenced_by
    users ||--o{ audit_logs : performs
    users ||--o{ bookmarks : saves
    cases ||--o{ bookmarks : saved_as
    users ||--o{ draft_sessions : owns
    statute_sections ||..o{ cases : matched_by_tags_or_text
```

The statute relationship is logical only. There is no normalized `case_statutes` join table. Citations are also stored as JSON inside `cases.precedents_cited`, not as a foreign-key-backed citation graph.

### 4.2 The `cases` table is doing too many jobs

`cases` currently combines:

- Case identity: case number, CNR, case type, court, year.
- Judicial metadata: judge, bench, parties, counsel, decision date.
- Research metadata: acts, sections, keywords, domain, citation, precedential status.
- Extracted content: summary, layman summary, facts, issues, ratio, statutory tests, disposition, full text.
- Document storage: file path, file hash, redacted path/hash, page count.
- Search state: embedding.
- Workflow state: status, auto-extracted flag, uploader, approver, approval time.
- Provenance: source URL and source verification state.
- Legacy/extra state: `comparison_profile` exists in SQLite/newer PostgreSQL dump but not in the current ORM model.

This makes the table easy to query for a prototype, but it weakens versioning, provenance, citation integrity, and future litigation-workflow support.

---

## 5. How cases are handled

### 5.1 Manual upload

Endpoint: `POST /api/v1/cases/upload`

Code: `backend/app/api/v1/endpoints/cases.py`

Flow:

1. Require staff role.
2. Validate extension: PDF or DOCX.
3. Read file and enforce 20 MB limit.
4. Compute SHA-256.
5. Query `cases.file_hash` for duplicates.
6. Write file to configured storage using a generated canonical filename.
7. Parse act/section/keyword tags.
8. Generate a 384-dimensional embedding.
9. Insert `cases` row with `status = pending_approval`.
10. Insert `document_versions` version 1.
11. Insert `approval_queue` row with `status = pending`.
12. Write an `UPLOAD` audit event.

Strengths:

- Duplicate hash check exists.
- Initial document version is recorded.
- Manual upload enters the approval queue.
- File is not published immediately.

Weaknesses:

- Duplicate check is not protected by a unique constraint, so concurrent uploads can race.
- File write, case insert, version/queue insert, and audit insert are separate commits.
- Failure after file write or case insert can leave partial state.
- DOCX is accepted, but the automated extraction path is PDF-only.

### 5.2 Automated PDF upload

Endpoint: `POST /api/v1/cases/upload-auto`

Flow:

1. Require staff role.
2. Accept PDF only.
3. Hash and duplicate-check.
4. Write temporary UUID-named file.
5. Run extraction passes.
6. Generate embedding.
7. Insert `cases` row with `status = pending_review` and `auto_extracted = true`.
8. Rename file to canonical judicial filename.
9. Insert `document_versions` version 1.
10. Write `AUTO_UPLOAD_DOCUMENT` audit event.

Critical gap:

- **No `approval_queue` row is created.**
- The admin queue endpoint reads only pending `approval_queue` rows.
- Therefore auto-ingested `pending_review` cases can be invisible to the normal admin queue unless another path manually opens them.

Additional issue:

- Extraction confidence scores are returned to the client but not stored as structured case fields in the current model.

### 5.3 Staff review and metadata editing

Endpoints:

- `PATCH /api/v1/cases/{case_id}`
- `POST /api/v1/cases/{case_id}/re-extract`

Behavior:

- Staff can update selected metadata fields.
- Substantive field changes regenerate embeddings.
- Re-extraction overwrites extracted fields from the stored PDF.
- Changes are audit logged.

Gaps:

- Metadata edits do not create a new metadata version.
- Edits after approval do not automatically invalidate or regenerate the composite judicial seal.
- The review UI sends `cnr`, but the backend patch schema does not accept `cnr` or map it to `cnr_number`; the value is ignored.
- The review UI sends the same combined tag list into both `act_tags` and `section_tags`.

### 5.4 Approval, rejection, and publication

Endpoint: `POST /api/v1/admin/approve/{case_id}`

Behavior:

1. Load case.
2. Set `case.status` from request.
3. Set approver and approval timestamp.
4. Update a pending approval-queue row if one exists.
5. Commit.
6. If status is `published`, compute a composite seal:

```text
H_doc  = SHA-256(document bytes)
H_meta = SHA-256(case_no | court | judge | disposition | year)
H_text = SHA-256(full_text)

Phi_case = SHA-256(H_doc | H_meta | H_text | approved_at_iso)
```

7. Store `Phi_case` in `cases.redacted_file_hash`.
8. Commit again.
9. Write approval/rejection audit event.

Problems:

- The endpoint accepts any status allowed by `CaseStatusUpdate`, including `pending_review`, `pending_approval`, and `quarantined`, but logs every non-published decision as `REJECT`.
- There is no explicit state-machine guard.
- A quarantined case can be moved back to published without re-verifying the file.
- Approval does not check that the physical file exists or matches `file_hash`.
- The composite seal is stored in a field named `redacted_file_hash`, even though it is not a redacted-document hash.
- No redacted file path is populated in the supplied SQLite data.
- The shared frontend helper `LG.api.admin.approve()` sends `{ notes }`, while the backend requires `{ status, review_note }`. Pydantic validation confirms `status` is missing. Some pages bypass the helper and send the correct payload.

### 5.5 Search and retrieval

Endpoint: `POST /api/v1/search/`

Behavior:

- Empty/short query: browse published cases with SQL filters and pagination.
- Normal query:
  1. Parse Boolean/field syntax.
  2. Enrich query using local LLM/NER fallback.
  3. Generate query embedding.
  4. Load published candidate cases.
  5. Score vector, lexical, and statutory channels in Python.
  6. Apply reciprocal rank fusion.
  7. Sort and paginate in Python.
  8. Return snippets and metadata.

Database implications:

- This is not PostgreSQL full-text search plus pgvector ANN search.
- The supplied PostgreSQL dumps store `embedding` as JSON, not `vector`.
- The search code defers `Case.full_text`, then accesses `c.full_text` during scoring, which can trigger per-case lazy loads.
- Ranking and pagination happen after loading candidates, so cost grows with the published corpus.
- Only 132 of 607 SQLite cases have non-null embeddings; 4 of those are all-zero vectors.
- Only 308 of 607 SQLite cases have non-empty full text.

### 5.6 Document viewing, download, and verification

There are multiple document paths with different guarantees.

| Path | Checks file hash? | Publication check? | Notes |
|---|---:|---:|---|
| `GET /cases/{id}/view` | Yes | Yes, but staff list is inconsistent | Quarantines on mismatch |
| `GET /cases/{id}/verify-integrity` | Yes | No explicit publication check | Returns expected/computed hash |
| `GET /cases/{id}/download` or `/pdf` | **No** | Yes | Sends `X-Lexguard-Verified: true` without hashing |
| `GET /verification/documents/{id}/stream` | Yes | Yes | Quarantines on mismatch; supports redacted path if present |
| `GET /verification/lookup/{hash}` | **No file re-hash** | Published only | Matches stored hash or composite seal |

The verified streaming endpoint is the strongest path. The older download endpoint undermines the integrity claim because it returns a verified header without checking current bytes.

The public hash lookup also returns `VERIFIED_OFFICIAL_RECORD` when a stored hash matches, but it does not:

- Re-hash the physical file.
- Recompute the composite seal from current metadata/text.
- Verify the full audit chain.
- Distinguish cryptographic registry match from official-source provenance.

### 5.7 Cause list handling

The cause-list page does not read a hearings or cause-list table. It fetches published cases and synthesizes:

- Court hall.
- Hearing stage.
- Status such as “In Session”, “Next in Roster”, “Passed Over”, or “Pronounced”.
- Fallback CNR values.

Therefore the current cause list is a UI demonstration over repository cases, not a persisted or authoritative daily court board.

---

## 6. Supplied database artifacts

### 6.1 Row counts

| Artifact | Cases | Audit logs | Document versions | Approval queue | Bookmarks | Draft sessions | Users | Statute sections |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `backend/lexguard.db` | 607 | 1,661 | 5 | 5 | 0 | 0 | 29 | 20 |
| `database/database_dump.sql` | 607 | 1,593 | 153 | 2 | 0 | 4 | 29 | 20 |
| `database/lexguard_dump.sql` | 145 | 1,179 | 18 | 0 | 0 | 4 | 26 | 20 |

The README describes restoration of “208 Cases” and instructs restoring `database/lexguard_dump.sql`, but that dump contains 145 cases. The newer `database_dump.sql` and SQLite file contain 607 cases.

### 6.2 SQLite case profile

From `backend/lexguard.db`:

| Metric | Value |
|---|---:|
| Total cases | 607 |
| Published | 606 |
| Pending review | 1 |
| Auto-extracted | 536 |
| Cases with non-empty full text | 308 |
| Cases with non-null embedding | 132 |
| All-zero embeddings | 4 |
| Cases with source URL | 410 |
| Source state `verified` | 410 |
| Source state `verified_authentic` | 30 |
| Source state `unverified` | 167 |
| Cases with composite seal in `redacted_file_hash` | 84 |
| Cases with redacted file path | 0 |
| Duplicate file-hash groups | 9 |
| Extra rows caused by duplicate file hashes | 9 |
| Cases with missing/invalid uploader reference | 327 |
| Cases with missing/invalid approver reference | 327 |
| Published cases missing approval metadata | 32 |
| Resolvable PDFs whose bytes match stored hash | 605 |
| Case PDFs not resolvable from repository storage | 2 |

SQLite `PRAGMA quick_check` returned `ok`, so the file is structurally readable. That does not mean the relational data is consistent.

### 6.3 Schema drift

| Schema item | ORM model | SQLite file | Newer PG dump | Older PG dump |
|---|---:|---:|---:|---:|
| `bookmarks.binder_name` | Yes | **Missing** | Yes | **Missing** |
| `cases.comparison_profile` | No | Yes | Yes | No |
| `approval_queue.target_user_id` | No | No | Yes | No |
| `users.reset_token_hash` / expiry | No | No | Yes | No |
| Case foreign keys | Yes | **Missing** | Yes | Yes |
| Audit foreign keys | Yes | **Missing** | Yes | Yes |
| Most case/audit indexes | Yes | **Missing** | Yes | Yes |
| Embedding column | `Vector(384)` if pgvector import succeeds, else JSON | JSON | JSON | JSON |

Confirmed runtime failure:

```text
Bookmark query against supplied SQLite:
OperationalError: no such column: bookmarks.binder_name
```

Confirmed query-plan behavior in SQLite:

- Published-case listing: full table scan plus temporary B-tree sort.
- File-hash lookup: full table scan.
- Title substring search: full table scan.
- Audit timestamp ordering: full table scan plus temporary B-tree sort.

### 6.4 PostgreSQL dump integrity

The newer dump, `database/database_dump.sql`, contains:

- 327 `cases.uploaded_by_id` values referencing a placeholder user ID that is absent from `users`.
- 327 `cases.approved_by_id` values referencing the same missing placeholder user.

Because the dump adds foreign keys after loading data, a clean restore with constraints enforced will fail on those references. If errors are ignored, the restore can complete partially without the intended constraints.

The older dump, `database/lexguard_dump.sql`, did not show those orphaned user references in this analysis, but it is a smaller and older schema snapshot.

---

## 7. Ranked findings

### P1 — Choose and enforce one canonical database path

**Evidence:** `backend/app/core/database.py`, `backend/app/core/config.py`, supplied SQLite/dumps.

**Risk:** The application can appear healthy while using a different database than operators expect. Development, evaluation, and production can diverge silently.

**Recommendation:**

- Make PostgreSQL mandatory outside explicit local development.
- Replace silent fallback with a loud startup failure or an explicit `ALLOW_SQLITE_FALLBACK=true` development flag.
- Use an absolute SQLite path when fallback is intentionally enabled.
- Report the active dialect/database identity in health/readiness output without exposing credentials.
- Stop logging full connection URLs.

### P1 — Repair schema drift and introduce real migrations

**Evidence:** ORM inspection, SQLite schema, PostgreSQL dump schemas, ad hoc migration scripts.

**Risk:** Existing deployments do not converge to the ORM schema. `create_all()` will not add missing columns, indexes, or constraints to existing tables.

**Recommendation:**

- Adopt Alembic or another versioned migration tool.
- Create a baseline migration matching the chosen canonical schema.
- Add missing SQLite columns/indexes if SQLite remains supported.
- Remove or formally model extra columns such as `comparison_profile`.
- Decide whether embeddings are JSON or pgvector; if pgvector, create the extension and migrate the column intentionally.
- Add CI checks that compare ORM metadata against a freshly migrated database.

### P1 — Repair referential integrity and duplicate controls

**Evidence:** SQLite orphan counts, PostgreSQL dump orphan counts, duplicate hash groups.

**Risk:** Cases can reference nonexistent users; versions/queue rows can become orphaned; duplicate documents can enter the repository.

**Recommendation:**

- Repair or quarantine the 327 invalid uploader/approver references before restoring the newer PostgreSQL dump.
- Add/restore foreign keys on cases, versions, queue, bookmarks, drafts, and audit logs.
- Enable SQLite foreign-key enforcement on every connection if SQLite remains supported.
- Add a unique constraint on `cases.file_hash` if one document hash must map to one case.
- Add a unique constraint on `(case_id, version_no)`.
- Add a controlled uniqueness rule for pending approval entries per case.
- Decide whether CNR and official citation should be unique, nullable-unique, or non-unique with explicit duplicate handling.

### P1 — Rebuild and harden the audit ledger

**Evidence:** Application audit verifier, audit service, batch ingestion audit writer.

Measured against the supplied SQLite database using the current verifier:

- First chain-link failure: chronological index 31.
- Full replay: 215 chain-link breaks.
- Full replay: 505 current-hash mismatches.
- Multiple genesis resets and forked previous-hash groups exist.

A concrete code bug exists in `backend/batch_ingest_1000.py`: it hashes one `details` string but stores a different `details` string in the audit row.

**Risk:** The audit ledger cannot currently support a claim of verified immutability. Hash mismatches do not by themselves prove malicious tampering; they can also come from legacy serialization, import changes, or writer bugs.

**Recommendation:**

- Define a canonical, versioned audit payload serialization.
- Hash exactly the fields that are stored.
- Include `user_agent` if it is part of the integrity claim.
- Use a database-backed sequence or advisory lock to serialize audit appends across workers.
- Store UTC timestamps consistently and normalize before hashing.
- Rebuild a new audit chain from a trusted checkpoint; do not silently rewrite history without an explicit migration record.
- Make audit verification part of CI and operational monitoring.
- Stop tests from deleting audit rows in a shared database.

### P1 — Fix the approval workflow and publication boundary

**Evidence:** upload/auto-upload endpoints, admin queue/approval endpoints, frontend API helper.

**Risk:** Cases can bypass the visible review queue, be published without file verification, or fail to approve from parts of the UI.

**Recommendation:**

- Create an approval-queue entry for auto-ingested cases, or make the queue read directly from case workflow state.
- Include `pending_review` in admin analytics and queue views.
- Fix `LG.api.admin.approve()` to send `{ status: "published", review_note }`.
- Add explicit allowed transitions, for example:

```text
pending_review -> pending_approval -> published
pending_review -> rejected
pending_approval -> rejected
published -> quarantined
quarantined -> pending_review
```

- Verify file existence and hash before publication.
- Recompute or invalidate the composite seal after post-approval metadata/text changes.
- Store the composite seal in a dedicated field such as `judicial_seal`, not `redacted_file_hash`.
- Centralize publication checks across view, download, stream, citations, external references, bookmarks, and draft comparison.

### P1 — Make integrity and provenance claims match actual checks

**Evidence:** download endpoint, hash lookup endpoint, extraction source logic, ingestion scripts.

**Risk:** Users may interpret “verified” as official-source authentication or current-byte integrity when the system only matched a stored value or detected a URL.

Measured seal result:

- 84 SQLite cases have a stored composite seal.
- Only 2 reproduce with the current formula and currently stored metadata/text/approval timestamp.
- 247 published cases have `updated_at` later than `approved_at`.

This does not prove tampering; timestamp serialization and post-approval edits can also break reproduction. It does show that the seal is not currently a reliable, independently verified invariant.

**Recommendation:**

- Remove `X-Lexguard-Verified: true` from paths that do not verify bytes, or perform verification before sending it.
- Prefer the verified streaming endpoint for all document delivery.
- On hash lookup, distinguish:
  - Registry hash match.
  - Current file integrity verified.
  - Composite seal verified.
  - Official source provenance verified.
- Store provenance evidence: source institution, retrieval URL, retrieval time, downloader identity, expected hash, and verification method.
- Do not mark a case officially verified solely because a government URL appears in extracted text.
- Treat generated landmark summary PDFs as demo/reference material unless clearly labeled as non-original.

### P2 — Improve search storage and execution

**Evidence:** search endpoint, embedding service, supplied JSON embeddings, SQLite query plans.

**Risk:** Search quality and latency degrade as the corpus grows. Many cases lack embeddings or full text.

**Recommendation:**

- Backfill embeddings and full text for all published cases.
- Store embedding model name/version and generation time.
- Use PostgreSQL full-text search for lexical retrieval.
- Use pgvector with an appropriate index if semantic ANN search is required.
- Push candidate filtering, ranking, and pagination into the database where practical.
- Avoid deferring `full_text` and then immediately accessing it for every candidate.
- Add regression tests for Boolean semantics, mandatory phrases, field filters, and citation lookup.

### P2 — Normalize legal relationships if the project becomes a case-management system

**Evidence:** JSON tags/citations, static statute counts, synthetic cause list.

**Risk:** Citation counts, statute links, party roles, hearings, and orders cannot be reliably constrained or queried.

**Recommendation:** add focused tables only when needed:

- `case_parties`
- `case_statutes`
- `case_citations`
- `case_documents`
- `case_status_history`
- `hearings`
- `orders`
- `ingestion_jobs`

Keep `cases` as the identity/workflow anchor, but move multi-valued and event-like data out of JSON where integrity matters.

### P2 — Make writes transactional and recoverable

**Evidence:** multi-commit upload/approval/audit flows.

**Risk:** Partial uploads, missing versions, missing queue entries, or case updates without audit events.

**Recommendation:**

- Use one database transaction for case + version + queue + audit where possible.
- Treat file storage as a staged operation: write temporary file, commit DB state, finalize/rename, clean up on failure.
- Add an outbox or repair job for audit events if external file operations prevent a single transaction.
- Add idempotency keys for upload and approval operations.

### P2 — Align frontend/backend contracts and test them

**Evidence:** approval helper, review CNR field, comparison helper, draft helper.

**Risk:** UI actions can fail or silently discard data even when the database is healthy.

**Recommendation:**

- Generate or contract-test API payloads from OpenAPI/Pydantic schemas.
- Add integration tests for manual upload, auto upload, review save, approval, rejection, bookmark creation, and verified download.
- Run tests against isolated migrated databases, not the shipped SQLite file.

---

## 8. What the database supports well today

Despite the issues, several foundations are useful:

- Clear central `cases` entity with UUID identifiers.
- Separation of users, cases, versions, approval queue, bookmarks, drafts, and audit logs.
- SHA-256 document hashing at ingestion.
- A verified streaming path that can quarantine mismatched files.
- Publication-state filtering in the main search path.
- Structured legal metadata fields beyond simple title/summary.
- JSON tags and embeddings that allow rapid prototyping.
- Audit intent and a verification endpoint, even though the current data/implementation need repair.
- A statute table and API surface that can evolve into a proper case-statute relationship.

---

## 9. Recommended remediation order

### Phase 1: Stabilize identity and schema

1. Declare PostgreSQL as the canonical runtime database.
2. Disable silent production fallback.
3. Choose one canonical dump/schema baseline.
4. Add Alembic migrations.
5. Repair invalid user references.
6. Add missing columns, indexes, foreign keys, and uniqueness constraints.
7. Update README counts and restore instructions.

### Phase 2: Repair trust-critical workflows

1. Fix approval payload and queue visibility.
2. Enforce workflow transitions.
3. Verify file hash before publication and download.
4. Separate composite seal from redacted-file hash.
5. Rebuild audit chain with canonical serialization.
6. Add provenance evidence fields and stop heuristic “official verified” labeling.

### Phase 3: Improve data quality and search

1. Backfill full text and embeddings.
2. Resolve duplicate document hashes.
3. Normalize citations and statute links.
4. Add PostgreSQL FTS/pgvector or keep application-side search with explicit scale limits.
5. Add data-quality dashboards and restore drills.

### Phase 4: Expand only if live case management is required

Add hearings, orders, party roles, status history, and cause-list ingestion as real persisted entities. Until then, label the cause list as demo/synthetic and avoid implying live court-board authority.

---

## 10. Evidence index

| Area | Primary files |
|---|---|
| DB configuration/fallback | `backend/app/core/config.py`, `backend/app/core/database.py` |
| Startup schema creation/seeding | `backend/app/main.py` |
| Case model | `backend/app/models/case.py` |
| Supporting models | `backend/app/models/user.py`, `document_version.py`, `approval_queue.py`, `audit_log.py`, `bookmark.py`, `draft_session.py`, `statute.py` |
| Upload/review/download | `backend/app/api/v1/endpoints/cases.py` |
| Approval/audit admin | `backend/app/api/v1/endpoints/admin.py` |
| Hash lookup/streaming | `backend/app/api/v1/endpoints/verification.py` |
| Search | `backend/app/api/v1/endpoints/search.py`, `backend/app/services/embedding_service.py` |
| Audit hashing | `backend/app/services/audit_service.py`, `backend/app/services/crypto_service.py` |
| Batch ingestion audit bug | `backend/batch_ingest_1000.py` |
| Source/provenance heuristics | `backend/app/services/extraction_service.py`, `backend/download_and_ingest_official.py` |
| Frontend contracts | `frontend/js/lexguard-api.js`, `frontend/js/pages/admin.js`, `frontend/js/pages/case-review.js`, `frontend/js/pages/case-upload.js` |
| Synthetic cause list | `frontend/js/pages/cause-list.js` |
| Supplied databases | `backend/lexguard.db`, `database/database_dump.sql`, `database/lexguard_dump.sql` |
| Ad hoc migrations | `backend/migrate_columns.py`, `backend/migrate_source_fields.py`, `backend/migrations/001_add_structured_fields.py` |

---

## 11. Final assessment

The database design is suitable for a **prototype legal judgment repository**, but the current implementation should not yet be described as a fully reliable, production-grade case-handling database. The highest-value next step is not adding more AI features; it is making the database identity, schema, approval workflow, document integrity, and audit ledger consistent and testable.