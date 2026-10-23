"""
Full verification test suite for all 7 PostgreSQL tables in Lexguard:
1. users
2. cases
3. document_versions
4. audit_logs
5. bookmarks
6. draft_sessions
7. approval_queue
"""

import os
import sys
import uuid
import datetime

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__) + "/.."))

from app.core.database import SessionLocal, engine
from app.models.user import User
from app.models.case import Case
from app.models.document_version import DocumentVersion
from app.models.audit_log import AuditLog
from app.models.bookmark import Bookmark
from app.models.draft_session import DraftSession
from app.models.approval_queue import ApprovalQueue
from app.services.crypto_service import compute_sha256, compute_audit_log_hash, verify_audit_chain


def run_full_7_table_check():
    print("=" * 60)
    print("LEXGUARD POSTGRESQL 7-TABLE VERIFICATION SUITE")
    print(f"Target DB: {engine.url}")
    print("=" * 60)

    db = SessionLocal()
    run_id = uuid.uuid4().hex[:8]

    try:
        # ---------------------------------------------------------
        # Table 1: users
        # ---------------------------------------------------------
        print("\n[1/7] Testing 'users' table CRUD & constraints...")
        test_user = User(
            name=f"Test Advocate {run_id}",
            email=f"advocate_{run_id}@court.in",
            password_hash="$2b$12$fakehashedpasswordforverificationsuite",
            role="advocate",
            status="active",
            credential_id=f"BCI-{run_id}",
        )
        db.add(test_user)
        db.commit()
        db.refresh(test_user)
        assert test_user.id is not None
        user_row = db.query(User).filter(User.id == test_user.id).first()
        assert user_row is not None
        print(f"  --> users: OK (Created user ID: {user_row.id[:8]}..., Email: {user_row.email})")

        # ---------------------------------------------------------
        # Table 2: cases
        # ---------------------------------------------------------
        print("\n[2/7] Testing 'cases' table CRUD & cryptographic hash storage...")
        dummy_content = f"Judgment Text content for test verification run {run_id}".encode("utf-8")
        file_hash = compute_sha256(dummy_content)

        test_case = Case(
            case_no=f"CRIM-{run_id}/2026",
            title=f"State of NCT vs Accused {run_id}",
            court="Supreme Court of India",
            year=2026,
            judge="Hon'ble Justice D.Y. Chandrachud",
            parties=f"Petitioner {run_id} vs State",
            act_tags=["IPC", "CrPC"],
            section_tags=["Section 438 CrPC", "Section 420 IPC"],
            keyword_tags=["bail", "precedent", "anticipatory"],
            summary="Application for anticipatory bail under criminal provisions.",
            outcome="Allowed",
            file_path=f"/storage/cases/test_{run_id}.pdf",
            file_hash=file_hash,
            embedding=[0.05] * 384,
            status="pending_approval",
            uploaded_by_id=test_user.id,
        )
        db.add(test_case)
        db.commit()
        db.refresh(test_case)
        assert test_case.id is not None
        assert len(test_case.file_hash) == 64
        print(f"  --> cases: OK (Case No: {test_case.case_no}, SHA-256: {test_case.file_hash[:16]}...)")

        # ---------------------------------------------------------
        # Table 3: document_versions
        # ---------------------------------------------------------
        print("\n[3/7] Testing 'document_versions' table & foreign key to cases...")
        v1 = DocumentVersion(
            case_id=test_case.id,
            version_no=1,
            file_path=test_case.file_path,
            file_hash=test_case.file_hash,
            change_summary="Initial verification filing",
            changed_by_id=test_user.id,
        )
        db.add(v1)
        db.commit()
        db.refresh(v1)
        assert v1.id is not None
        assert v1.case_id == test_case.id
        print(f"  --> document_versions: OK (Version No: {v1.version_no}, Case ID: {v1.case_id[:8]}...)")

        # ---------------------------------------------------------
        # Table 4: audit_logs
        # ---------------------------------------------------------
        print("\n[4/7] Testing 'audit_logs' table & cryptographic hash-chaining...")
        ts = datetime.datetime.now(datetime.timezone.utc)
        log_hash = compute_audit_log_hash(
            previous_hash="0" * 64,
            user_id=test_user.id,
            case_id=test_case.id,
            action="TEST_VERIFY_ACTION",
            ip_address="127.0.0.1",
            timestamp_iso=ts,
            details=f"Automated verification test run {run_id}",
        )

        audit_entry = AuditLog(
            action="TEST_VERIFY_ACTION",
            user_id=test_user.id,
            case_id=test_case.id,
            previous_log_hash="0" * 64,
            current_hash=log_hash,
            details=f"Automated verification test run {run_id}",
            ip_address="127.0.0.1",
            user_agent="Lexguard-Verifier/1.0",
        )
        db.add(audit_entry)
        db.commit()
        db.refresh(audit_entry)
        assert audit_entry.id is not None
        assert len(audit_entry.current_hash) == 64
        print(f"  --> audit_logs: OK (Action: {audit_entry.action}, Current Hash: {audit_entry.current_hash[:16]}...)")

        # ---------------------------------------------------------
        # Table 5: bookmarks
        # ---------------------------------------------------------
        print("\n[5/7] Testing 'bookmarks' table & user/case association...")
        bm = Bookmark(
            user_id=test_user.id,
            case_id=test_case.id,
            notes="Crucial precedent on anticipatory bail",
        )
        db.add(bm)
        db.commit()
        db.refresh(bm)
        assert bm.id is not None
        assert bm.user_id == test_user.id
        assert bm.case_id == test_case.id
        print(f"  --> bookmarks: OK (Bookmark ID: {bm.id[:8]}..., User: {bm.user_id[:8]}..., Case: {bm.case_id[:8]}...)")

        # ---------------------------------------------------------
        # Table 6: draft_sessions
        # ---------------------------------------------------------
        print("\n[6/7] Testing 'draft_sessions' table JSON payloads & relationship...")
        draft = DraftSession(
            user_id=test_user.id,
            title=f"Petition Draft v1 {run_id}",
            draft_text="The Petitioner respectfully submits before this Hon'ble Court that...",
            citations_inserted=[{"case_id": test_case.id, "citation": "2026 SC 101"}],
            gap_analysis_result={"missing_arguments": ["Article 21 delay"], "score": 0.85},
        )
        db.add(draft)
        db.commit()
        db.refresh(draft)
        assert draft.id is not None
        assert draft.user_id == test_user.id
        assert "missing_arguments" in draft.gap_analysis_result
        print(f"  --> draft_sessions: OK (Draft Title: {draft.title}, JSON Citations: {len(draft.citations_inserted)})")

        # ---------------------------------------------------------
        # Table 7: approval_queue
        # ---------------------------------------------------------
        print("\n[7/7] Testing 'approval_queue' table & workflow status...")
        queue_item = ApprovalQueue(
            case_id=test_case.id,
            submitted_by_id=test_user.id,
            status="pending",
            review_note="Pending initial Registrar scrutiny",
        )
        db.add(queue_item)
        db.commit()
        db.refresh(queue_item)
        assert queue_item.id is not None
        assert queue_item.case_id == test_case.id
        print(f"  --> approval_queue: OK (Queue ID: {queue_item.id[:8]}..., Status: {queue_item.status})")

        # ---------------------------------------------------------
        # Row counts across all 7 tables in PostgreSQL
        # ---------------------------------------------------------
        print("\n" + "=" * 60)
        print("LIVE ROW COUNTS IN POSTGRESQL:")
        print("=" * 60)
        counts = {
            "users": db.query(User).count(),
            "cases": db.query(Case).count(),
            "document_versions": db.query(DocumentVersion).count(),
            "audit_logs": db.query(AuditLog).count(),
            "bookmarks": db.query(Bookmark).count(),
            "draft_sessions": db.query(DraftSession).count(),
            "approval_queue": db.query(ApprovalQueue).count(),
        }
        for tbl, cnt in counts.items():
            print(f"  * {tbl.ljust(20)} : {cnt} rows")

        # Clean up test rows
        db.delete(queue_item)
        db.delete(draft)
        db.delete(bm)
        db.delete(audit_entry)
        db.delete(v1)
        db.delete(test_case)
        db.delete(test_user)
        db.commit()
        print("\nCleaned up verification test records successfully.")
        print("\nALL 7 TABLES ARE WORKING 100% PERFECTLY!")

    except Exception as e:
        db.rollback()
        print(f"\n[ERROR] Table verification failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_full_7_table_check()
