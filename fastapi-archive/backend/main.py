"""
main.py — TutorTrack AI FastAPI application entry point.
Adapted from the Guesthouse Booking app.

Run in development:
    uvicorn main:app --reload --port 8000

Run in production:
    uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from config import get_settings
from database import init_firebase
from routers import admin as admin_router
from routers import records as records_router

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger   = logging.getLogger(__name__)
settings = get_settings()

# ── Rate limiter ───────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


# ══════════════════════════════════════════════════════════════════
#  LIFESPAN — startup / shutdown hooks
# ══════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting %s API server...", settings.APP_NAME)
    init_firebase()
    logger.info("✅ All services ready.")
    yield
    logger.info("👋 Shutting down.")


# ══════════════════════════════════════════════════════════════════
#  APP FACTORY
# ══════════════════════════════════════════════════════════════════

app = FastAPI(
    title=f"{settings.APP_NAME} — Student Records API",
    description=(
        "Server-side API for TutorTrack AI — a student performance tracking system "
        "for teachers. Manages student records (name, test date, marks), "
        "grade computation, analytics, and admin authentication."
    ),
    version="1.0.0",
    docs_url="/api/docs" if settings.APP_ENV != "production" else None,
    redoc_url="/api/redoc" if settings.APP_ENV != "production" else None,
    lifespan=lifespan,
)

app.state.limiter = limiter

# ── CORS ────────────────────────────────────────────────────────────────────
_origins = [o.strip() for o in settings.FRONTEND_ORIGIN.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ── Request timing logger ──────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s → %d  (%.1f ms)",
        request.method, request.url.path, response.status_code, ms
    )
    return response

app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ══════════════════════════════════════════════════════════════════
#  ROUTES
# ══════════════════════════════════════════════════════════════════

app.include_router(admin_router.router)
app.include_router(records_router.router)


# ══════════════════════════════════════════════════════════════════
#  HEALTH CHECK
# ══════════════════════════════════════════════════════════════════

@app.get("/api/health", tags=["health"])
async def health():
    """Simple liveness check — useful for monitoring / load balancers."""
    return {"status": "ok", "service": settings.APP_NAME}
