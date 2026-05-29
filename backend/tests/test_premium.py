"""
Tests for the premium payment flow (Phase 7).

POST /api/v1/premium/checkout  — Subscriber+, returns checkout URL (MockPaymentService)
POST /api/v1/premium/webhook   — Public, verifies signature FIRST then upgrades role
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.enums import PaymentStatus, UserRole
from models.payment import Payment
from models.user import User

REGISTER = "/api/v1/auth/register"
LOGIN    = "/api/v1/auth/login"
VERIFY   = "/api/v1/auth/verify-email"
CHECKOUT = "/api/v1/premium/checkout"
WEBHOOK  = "/api/v1/premium/webhook"


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _register_and_login(
    client: AsyncClient,
    db_session: AsyncSession,
    email: str,
    password: str = "TestPass123",
) -> str:
    """Register, verify, log in a subscriber. Returns access token."""
    await client.post(
        REGISTER,
        json={"email": email, "password": password, "full_name": "Premium Tester"},
    )
    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
    await client.post(VERIFY, json={"token": user.verification_token})
    resp = await client.post(LOGIN, json={"email": email, "password": password})
    assert resp.status_code == 200
    return resp.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _get_user(db: AsyncSession, email: str) -> User:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one()


def _webhook_body(event_type: str, session_id: str) -> bytes:
    return json.dumps({"type": event_type, "session_id": session_id}).encode()


# ── POST /premium/checkout ────────────────────────────────────────────────────

async def test_checkout_monthly_returns_201(
    client: AsyncClient, db_session: AsyncSession
):
    token = await _register_and_login(client, db_session, "pm_monthly@test.com")
    resp = await client.post(
        CHECKOUT,
        json={"plan_name": "monthly"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "mock-checkout" in data["checkout_url"]
    assert data["session_id"].startswith("mock_")
    assert data["plan_name"] == "monthly"


async def test_checkout_yearly_returns_201(
    client: AsyncClient, db_session: AsyncSession
):
    token = await _register_and_login(client, db_session, "pm_yearly@test.com")
    resp = await client.post(
        CHECKOUT,
        json={"plan_name": "yearly"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    assert resp.json()["plan_name"] == "yearly"


async def test_checkout_guest_returns_401(client: AsyncClient):
    resp = await client.post(CHECKOUT, json={"plan_name": "monthly"})
    assert resp.status_code == 401


async def test_checkout_invalid_plan_returns_422(
    client: AsyncClient, db_session: AsyncSession
):
    token = await _register_and_login(client, db_session, "pm_invalid@test.com")
    resp = await client.post(
        CHECKOUT,
        json={"plan_name": "enterprise"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


# ── POST /premium/webhook ─────────────────────────────────────────────────────

async def test_webhook_success_upgrades_role(
    client: AsyncClient, db_session: AsyncSession
):
    token = await _register_and_login(client, db_session, "pm_upgrade@test.com")

    # Create checkout so a pending payment row exists
    co = await client.post(
        CHECKOUT,
        json={"plan_name": "monthly"},
        headers=_auth(token),
    )
    assert co.status_code == 201
    session_id = co.json()["session_id"]

    # Send valid webhook
    resp = await client.post(
        WEBHOOK,
        content=_webhook_body("payment.success", session_id),
        headers={"Content-Type": "application/json", "X-Mock-Signature": "valid-sig"},
    )
    assert resp.status_code == 200
    assert resp.json()["received"] is True

    # User role must be premium in the DB
    user = await _get_user(db_session, "pm_upgrade@test.com")
    await db_session.refresh(user)
    assert user.role == UserRole.premium

    # Payment row status must be succeeded (query by user_id — provider_transaction_id
    # may be updated by MockPaymentService to its generated mock_txn_ value)
    pay_result = await db_session.execute(
        select(Payment).where(Payment.user_id == user.id)
    )
    payment = pay_result.scalar_one()
    assert payment.status == PaymentStatus.succeeded
    assert payment.premium_activated_at is not None
    assert payment.premium_expires_at is not None


async def test_webhook_missing_signature_returns_400_no_db_write(
    client: AsyncClient, db_session: AsyncSession
):
    """Signature verified BEFORE any DB write — bad sig must leave DB untouched."""
    token = await _register_and_login(client, db_session, "pm_badsig@test.com")
    user = await _get_user(db_session, "pm_badsig@test.com")

    # Send webhook with NO signature header (empty string resolves to empty)
    resp = await client.post(
        WEBHOOK,
        content=_webhook_body("payment.success", "any-session-id"),
        headers={"Content-Type": "application/json"},  # X-Mock-Signature omitted
    )
    assert resp.status_code == 400

    # No payment row must have been inserted (verify-FIRST means no DB touch)
    pay_result = await db_session.execute(
        select(Payment).where(Payment.user_id == user.id)
    )
    assert pay_result.scalars().all() == []

    # User role must still be subscriber
    await db_session.refresh(user)
    assert user.role == UserRole.subscriber


async def test_webhook_duplicate_delivery_is_idempotent(
    client: AsyncClient, db_session: AsyncSession
):
    token = await _register_and_login(client, db_session, "pm_idem@test.com")

    co = await client.post(
        CHECKOUT,
        json={"plan_name": "yearly"},
        headers=_auth(token),
    )
    session_id = co.json()["session_id"]
    sig_headers = {"Content-Type": "application/json", "X-Mock-Signature": "valid"}

    # First webhook — succeeds and upgrades
    r1 = await client.post(
        WEBHOOK,
        content=_webhook_body("payment.success", session_id),
        headers=sig_headers,
    )
    assert r1.status_code == 200
    assert r1.json()["received"] is True

    # Second webhook with same session_id — idempotent, must not error
    r2 = await client.post(
        WEBHOOK,
        content=_webhook_body("payment.success", session_id),
        headers=sig_headers,
    )
    assert r2.status_code == 200
    assert r2.json()["received"] is True

    # Exactly one payment row, still succeeded
    user = await _get_user(db_session, "pm_idem@test.com")
    pay_result = await db_session.execute(
        select(Payment).where(Payment.user_id == user.id)
    )
    payments = pay_result.scalars().all()
    assert len(payments) == 1
    assert payments[0].status == PaymentStatus.succeeded

    # User role still premium (not double-upgraded to something else)
    await db_session.refresh(user)
    assert user.role == UserRole.premium


# ── GET /predictions/{id}/pdf  (Part A — PDF endpoints) ──────────────────────

async def test_pdf_requires_premium(client: AsyncClient, db_session: AsyncSession):
    """Subscriber (non-premium) cannot download a prediction PDF — must get 403."""
    token = await _register_and_login(client, db_session, "pm_pdf_sub@test.com")
    user  = await _get_user(db_session, "pm_pdf_sub@test.com")

    from models.enums import SeverityLevel
    from models.prediction import Prediction

    pred = Prediction(
        user_id=user.id,
        disaster_type="Flood",
        probability_score=0.7,
        severity_level=SeverityLevel.high,
        risk_score=55.0,
        model_version="v4.2",
    )
    db_session.add(pred)
    await db_session.flush()

    resp = await client.get(f"/api/v1/predictions/{pred.id}/pdf", headers=_auth(token))
    assert resp.status_code == 403


async def test_pdf_premium_user_gets_pdf(client: AsyncClient, db_session: AsyncSession):
    """Premium user can download their own prediction as a valid PDF."""
    token = await _register_and_login(client, db_session, "pm_pdf_premium@test.com")
    user  = await _get_user(db_session, "pm_pdf_premium@test.com")

    # Upgrade to premium in-DB (same pattern as other tests)
    user.role = UserRole.premium
    await db_session.flush()

    from models.enums import SeverityLevel
    from models.prediction import Prediction

    pred = Prediction(
        user_id=user.id,
        disaster_type="Flood",
        probability_score=0.7,
        severity_level=SeverityLevel.high,
        risk_score=55.0,
        model_version="v4.2",
    )
    db_session.add(pred)
    await db_session.flush()

    resp = await client.get(f"/api/v1/predictions/{pred.id}/pdf", headers=_auth(token))
    assert resp.status_code == 200
    assert "application/pdf" in resp.headers["content-type"]
    assert len(resp.content) > 100  # non-empty PDF bytes


async def test_pdf_wrong_user_gets_403(client: AsyncClient, db_session: AsyncSession):
    """Premium user cannot download another user's prediction — ownership check."""
    token_a = await _register_and_login(client, db_session, "pm_pdf_owner@test.com")
    token_b = await _register_and_login(client, db_session, "pm_pdf_other@test.com")

    user_a = await _get_user(db_session, "pm_pdf_owner@test.com")
    user_b = await _get_user(db_session, "pm_pdf_other@test.com")

    user_a.role = UserRole.premium
    user_b.role = UserRole.premium
    await db_session.flush()

    from models.enums import SeverityLevel
    from models.prediction import Prediction

    pred = Prediction(
        user_id=user_a.id,
        disaster_type="Storm",
        probability_score=0.8,
        severity_level=SeverityLevel.critical,
        risk_score=75.0,
        model_version="v4.2",
    )
    db_session.add(pred)
    await db_session.flush()

    # user_b tries to download user_a's prediction
    resp = await client.get(f"/api/v1/predictions/{pred.id}/pdf", headers=_auth(token_b))
    assert resp.status_code == 403


