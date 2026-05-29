"""
Tests for the alerts feature (Phase 6).

Unit tests  — dispatch_critical_alert service logic (mocked DB + email)
Integration — POST /alerts/dispatch (dual-auth: admin JWT and shared-secret paths)
Integration — GET  /alerts/history  (per-user isolation, pagination)
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.alert import Alert
from models.enums import AlertFrequency, AlertStatus, AlertType, SeverityLevel, UserRole
from models.premium_email_log import PremiumEmailLog
from models.subscription import Subscription
from models.user import User
from services import alert_service

# ── Endpoints ─────────────────────────────────────────────────────────────────

REGISTER = "/api/v1/auth/register"
LOGIN    = "/api/v1/auth/login"
VERIFY   = "/api/v1/auth/verify-email"
DISPATCH = "/api/v1/alerts/dispatch"
HISTORY  = "/api/v1/alerts/history"

_DISPATCH_SECRET = "unit-test-dispatch-secret-abc"


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _register_and_login(
    client: AsyncClient,
    db_session: AsyncSession,
    email: str,
    password: str = "TestPass123",
    role: str = "subscriber",
) -> str:
    """Register, optionally elevate role, verify, login. Returns access token."""
    await client.post(
        REGISTER,
        json={"email": email, "password": password, "full_name": "Test User"},
    )
    result = await db_session.execute(select(User).where(User.email == email))
    user   = result.scalar_one()

    if role != "subscriber":
        user.role = UserRole(role)
        db_session.add(user)
        await db_session.flush()

    await client.post(VERIFY, json={"token": user.verification_token})
    resp = await client.post(LOGIN, json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _get_user(db_session: AsyncSession, email: str) -> User:
    result = await db_session.execute(select(User).where(User.email == email))
    return result.scalar_one()


async def _create_subscription(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    region_name: str = "Cairo",
    alert_frequency: AlertFrequency = AlertFrequency.weekly,
) -> Subscription:
    sub = Subscription(
        id               = uuid.uuid4(),
        user_id          = user_id,
        region_name      = region_name,
        latitude         = 30.06,
        longitude        = 31.24,
        alert_frequency  = alert_frequency,
        is_active        = True,
        unsubscribe_token= secrets.token_urlsafe(32),
    )
    db_session.add(sub)
    await db_session.flush()
    return sub


# ── Mock: make AsyncSessionLocal() yield the test session ─────────────────────

class _SessionContextMock:
    """Wraps the test session so `async with AsyncSessionLocal() as db:` works in tests."""
    def __init__(self, session: AsyncSession):
        self._session = session

    def __call__(self):
        return self  # called like AsyncSessionLocal()

    async def __aenter__(self) -> AsyncSession:
        return self._session

    async def __aexit__(self, *_args) -> None:
        pass  # don't close the shared test session


# ─────────────────────────────────────────────────────────────────────────────
# 1. Unit — Subscriber gets in-app alert, NO email
# ─────────────────────────────────────────────────────────────────────────────

async def test_subscriber_gets_inapp_alert_no_email(
    client: AsyncClient, db_session: AsyncSession
):
    await _register_and_login(client, db_session, "alert_sub@test.com")
    user = await _get_user(db_session, "alert_sub@test.com")
    await _create_subscription(db_session, user.id, region_name="Cairo")

    mock_email     = AsyncMock(return_value="dev-fallback")
    session_mock   = _SessionContextMock(db_session)

    with (
        patch("services.alert_service.AsyncSessionLocal", session_mock),
        patch("services.email_service.send_premium_alert_email", mock_email),
    ):
        await alert_service.dispatch_critical_alert(
            prediction_id = uuid.uuid4(),
            user_id       = user.id,
            disaster_type = "Flood",
            severity      = "Critical",
            region_name   = "Cairo",
        )

    # One Alert row must exist
    alerts = (await db_session.execute(
        select(Alert).where(Alert.user_id == user.id)
    )).scalars().all()
    assert len(alerts) == 1
    assert alerts[0].alert_type == AlertType.high_risk_immediate
    assert alerts[0].status     == AlertStatus.sent
    assert alerts[0].disaster_type == "Flood"

    # No email for free Subscriber
    mock_email.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 2. Unit — Premium gets alert + email + PremiumEmailLog
# ─────────────────────────────────────────────────────────────────────────────

async def test_premium_gets_alert_and_email_and_log(
    client: AsyncClient, db_session: AsyncSession
):
    await _register_and_login(client, db_session, "alert_prem@test.com", role="premium")
    user = await _get_user(db_session, "alert_prem@test.com")
    await _create_subscription(db_session, user.id, region_name="Cairo")

    mock_email   = AsyncMock(return_value="resend-msg-xyz")
    session_mock = _SessionContextMock(db_session)

    with (
        patch("services.alert_service.AsyncSessionLocal", session_mock),
        patch("services.email_service.send_premium_alert_email", mock_email),
    ):
        await alert_service.dispatch_critical_alert(
            prediction_id = uuid.uuid4(),
            user_id       = user.id,
            disaster_type = "Flood",
            severity      = "Critical",
            region_name   = "Cairo",
        )

    # Alert row
    alerts = (await db_session.execute(
        select(Alert).where(Alert.user_id == user.id)
    )).scalars().all()
    assert len(alerts) == 1
    alert = alerts[0]

    # Email called exactly once with the premium user's address
    mock_email.assert_called_once()
    assert mock_email.call_args[0][0] == user.email

    # PremiumEmailLog row with correct resend_message_id
    logs = (await db_session.execute(
        select(PremiumEmailLog).where(PremiumEmailLog.alert_id == alert.id)
    )).scalars().all()
    assert len(logs) == 1
    assert logs[0].resend_message_id == "resend-msg-xyz"
    assert logs[0].status.value      == "sent"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Unit — region_name=None skips fan-out entirely
# ─────────────────────────────────────────────────────────────────────────────

async def test_dispatch_critical_alert_no_region_is_noop(
    client: AsyncClient, db_session: AsyncSession
):
    await _register_and_login(client, db_session, "alert_noop@test.com")
    user = await _get_user(db_session, "alert_noop@test.com")
    await _create_subscription(db_session, user.id, region_name="Cairo")

    session_mock = _SessionContextMock(db_session)
    with patch("services.alert_service.AsyncSessionLocal", session_mock):
        await alert_service.dispatch_critical_alert(
            prediction_id = uuid.uuid4(),
            user_id       = user.id,
            disaster_type = "Flood",
            severity      = "Critical",
            region_name   = None,   # ← no region → skip
        )

    alerts = (await db_session.execute(
        select(Alert).where(Alert.user_id == user.id)
    )).scalars().all()
    assert alerts == []


# ─────────────────────────────────────────────────────────────────────────────
# 4. POST /alerts/dispatch — valid admin JWT → 200
# ─────────────────────────────────────────────────────────────────────────────

async def test_dispatch_admin_jwt_returns_200(
    client: AsyncClient, db_session: AsyncSession
):
    token = await _register_and_login(
        client, db_session, "dispatch_admin@test.com", role="admin"
    )
    resp = await client.post(
        DISPATCH,
        json={"alert_type": "weekly_digest"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "queued" in data
    assert "message" in data


# ─────────────────────────────────────────────────────────────────────────────
# 5. POST /alerts/dispatch — valid shared secret → 200 and creates alert rows
# ─────────────────────────────────────────────────────────────────────────────

async def test_dispatch_shared_secret_creates_alert_rows(
    client: AsyncClient, db_session: AsyncSession
):
    # Set up a subscriber with a weekly subscription
    await _register_and_login(client, db_session, "dispatch_secret@test.com")
    user = await _get_user(db_session, "dispatch_secret@test.com")
    await _create_subscription(db_session, user.id, alert_frequency=AlertFrequency.weekly)

    settings = __import__("config").get_settings()
    object.__setattr__(settings, "alert_dispatch_secret", _DISPATCH_SECRET)
    try:
        resp = await client.post(
            DISPATCH,
            json={"alert_type": "weekly_digest"},
            headers={"X-Dispatch-Secret": _DISPATCH_SECRET},
        )
        assert resp.status_code == 200
        assert resp.json()["queued"] >= 1
    finally:
        object.__setattr__(settings, "alert_dispatch_secret", "")

    # Alert row committed in DB (dispatch_alerts calls db.commit())
    alerts = (await db_session.execute(
        select(Alert).where(Alert.user_id == user.id)
    )).scalars().all()
    assert len(alerts) == 1
    assert alerts[0].alert_type == AlertType.weekly_digest


# ─────────────────────────────────────────────────────────────────────────────
# 6. POST /alerts/dispatch — missing auth → 401
# ─────────────────────────────────────────────────────────────────────────────

async def test_dispatch_no_auth_returns_401(client: AsyncClient):
    resp = await client.post(DISPATCH, json={"alert_type": "weekly_digest"})
    assert resp.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 7. POST /alerts/dispatch — wrong shared secret → 401
# ─────────────────────────────────────────────────────────────────────────────

async def test_dispatch_wrong_secret_returns_401(client: AsyncClient):
    settings = __import__("config").get_settings()
    object.__setattr__(settings, "alert_dispatch_secret", _DISPATCH_SECRET)
    try:
        resp = await client.post(
            DISPATCH,
            json={"alert_type": "weekly_digest"},
            headers={"X-Dispatch-Secret": "totally-wrong-secret"},
        )
        assert resp.status_code == 401
    finally:
        object.__setattr__(settings, "alert_dispatch_secret", "")


# ─────────────────────────────────────────────────────────────────────────────
# 8. GET /alerts/history — per-user isolation
# ─────────────────────────────────────────────────────────────────────────────

async def test_alert_history_per_user_isolation(
    client: AsyncClient, db_session: AsyncSession
):
    token_a = await _register_and_login(client, db_session, "hist_a@test.com")
    token_b = await _register_and_login(client, db_session, "hist_b@test.com")
    user_a  = await _get_user(db_session, "hist_a@test.com")
    sub_a   = await _create_subscription(db_session, user_a.id)

    # Insert one alert only for user A
    db_session.add(Alert(
        id              = uuid.uuid4(),
        subscription_id = sub_a.id,
        user_id         = user_a.id,
        alert_type      = AlertType.weekly_digest,
        sent_at         = datetime.now(timezone.utc),
        status          = AlertStatus.sent,
    ))
    await db_session.flush()

    resp_a = await client.get(HISTORY, headers=_auth(token_a))
    resp_b = await client.get(HISTORY, headers=_auth(token_b))

    assert resp_a.status_code == 200
    assert resp_a.json()["total"] == 1

    assert resp_b.status_code == 200
    assert resp_b.json()["total"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 9. GET /alerts/history — pagination
# ─────────────────────────────────────────────────────────────────────────────

async def test_alert_history_pagination(
    client: AsyncClient, db_session: AsyncSession
):
    token = await _register_and_login(client, db_session, "hist_page@test.com")
    user  = await _get_user(db_session, "hist_page@test.com")
    sub   = await _create_subscription(db_session, user.id)

    for _ in range(3):
        db_session.add(Alert(
            id              = uuid.uuid4(),
            subscription_id = sub.id,
            user_id         = user.id,
            alert_type      = AlertType.weekly_digest,
            sent_at         = datetime.now(timezone.utc),
            status          = AlertStatus.sent,
        ))
    await db_session.flush()

    resp = await client.get(f"{HISTORY}?page=1&page_size=2", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"]     == 3
    assert data["page"]      == 1
    assert data["page_size"] == 2
    assert len(data["items"]) == 2


# ─────────────────────────────────────────────────────────────────────────────
# 10. GET /alerts/history — unauthenticated → 401
# ─────────────────────────────────────────────────────────────────────────────

async def test_alert_history_requires_auth(client: AsyncClient):
    resp = await client.get(HISTORY)
    assert resp.status_code == 401
