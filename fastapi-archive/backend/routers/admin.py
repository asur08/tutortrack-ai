"""
routers/admin.py — Authentication endpoints.
Identical structure to the Guesthouse admin router.

POST /api/auth/login           — returns JWT
POST /api/auth/change-password — changes admin password (requires JWT)
"""
import logging
from fastapi import APIRouter, HTTPException, Depends, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from auth import authenticate_admin, change_admin_password, create_access_token, require_admin
from config import get_settings
from models import LoginRequest, LoginResponse, ChangePasswordRequest, MessageResponse

logger   = logging.getLogger(__name__)
settings = get_settings()
router   = APIRouter(prefix="/api/auth", tags=["auth"])
limiter  = Limiter(key_func=get_remote_address)


@router.post("/login", response_model=LoginResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest):
    """
    Verify admin credentials and return a JWT bearer token.
    The token expires after JWT_EXPIRE_HOURS (default 8 hours).
    """
    if not await authenticate_admin(body.uid, body.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    token, expires_in = create_access_token(body.uid)
    logger.info("Admin '%s' logged in successfully.", body.uid)
    return LoginResponse(access_token=token, expires_in_seconds=expires_in)


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    body: ChangePasswordRequest,
    admin: str = Depends(require_admin),
):
    """Change the admin password. Requires a valid JWT."""
    ok = await change_admin_password(body.current_password, body.new_password)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    logger.info("Admin '%s' changed their password.", admin)
    return MessageResponse(message="Password changed successfully")
