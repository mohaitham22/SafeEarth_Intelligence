from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_current_user
from core.security import create_access_token, create_refresh_token
from database import get_db
from models.user import User
from schemas.auth import (
    TokenRefresh,
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
    VerifyEmail,
)
from services.auth_service import (
    authenticate_user,
    refresh_access_token,
    register_user,
    verify_email_token,
)
from services import email_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: UserRegister,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    user = await register_user(db, body)
    background_tasks.add_task(
        email_service.send_verification_email, user.email, user.verification_token
    )
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    body: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    user = await authenticate_user(db, body.email, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/verify-email", response_model=UserResponse)
async def verify_email(
    body: VerifyEmail,
    db: AsyncSession = Depends(get_db),
):
    user = await verify_email_token(db, body.token)
    return user


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: TokenRefresh,
    db: AsyncSession = Depends(get_db),
):
    new_access_token = await refresh_access_token(db, body.refresh_token)
    return TokenResponse(
        access_token=new_access_token,
        refresh_token=body.refresh_token,  # unchanged until Phase 6 adds token rotation
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    _: User = Depends(get_current_user),
):
    # TODO: Phase 6 will add refresh token blacklist (server-side invalidation)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
