from fastapi import APIRouter
from app.api.v1.endpoints import auth, cases, search, draft, admin, bookmarks, verification, comparison

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication & RBAC"])
api_router.include_router(auth.router, prefix="/users", tags=["User Profile Alias"])
api_router.include_router(cases.router, prefix="/cases", tags=["Case Repository & Cryptographic Verification"])
api_router.include_router(verification.router, prefix="/verification", tags=["Document Integrity & Hash Verification"])
api_router.include_router(comparison.router, prefix="/comparison", tags=["Precedent Case Comparison"])
api_router.include_router(search.router, prefix="/search", tags=["Legal Search & Precedent Matching"])
api_router.include_router(draft.router, prefix="/draft", tags=["AI Draft Assistant"])
api_router.include_router(admin.router, prefix="/admin", tags=["Court Staff Administration & Audit"])
api_router.include_router(bookmarks.router, prefix="/bookmarks", tags=["Bookmarks"])
