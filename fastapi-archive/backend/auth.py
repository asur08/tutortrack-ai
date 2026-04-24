"""
auth.py — JWT token creation/verification and admin login logic.
Identical security model to the Guesthouse app:
  - Single admin account verified against Firestore.
  - bcrypt password hashing with sha-256 pre-hash to avoid 72-byte limit.
  - JWT tokens signed HS256, expiring after JWT_EXPIRE_HOURS.
"""
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
import passlib.handlers.bcrypt
from passlib.context import CryptContext

from config import get_settings
from database import get_admin_password, save_admin_password

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Monkey-patch: disable bcrypt 72-byte truncation error (Python 3.12) ────
class TruncatingBcrypt(passlib.handlers.bcrypt.bcrypt):
    name = "truncating_bcrypt"
    truncate_error = False

pwd_ctx = CryptContext(schemes=[TruncatingBcrypt, "bcrypt"], deprecated="auto")

# ── Bearer token extractor ─────────────────────────────────────────────────
bearer_scheme = HTTPBearer()


# ══════════════════════════════════════════════════════════════════
#  PASSWORD HELPERS
# ══════════════════════════════════════════════════════════════════

def _hash_for_bcrypt(plain: str) -> str:
    """Pre-hash to avoid bcrypt 72-byte limit."""
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def hash_password(plain: str) -> str:
    return pwd_ctx.hash(_hash_for_bcrypt(plain))


def verify_password(plain: str, hashed: str) -> bool:
    if hashed.startswith("$2"):
        return pwd_ctx.verify(_hash_for_bcrypt(plain), hashed)
    return plain == hashed   # legacy plain-text fallback


def is_plain_text(stored: str) -> bool:
    return not stored.startswith("$2")


# ══════════════════════════════════════════════════════════════════
#  JWT HELPERS
# ══════════════════════════════════════════════════════════════════

def create_access_token(uid: str) -> tuple[str, int]:
    """Returns (token_string, expires_in_seconds)."""
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    payload = {
        "sub": uid,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, settings.JWT_EXPIRE_HOURS * 3600


def decode_token(token: str) -> str:
    """Decode and validate a JWT. Returns the subject (admin uid) on success."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        uid: Optional[str] = payload.get("sub")
        if uid is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return uid
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired or invalid. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ── FastAPI dependency ─────────────────────────────────────────────────────

async def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> str:
    """Protect admin endpoints — returns admin uid."""
    return decode_token(credentials.credentials)


# ══════════════════════════════════════════════════════════════════
#  LOGIN LOGIC
# ══════════════════════════════════════════════════════════════════

async def authenticate_admin(uid: str, password: str) -> bool:
    if uid != settings.ADMIN_ID:
        return False

    stored = await get_admin_password()

    if stored is None:
        if password != settings.ADMIN_PASS_DEFAULT:
            return False
        hashed = hash_password(password)
        await save_admin_password(hashed)
        logger.info("Admin password migrated to bcrypt hash in Firestore.")
        return True

    if not verify_password(password, stored):
        return False

    if is_plain_text(stored):
        hashed = hash_password(password)
        await save_admin_password(hashed)
        logger.info("Legacy plain-text admin password migrated to bcrypt hash.")

    return True


async def change_admin_password(current: str, new: str) -> bool:
    if not await authenticate_admin(settings.ADMIN_ID, current):
        return False
    hashed = hash_password(new)
    return await save_admin_password(hashed)
