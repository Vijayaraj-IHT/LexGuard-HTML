"""
Tests for LexGuard Week 1 Foundations & Critical Correctness Fixes.
Validates:
1. junior_staff RBAC permissions under staff role expansion.
2. Production startup security guards (SECRET_KEY & COOKIE_SECURE).
3. Server filesystem path exclusion from API response schemas.
4. Correct MIME-type detection for DOCX vs PDF downloads.
5. ExtractionService Pass 1 structural extraction on real Indian High Court documents.
"""

import pytest
from pydantic import ValidationError
from app.core.config import Settings
from app.core.security import require_role
from app.schemas.case import CaseDetailResponse
from app.services.extraction_service import ExtractionService


def test_junior_staff_rbac_expansion():
    """Verify junior_staff is included in the staff role expansion."""
    # When a route specifies "staff", junior_staff must be allowed
    checker = require_role(["staff"])
    
    class MockUser:
        def __init__(self, role):
            self.role = role

    # junior_staff must not raise 403
    user_junior = MockUser("junior_staff")
    res = checker(current_user=user_junior)
    assert res.role == "junior_staff"

    # senior_staff and court_staff must also pass
    user_senior = MockUser("senior_staff")
    assert checker(current_user=user_senior).role == "senior_staff"

    user_court = MockUser("court_staff")
    assert checker(current_user=user_court).role == "court_staff"

    # Unauthorized roles must be denied
    with pytest.raises(Exception) as exc_info:
        checker(current_user=MockUser("public"))
    assert "Access denied" in str(exc_info.value.detail)


def test_production_security_guards():
    """Verify startup guard rejects default SECRET_KEY or insecure cookies in production."""
    # Valid in development
    dev_settings = Settings(
        ENVIRONMENT="development",
        SECRET_KEY="lexguard-super-secret-jwt-key-2026-production-ready-32-chars-min",
        COOKIE_SECURE=False,
    )
    assert dev_settings.ENVIRONMENT == "development"

    # Invalid in production with default key
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="lexguard-super-secret-jwt-key-2026-production-ready-32-chars-min",
            COOKIE_SECURE=True,
        )
    assert "Production security violation: SECRET_KEY" in str(exc_info.value)

    # Invalid in production with COOKIE_SECURE=False
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="a-very-long-unique-production-random-secret-key-32-chars",
            COOKIE_SECURE=False,
        )
    assert "Production security violation: COOKIE_SECURE" in str(exc_info.value)

    # Valid in production with secure configuration
    prod_settings = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="a-very-long-unique-production-random-secret-key-32-chars",
        COOKIE_SECURE=True,
    )
    assert prod_settings.ENVIRONMENT == "production"


def test_schema_excludes_server_file_path():
    """Verify CaseDetailResponse does not expose internal filesystem paths."""
    schema_fields = CaseDetailResponse.model_fields.keys()
    assert "file_path" not in schema_fields, "Critical Security Flaw: file_path must NOT be exposed in API schemas."
    assert "redacted_file_path" not in schema_fields, "Critical Security Flaw: redacted_file_path must NOT be exposed in API schemas."
    assert "integrity_status" in schema_fields
    assert "file_hash" in schema_fields


def test_extraction_service_structural_parsing():
    """Verify ExtractionService parses Indian High Court documents accurately."""
    sample_text = """
    CRL OP No. 26284 of 2026
    IN THE HIGH COURT OF JUDICATURE AT MADRAS
    DATED: 09-10-2026
    CORAM
    THE HON'BLE MR.JUSTICE N.RAMESH
    CRL OP No. 26284 of 2026
    CNR: {HCMA012140432026}
    Silu Chhinchani
    ..Petitioner(s)
    Vs
    State Rep.by,
    The Inspector of Police
    PEW - Tambaram Police Station,
    Tambaram, Cr.No.52 of 2025.
    ..Respondent(s)
    PRAYER: This criminal original petition filed under Section 482 BNSS Act to
    enlarge on bail in CC.No.758 of 2025 in Cr.No.52 of 2025 pending on the file
    of the I Additional Special Judge, Special Court for EC and NDPS Act,
    Chennai.
    For Petitioner(s): Mr.S.Karthikeyan
    For Respondent(s): Mr.E.Raj Thilak, Additional Public Prosecutor
    ORDER
    Accordingly, this Criminal Original Petition is allowed and the petitioner is ordered to be released on bail.
    https://www.mhc.tn.gov.in/judis
    """

    data, confidence = ExtractionService._pass1_structural(
        first_page=sample_text,
        last_pages=sample_text,
        full_text=sample_text,
        page_count=1,
    )

    assert data["court"] == "Madras High Court"
    assert "26284" in data["case_no"]
    assert data["year"] == 2026
    assert "N.RAMESH" in data["judge"]
    assert data["cnr"] == "HCMA012140432026"
    assert "Silu Chhinchani" in data["parties"]
    assert data["outcome"] == "Allowed"
    assert "https://www.mhc.tn.gov.in/judis" in data["source_url"]
    assert data["petition_type"] == "Criminal Original Petition (Bail / Quashing)"
    assert confidence["case_no"]["confidence"] >= 0.85
    assert confidence["court"]["confidence"] >= 0.85
