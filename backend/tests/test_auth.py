import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User

REGISTER = "/api/v1/auth/register"
LOGIN    = "/api/v1/auth/login"
VERIFY   = "/api/v1/auth/verify-email"
LOGOUT   = "/api/v1/auth/logout"
REFRESH  = "/api/v1/auth/refresh"

USER = {"email": "auth@test.com", "password": "TestPass123", "full_name": "Auth Test"}


async def _register(client: AsyncClient, data: dict = USER) -> dict:
    resp = await client.post(REGISTER, json=data)
    assert resp.status_code == 201
    return resp.json()


async def _get_token(db_session: AsyncSession, email: str) -> str:
    """Grab the verification token directly from DB — avoids parsing console logs."""
    result = await db_session.execute(select(User).where(User.email == email))
    return result.scalar_one().verification_token


async def _verify_and_login(client: AsyncClient, db_session: AsyncSession, email: str, password: str) -> dict:
    token = await _get_token(db_session, email)
    await client.post(VERIFY, json={"token": token})
    resp = await client.post(LOGIN, json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()


# ── Registration ──────────────────────────────────────────────────────────────

async def test_register_returns_201(client: AsyncClient):
    resp = await client.post(REGISTER, json=USER)
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == USER["email"]
    assert data["role"] == "subscriber"
    assert data["is_verified"] is False
    assert "password" not in data
    assert "password_hash" not in data


async def test_register_duplicate_email_returns_400(client: AsyncClient):
    await _register(client)
    resp = await client.post(REGISTER, json=USER)
    assert resp.status_code == 400
    assert "already registered" in resp.json()["detail"]


# ── Login behaviour ───────────────────────────────────────────────────────────

async def test_login_unverified_user_returns_400(client: AsyncClient):
    # Design decision: 400 (not 401) so frontend can show "check your inbox"
    await _register(client)
    resp = await client.post(LOGIN, json={"email": USER["email"], "password": USER["password"]})
    assert resp.status_code == 400
    assert "not verified" in resp.json()["detail"].lower()


async def test_login_wrong_password_returns_401(client: AsyncClient, db_session: AsyncSession):
    await _register(client)
    token = await _get_token(db_session, USER["email"])
    await client.post(VERIFY, json={"token": token})

    resp = await client.post(LOGIN, json={"email": USER["email"], "password": "WrongPassword!"})
    assert resp.status_code == 401


async def test_login_unknown_email_returns_401(client: AsyncClient):
    resp = await client.post(LOGIN, json={"email": "nobody@test.com", "password": "TestPass123"})
    assert resp.status_code == 401


# ── Email verification + login ────────────────────────────────────────────────

async def test_verify_email_then_login_succeeds(client: AsyncClient, db_session: AsyncSession):
    await _register(client)
    token = await _get_token(db_session, USER["email"])

    verify_resp = await client.post(VERIFY, json={"token": token})
    assert verify_resp.status_code == 200
    assert verify_resp.json()["is_verified"] is True

    login_resp = await client.post(LOGIN, json={"email": USER["email"], "password": USER["password"]})
    assert login_resp.status_code == 200
    tokens = login_resp.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "bearer"


async def test_verify_invalid_token_returns_400(client: AsyncClient):
    resp = await client.post(VERIFY, json={"token": "not-a-real-token"})
    assert resp.status_code == 400


# ── Logout ────────────────────────────────────────────────────────────────────

async def test_logout_without_token_returns_401(client: AsyncClient):
    resp = await client.post(LOGOUT)
    assert resp.status_code == 401


async def test_logout_with_token_returns_204(client: AsyncClient, db_session: AsyncSession):
    await _register(client)
    tokens = await _verify_and_login(client, db_session, USER["email"], USER["password"])

    resp = await client.post(
        LOGOUT,
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 204


# ── Token refresh ─────────────────────────────────────────────────────────────

async def test_refresh_token_returns_new_access_token(client: AsyncClient, db_session: AsyncSession):
    await _register(client)
    tokens = await _verify_and_login(client, db_session, USER["email"], USER["password"])

    resp = await client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert "access_token" in new_tokens
    assert new_tokens["token_type"] == "bearer"
    # Refresh token is unchanged until Phase 6 adds token rotation
    assert new_tokens["refresh_token"] == tokens["refresh_token"]


async def test_refresh_with_access_token_returns_401(client: AsyncClient, db_session: AsyncSession):
    # Passing an access token where a refresh token is expected must be rejected
    await _register(client)
    tokens = await _verify_and_login(client, db_session, USER["email"], USER["password"])

    resp = await client.post(REFRESH, json={"refresh_token": tokens["access_token"]})
    assert resp.status_code == 401
