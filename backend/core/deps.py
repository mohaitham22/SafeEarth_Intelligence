import secrets
import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from core.security import decode_token
from database import get_db
from models.user import User

# Used by get_current_user — extracts Bearer token from Authorization header.
# tokenUrl points to the login endpoint for Swagger UI's "Authorize" button.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# auto_error=False so missing token returns None instead of raising 401 (guest flow).
oauth2_scheme_optional = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login", auto_error=False
)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Requires a valid access token. Raises 401 if missing or invalid."""
    payload = decode_token(token)
    user_id = uuid.UUID(payload["sub"])

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_optional_user(
    token: str | None = Depends(oauth2_scheme_optional),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Returns User if token is present and valid, None if no token (guest). Never raises."""
    if token is None:
        return None
    try:
        payload = decode_token(token)
    except HTTPException:
        return None

    user_id = uuid.UUID(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Requires role='admin'. Raises 403 otherwise."""
    if current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


async def require_premium(
    current_user: User = Depends(get_current_user),
) -> User:
    """Requires role='premium' or 'admin'. Raises 403 otherwise."""
    if current_user.role.value not in ("premium", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Premium subscription required",
        )
    return current_user


async def require_dispatch_auth(
    request: Request,
    token: str | None = Depends(oauth2_scheme_optional),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Dual-credential guard for POST /alerts/dispatch.

    Accepts either:
      1. X-Dispatch-Secret header matching ALERT_DISPATCH_SECRET (n8n machine caller)
      2. A valid Admin JWT in the Authorization: Bearer header

    If ALERT_DISPATCH_SECRET is empty the header path is disabled; admin JWT still works.
    """
    settings = get_settings()

    # Path 1 — shared-secret header (n8n)
    header_secret = request.headers.get("X-Dispatch-Secret", "")
    if header_secret and settings.alert_dispatch_secret:
        if secrets.compare_digest(header_secret, settings.alert_dispatch_secret):
            return

    # Path 2 — Admin JWT
    if token is not None:
        try:
            payload = decode_token(token)
            user_id = uuid.UUID(payload["sub"])
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user and user.role.value == "admin":
                return
        except HTTPException:
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Valid X-Dispatch-Secret header or Admin JWT required.",
        headers={"WWW-Authenticate": "Bearer"},
    )
