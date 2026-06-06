import logging
import secrets
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from models.user import User
from schemas.auth import UserRegister

logger = logging.getLogger(__name__)


async def register_user(db: AsyncSession, user_data: UserRegister) -> User:
    existing = await db.execute(select(User).where(User.email == user_data.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    verification_token = secrets.token_urlsafe(32)

    user = User(
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        full_name=user_data.full_name,
        verification_token=verification_token,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # The verification email (incl. the token) is dispatched by the /auth/register
    # router via BackgroundTasks → email_service.send_verification_email. When SMTP
    # creds are absent that service dev-logs the token, so local dev still works.
    logger.info("Registered %s (pending verification)", user.email)

    return user


async def resend_verification(db: AsyncSession, email: str) -> User | None:
    """Regenerate the verification token for an unverified user and return them.

    Returns None for unknown emails or already-verified accounts so the endpoint
    can respond uniformly without revealing which addresses exist. The caller is
    responsible for dispatching the email (via BackgroundTasks).
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or user.is_verified:
        return None

    user.verification_token = secrets.token_urlsafe(32)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(
    db: AsyncSession, email: str, password: str
) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        return None

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email not verified. Check your inbox for the verification link.",
        )

    return user


async def verify_email_token(db: AsyncSession, token: str) -> User:
    result = await db.execute(
        select(User).where(User.verification_token == token)
    )
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token",
        )

    user.is_verified = True
    user.verification_token = None
    await db.commit()
    await db.refresh(user)

    return user


async def refresh_access_token(db: AsyncSession, refresh_token: str) -> str:
    payload = decode_token(refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type — expected refresh token",
        )

    user_id = uuid.UUID(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return create_access_token(user.id)
