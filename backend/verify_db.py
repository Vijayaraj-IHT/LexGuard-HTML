import os
import sys
from dotenv import load_dotenv

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from app.core.config import settings
from app.core.database import engine, Base, SessionLocal
from app.models import User, Case, DocumentVersion, AuditLog, Bookmark, DraftSession, ApprovalQueue
from app.core.security import get_password_hash
from sqlalchemy import text


def verify_database():
    print(f"Connecting to database: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else settings.DATABASE_URL}")
    print("Executing Base.metadata.create_all(bind=engine)...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully!")

    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"
        ))
        tables = [row[0] for row in result.fetchall()]
        print("\n=== Verified Public Tables in PostgreSQL ===")
        for t in tables:
            print(f"  - {t}")

    # Seed users across all 4 roles
    db = SessionLocal()
    try:
        seed_users = [
            ("staff@court.gov.in", "staff123", "Chief Registrar", "staff", "COURT-REG-001"),
            ("advocate@bar.in", "advocate123", "Senior Advocate", "advocate", "BAR-DL-2024-9912"),
            ("scholar@law.edu", "scholar123", "Legal Scholar", "scholar", "NLSIU-FAC-4012"),
            ("public@citizen.in", "public123", "Citizen User", "public", None),
            ("staff@lexguard.gov.in", "Admin@Lexguard2026", "Chief Registrar", "senior_staff", "COURT-REG-001"),
        ]
        print("\n=== Seeding Verified User Roles ===")
        for email, password, name, role, cred_id in seed_users:
            existing = db.query(User).filter(User.email == email).first()
            if not existing:
                u = User(
                    name=name,
                    email=email,
                    password_hash=get_password_hash(password),
                    role=role,
                    status="active",
                    credential_id=cred_id,
                )
                db.add(u)
                print(f"  [+] Created user: {email} (role: {role})")
            else:
                existing.status = "active"
                print(f"  [=] User exists: {email} (role: {existing.role}, status: active)")
        db.commit()

        user_count = db.query(User).count()
        print(f"\nTotal users in database: {user_count}")
    finally:
        db.close()


if __name__ == "__main__":
    verify_database()
