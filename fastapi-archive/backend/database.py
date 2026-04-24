"""
database.py — Firebase Admin SDK initialisation and Firestore helpers.
Adapted from the Guesthouse Booking app for TutorTrack AI.

Collection mapping:
  bookings          → student_records
  config/admin      → config/admin  (unchanged — same auth pattern)
"""
import logging
from functools import lru_cache
from typing import Optional

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1 import AsyncClient

from config import get_settings

logger = logging.getLogger(__name__)

# ── Module-level singletons ────────────────────────────────────────────────
_firebase_app: Optional[firebase_admin.App] = None
_db: Optional[AsyncClient] = None


def init_firebase() -> None:
    """Initialise Firebase Admin SDK. Called once at app startup."""
    global _firebase_app, _db

    if _firebase_app is not None:
        return  # Already initialised

    settings = get_settings()
    try:
        from google.oauth2 import service_account
        cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
        _firebase_app = firebase_admin.initialize_app(cred, {
            "projectId": settings.FIREBASE_PROJECT_ID
        })
        google_creds = service_account.Credentials.from_service_account_file(
            settings.FIREBASE_CREDENTIALS_PATH,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        _db = firestore.AsyncClient(
            project=settings.FIREBASE_PROJECT_ID,
            credentials=google_creds
        )
        logger.info("✅ Firebase Admin SDK initialised — project: %s", settings.FIREBASE_PROJECT_ID)
    except Exception as exc:
        logger.error("❌ Firebase initialisation failed: %s", exc)
        raise RuntimeError(f"Firebase init failed: {exc}") from exc


def get_db() -> AsyncClient:
    """Return the Firestore async client. Raises if not initialised."""
    if _db is None:
        raise RuntimeError("Firestore not initialised. Call init_firebase() first.")
    return _db


# ══════════════════════════════════════════════════════════════════
#  COLLECTION CONSTANTS
# ══════════════════════════════════════════════════════════════════

RECORDS_COLLECTION = "student_records"   # was: "bookings"
CONFIG_COLLECTION  = "config"
ADMIN_CONFIG_DOC   = "admin"


# ══════════════════════════════════════════════════════════════════
#  STUDENT RECORD HELPERS  (analogous to booking helpers)
# ══════════════════════════════════════════════════════════════════

async def get_all_records() -> list[dict]:
    """Fetch every student record document from Firestore."""
    db = get_db()
    col = db.collection(RECORDS_COLLECTION)
    snap = await col.get()
    return [{"fbDocId": doc.id, **doc.to_dict()} for doc in snap]


async def get_record_by_doc_id(doc_id: str) -> Optional[dict]:
    """Fetch a single student record by Firestore document ID."""
    db = get_db()
    ref = db.collection(RECORDS_COLLECTION).document(doc_id)
    snap = await ref.get()
    if not snap.exists:
        return None
    return {"fbDocId": snap.id, **snap.to_dict()}


async def create_record(record_data: dict) -> str:
    """
    Save a new student record document.
    Returns the Firestore-generated document ID.
    """
    db = get_db()
    _, doc_ref = await db.collection(RECORDS_COLLECTION).add(record_data)
    return doc_ref.id


async def update_record_status(
    doc_id: str,
    status: str,
    notes: Optional[str] = None,
) -> None:
    """Patch only the status-related fields on an existing student record."""
    db = get_db()
    ref = db.collection(RECORDS_COLLECTION).document(doc_id)
    payload: dict = {"status": status}
    if notes is not None:
        payload["notes"] = notes
    await ref.update(payload)


async def delete_record(doc_id: str) -> None:
    """Hard-delete a student record document."""
    db = get_db()
    ref = db.collection(RECORDS_COLLECTION).document(doc_id)
    await ref.delete()


# ── Admin config helpers (password stored in Firestore) ───────────────────

async def get_admin_password() -> Optional[str]:
    """Read the admin password from Firestore config doc. Returns None if unset."""
    try:
        db = get_db()
        ref = db.collection(CONFIG_COLLECTION).document(ADMIN_CONFIG_DOC)
        snap = await ref.get()
        if snap.exists and snap.to_dict().get("password"):
            return snap.to_dict()["password"]
        return None
    except Exception as exc:
        logger.warning("Could not read admin password from Firestore: %s", exc)
        return None


async def save_admin_password(new_password: str) -> bool:
    """Persist a new admin password to Firestore."""
    try:
        db = get_db()
        ref = db.collection(CONFIG_COLLECTION).document(ADMIN_CONFIG_DOC)
        await ref.set({"password": new_password}, merge=True)
        return True
    except Exception as exc:
        logger.error("Failed to save admin password: %s", exc)
        return False
