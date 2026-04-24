"""
config.py — All application settings loaded from environment variables.
Never hardcode credentials here; use the .env file (see .env.example).
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── App ────────────────────────────────────────────────────────────────
    APP_NAME: str = "TutorTrack AI"
    APP_ENV: str = "development"           # "development" | "production"
    FRONTEND_ORIGIN: str = "http://localhost:5500"   # your dev / deployed URL

    # ── Admin credentials (MUST be set in .env — no defaults) ──────────────
    ADMIN_ID: str
    ADMIN_PASS_DEFAULT: str

    # ── JWT ────────────────────────────────────────────────────────────────
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 8

    # ── Firebase ───────────────────────────────────────────────────────────
    FIREBASE_CREDENTIALS_PATH: str = "firebase-service-account.json"
    FIREBASE_PROJECT_ID: str = "tutortrack-ai"

    # ── TutorTrack config ──────────────────────────────────────────────────
    CLEANUP_DAYS: int = 90   # auto-archive records older than N days

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton — import and call this everywhere."""
    return Settings()
