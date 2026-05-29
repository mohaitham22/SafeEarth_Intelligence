"""
Tests for the subscriptions feature (Phase 6).

POST   /api/v1/subscriptions        — create (Subscriber+, 201)
GET    /api/v1/subscriptions        — list active only (Subscriber+, 200)
DELETE /api/v1/subscriptions/{tok}  — one-click unsubscribe (PUBLIC, no auth)
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from models.user import User

REGISTER = "/api/v1/auth/register"
LOGIN    = "/api/v1/auth/login"
VERIFY   = "/api/v1/auth/verify-email"
SUBS     = "/api/v1/subscriptions"

_BASE_PAYLOAD = {
    "region_name": "Cairo",
    "latitude":    30.06,
    "longitude":   31.24,
    "alert_frequency": "weekly",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _register_and_login(
    client: AsyncClient,
    db_session: AsyncSession,
    email: str,
    password: str = "TestPass123",
) -> dict:
    """Register, verify, and log in a fresh user. Returns token dict."""
    from sqlalchemy import select

    await client.post(REGISTER, json={"email": email, "password": password, "full_name": "Test"})
    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    await client.post(VERIFY, json={"token": user.verification_token})
    resp = await client.post(LOGIN, json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()


def _auth(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# ── POST /subscriptions ────────────────────────────────────────────────────────

async def test_create_subscription_returns_201(
    client: AsyncClient, db_session: AsyncSession
):
    tokens = await _register_and_login(client, db_session, "sub_create@test.com")
    resp = await client.post(SUBS, json=_BASE_PAYLOAD, headers=_auth(tokens))
    assert resp.status_code == 201
    data = resp.json()
    assert data["region_name"] == "Cairo"
    assert data["is_active"] is True
    assert "unsubscribe_token" in data
    assert len(data["unsubscribe_token"]) >= 32


async def test_create_subscription_requires_auth(client: AsyncClient):
    resp = await client.post(SUBS, json=_BASE_PAYLOAD)
    assert resp.status_code == 401


async def test_create_subscription_invalid_lat_returns_422(
    client: AsyncClient, db_session: AsyncSession
):
    tokens = await _register_and_login(client, db_session, "sub_invalid@test.com")
    payload = {**_BASE_PAYLOAD, "latitude": 999.0}
    resp = await client.post(SUBS, json=payload, headers=_auth(tokens))
    assert resp.status_code == 422


async def test_subscriber_limit_enforced_at_3(
    client: AsyncClient, db_session: AsyncSession
):
    tokens = await _register_and_login(client, db_session, "sub_limit@test.com")
    headers = _auth(tokens)

    # Create 3 subscriptions in different regions
    for i in range(3):
        payload = {**_BASE_PAYLOAD, "region_name": f"Region {i}", "latitude": float(i)}
        r = await client.post(SUBS, json=payload, headers=headers)
        assert r.status_code == 201, f"Expected 201, got {r.status_code} on sub {i}"

    # Fourth must fail
    payload = {**_BASE_PAYLOAD, "region_name": "Region 99", "latitude": 5.0}
    r = await client.post(SUBS, json=payload, headers=headers)
    assert r.status_code == 403
    assert "limit" in r.json()["detail"].lower()


# ── GET /subscriptions ─────────────────────────────────────────────────────────

async def test_list_subscriptions_requires_auth(client: AsyncClient):
    resp = await client.get(SUBS)
    assert resp.status_code == 401


async def test_list_subscriptions_returns_active_only(
    client: AsyncClient, db_session: AsyncSession
):
    tokens = await _register_and_login(client, db_session, "sub_list@test.com")
    headers = _auth(tokens)

    # Create two subscriptions
    r1 = await client.post(SUBS, json={**_BASE_PAYLOAD, "region_name": "Alpha"}, headers=headers)
    r2 = await client.post(SUBS, json={**_BASE_PAYLOAD, "region_name": "Beta", "latitude": 1.0}, headers=headers)
    assert r1.status_code == 201
    assert r2.status_code == 201

    # Unsubscribe the second one via its token
    token = r2.json()["unsubscribe_token"]
    await client.delete(f"{SUBS}/{token}")

    # List should only have the active one
    resp = await client.get(SUBS, headers=headers)
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["region_name"] == "Alpha"
    # Token is included in the authenticated list (needed for dashboard unsubscribe)
    assert "unsubscribe_token" in items[0]
    assert len(items[0]["unsubscribe_token"]) >= 32


async def test_list_subscriptions_isolated_per_user(
    client: AsyncClient, db_session: AsyncSession
):
    tokens_a = await _register_and_login(client, db_session, "sub_iso_a@test.com")
    tokens_b = await _register_and_login(client, db_session, "sub_iso_b@test.com")

    await client.post(SUBS, json=_BASE_PAYLOAD, headers=_auth(tokens_a))

    resp = await client.get(SUBS, headers=_auth(tokens_b))
    assert resp.status_code == 200
    assert resp.json() == []


# ── DELETE /subscriptions/{token} — public, no auth ──────────────────────────

async def test_unsubscribe_by_token_returns_200(
    client: AsyncClient, db_session: AsyncSession
):
    tokens = await _register_and_login(client, db_session, "sub_del@test.com")
    r = await client.post(SUBS, json=_BASE_PAYLOAD, headers=_auth(tokens))
    assert r.status_code == 201
    tok = r.json()["unsubscribe_token"]

    resp = await client.delete(f"{SUBS}/{tok}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "unsubscribed"


async def test_unsubscribe_invalid_token_returns_404(client: AsyncClient):
    resp = await client.delete(f"{SUBS}/definitely-not-a-real-token")
    assert resp.status_code == 404


async def test_unsubscribe_idempotent_already_inactive(
    client: AsyncClient, db_session: AsyncSession
):
    tokens = await _register_and_login(client, db_session, "sub_idem@test.com")
    r = await client.post(SUBS, json=_BASE_PAYLOAD, headers=_auth(tokens))
    tok = r.json()["unsubscribe_token"]

    await client.delete(f"{SUBS}/{tok}")          # first unsubscribe
    resp = await client.delete(f"{SUBS}/{tok}")   # second — must not 409
    assert resp.status_code == 200