# ── Feature 8: Premium expiry checker ────────────────────────────────────────

async def test_downgrade_expired_premium(db_session: AsyncSession):
    """Daily expiry check downgrades expired Premium users and deactivates
    oldest excess subscriptions beyond the free limit of 3."""
    import secrets
    from datetime import timedelta
    from models.premium_plan import PremiumPlan
    from models.subscription import Subscription
    from services.premium_service import downgrade_expired_premium

    now = datetime.now(timezone.utc)

    user = User(
        email="pm_expiry_check@test.com",
        password_hash="hashed",
        full_name="Expiry Test",
        role=UserRole.premium,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    plan_result = await db_session.execute(
        select(PremiumPlan).where(PremiumPlan.name == "monthly")
    )
    plan = plan_result.scalar_one()

    payment = Payment(
        user_id=user.id,
        plan_id=plan.id,
        provider="mock",
        amount_usd=5.00,
        status=PaymentStatus.succeeded,
        premium_activated_at=now - timedelta(days=30, seconds=1),
        premium_expires_at=now - timedelta(seconds=1),  # already expired
    )
    db_session.add(payment)

    for i in range(5):
        sub = Subscription(
            user_id=user.id,
            region_name=f"Expiry Region {i}",
            latitude=float(i),
            longitude=float(i),
            is_active=True,
            unsubscribe_token=secrets.token_urlsafe(32),
        )
        db_session.add(sub)

    await db_session.flush()

    n = await downgrade_expired_premium(db_session)

    await db_session.refresh(user)
    await db_session.refresh(payment)

    assert user.role == UserRole.subscriber
    assert n >= 1

    # payment.premium_expires_at must NOT be erased (audit trail)
    assert payment.premium_expires_at is not None

    subs_result = await db_session.execute(
        select(Subscription).where(Subscription.user_id == user.id)
    )
    all_subs = subs_result.scalars().all()
    assert len(all_subs) == 5  # no deletions — only soft deactivation

    inactive = [s for s in all_subs if not s.is_active]
    active = [s for s in all_subs if s.is_active]
    assert len(inactive) == 2  # 5 - 3 = 2 oldest deactivated
    assert len(active) == 3    # free limit kept


# ── Unit test: pdf_service.generate_prediction_pdf ───────────────────────────

def test_generate_prediction_pdf_returns_valid_pdf_bytes():
    """generate_prediction_pdf() with a mock PredictionResponse (no pkl/DB needed).

    Note: PDF content streams are ASCII85-encoded so raw text is not findable
    there. Assertions target the PDF Info dictionary (/Title, /Subject) which is
    always stored as plain-text PDF syntax — no encoding, always grep-able.

    Verifies:
    - Return type is bytes and non-empty
    - Starts with b'%PDF' (valid PDF magic bytes)
    - Contains b'SafeEarth' (in /Title metadata — confirms header was written)
    - Contains b'EM-DAT'   (in /Subject metadata — confirms footer was written)
    """
    import uuid
    from schemas.prediction import PredictionResponse, SHAPFeature
    from schemas.recommendation import RecommendationItem
    from services.pdf_service import generate_prediction_pdf

    pred = PredictionResponse(
        id=uuid.uuid4(),
        disaster_type="Flood",
        probability_score=0.72,
        severity_level="High",
        risk_score=58.3,
        estimated_deaths=120,
        estimated_injuries=450,
        estimated_affected=32_000,
        estimated_damage_usd=15_000,
        uninsured_loss_usd=10_800,
        shap_explanation=[
            SHAPFeature(feature="latitude",       contribution_pct=24.3),
            SHAPFeature(feature="has_magnitude",  contribution_pct=17.5),
            SHAPFeature(feature="decade",         contribution_pct=15.7),
        ],
        secondary_disaster_warning="Historical data shows Landslide risk in 34% of Flood events.",
        seasonal_peak_months=[6, 7, 8],
        data_quality="full",
        data_source="country",
        country_used="Egypt",
        n_events=158,
        recommendations=[
            RecommendationItem(
                category="evacuation",
                title="Identify evacuation routes",
                body="Know at least two evacuation routes from your home and workplace.",
            ),
            RecommendationItem(
                category="kit",
                title="Prepare emergency kit",
                body="Stock food, water, and medications for at least 72 hours.",
            ),
            RecommendationItem(
                category="shelter",
                title="Identify safe shelter",
                body="Locate the nearest flood-safe shelter or upper-floor refuge.",
            ),
            RecommendationItem(
                category="medical",
                title="Stock essential medications",
                body="Keep a 7-day supply of prescription medications waterproofed.",
            ),
            RecommendationItem(
                category="contact",
                title="Save emergency contacts",
                body="Save local emergency services, hospital, and family contacts.",
            ),
            RecommendationItem(
                category="evacuation",
                title="Move vehicles to high ground",
                body="Park vehicles on elevated ground before floodwaters rise.",
            ),
        ],
        model_version="v4.2",
        created_at=datetime.now(timezone.utc),
    )

    pdf_bytes = generate_prediction_pdf(pred, "Test User")

    assert isinstance(pdf_bytes, bytes),  "must return bytes"
    assert len(pdf_bytes) > 0,            "PDF must not be empty"
    assert pdf_bytes[:4] == b"%PDF",      "must start with PDF magic bytes"
    assert b"SafeEarth" in pdf_bytes,     "/Title metadata must contain 'SafeEarth'"
    assert b"EM-DAT" in pdf_bytes,        "/Subject metadata must contain 'EM-DAT'"
