"""
Phase 4 — /api/v1/recommendations endpoint tests.

No network, no ChromaDB, no Groq. The recommender boundary
(rag.recommender.get_recommendations) is monkeypatched so:
  - happy-path tests inject a fixed 6-item response,
  - fallback tests inject a GroqUnavailableError so the
    recommendation_service falls back to the live `recommendations` DB table
    (seeded by the test with rows that are distinguishable from any mock).

Run with:
    py -3.12 -m pytest backend/tests/test_recommendations.py -v
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import secrets

from models.alert import Alert
from models.enums import (
    AlertStatus,
    AlertType,
    RecommendationCategory,
    SeverityLevel,
)
from models.recommendation import Recommendation
from models.subscription import Subscription
from models.user import User
from rag.recommender import GroqUnavailableError
from schemas.recommendation import RecommendationItem

ENDPOINT = "/api/v1/recommendations"

# Six fixed items returned by the mocked recommender on the happy path. Order
# matches the canonical sort (evacuation -> kit -> shelter -> medical -> contact)
# because the real rag.recommender.get_recommendations returns pre-sorted; we
# mock at that boundary so we mirror its contract.
HAPPY_RAG_ITEMS: list[RecommendationItem] = [
    RecommendationItem(category="evacuation", title="Move to higher ground", body="Evacuate immediately."),
    RecommendationItem(category="evacuation", title="Pre-plan two routes",   body="Know two routes out."),
    RecommendationItem(category="kit",        title="72-hour go-bag",        body="Water, food, torch, meds."),
    RecommendationItem(category="shelter",    title="Upper-floor shelter",   body="Move to highest floor."),
    RecommendationItem(category="medical",    title="Avoid floodwater",      body="Wash with clean water."),
    RecommendationItem(category="contact",    title="Call emergency line",   body="Notify authorities."),
]

VALID_CATEGORIES = {"evacuation", "kit", "shelter", "medical", "contact"}
EXPECTED_ORDER   = ["evacuation", "kit", "shelter", "medical", "contact"]


# ── Mock fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_rag_ok(monkeypatch):
    """Patch rag.recommender.get_recommendations to return HAPPY_RAG_ITEMS.

    The service module imports recommender as `from rag import recommender as
    rag_recommender` so calls go through `rag_recommender.get_recommendations`.
    Patching the attribute on the rag.recommender module hits the same object.
    """
    def fake_get_recommendations(**kwargs):
        return list(HAPPY_RAG_ITEMS)

    monkeypatch.setattr(
        "rag.recommender.get_recommendations", fake_get_recommendations
    )


@pytest.fixture
def mock_rag_groq_down(monkeypatch):
    """Force the recommender to raise GroqUnavailableError so the service
    falls back to the DB recommendations table."""
    def fake_get_recommendations(**kwargs):
        raise GroqUnavailableError("simulated Groq outage")

    monkeypatch.setattr(
        "rag.recommender.get_recommendations", fake_get_recommendations
    )


# ── DB seed helpers ───────────────────────────────────────────────────────────

# Distinct unique titles so the fallback test can prove the DB path was used
# (a mock returning 6 generic items would never produce these strings).
SEEDED_FALLBACK_TITLES = [
    "DB_FALLBACK_unique_title_evacuation_1",
    "DB_FALLBACK_unique_title_kit_1",
    "DB_FALLBACK_unique_title_shelter_1",
    "DB_FALLBACK_unique_title_medical_1",
    "DB_FALLBACK_unique_title_contact_1",
]


async def _seed_fallback_rows(
    db: AsyncSession,
    disaster_type: str = "Earthquake",
    severity: SeverityLevel = SeverityLevel.critical,
) -> None:
    """Insert 5 fallback rows in the recommendations table for the given key.
    Intentionally NOT 6 so the count alone proves the response came from DB,
    not from any mock that would return 6."""
    rows = [
        Recommendation(
            disaster_type  = disaster_type,
            severity_level = severity,
            category       = RecommendationCategory.evacuation,
            title          = SEEDED_FALLBACK_TITLES[0],
            body           = "Evacuate to higher ground.",
        ),
        Recommendation(
            disaster_type  = disaster_type,
            severity_level = severity,
            category       = RecommendationCategory.kit,
            title          = SEEDED_FALLBACK_TITLES[1],
            body           = "Prepare a 72-hour go-bag.",
        ),
        Recommendation(
            disaster_type  = disaster_type,
            severity_level = severity,
            category       = RecommendationCategory.shelter,
            title          = SEEDED_FALLBACK_TITLES[2],
            body           = "Seek upper floors if trapped.",
        ),
        Recommendation(
            disaster_type  = disaster_type,
            severity_level = severity,
            category       = RecommendationCategory.medical,
            title          = SEEDED_FALLBACK_TITLES[3],
            body           = "Avoid floodwater contact.",
        ),
        Recommendation(
            disaster_type  = disaster_type,
            severity_level = severity,
            category       = RecommendationCategory.contact,
            title          = SEEDED_FALLBACK_TITLES[4],
            body           = "Call local emergency services.",
        ),
    ]
    for row in rows:
        db.add(row)
    await db.commit()


# ── Auth helper (mirrors test_predictions._register_and_login) ────────────────

async def _register_verify_login(
    client: AsyncClient,
    db_session: AsyncSession,
    email: str,
    password: str = "TestPass99!",
) -> tuple[str, uuid.UUID]:
    """Register → verify → login. Returns (access_token, user_id)."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Reco Test"},
    )
    assert resp.status_code == 201, resp.text

    result = await db_session.execute(
        select(User).where(User.email == email)
    )
    user = result.scalar_one()

    resp = await client.post(
        "/api/v1/auth/verify-email", json={"token": user.verification_token}
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"], user.id


# ─────────────────────────────────────────────────────────────────────────────
#  1, 2, 3 — Happy path: 6 items, valid categories, correct order
# ─────────────────────────────────────────────────────────────────────────────

async def test_happy_path_returns_6_items(client: AsyncClient, mock_rag_ok):
    resp = await client.get(
        ENDPOINT,
        params={"disaster_type": "Flood", "severity": "High", "region_name": "Cairo"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["items"]) == 6


async def test_happy_path_categories_all_valid(client: AsyncClient, mock_rag_ok):
    resp = await client.get(
        ENDPOINT,
        params={"disaster_type": "Flood", "severity": "High", "region_name": "Cairo"},
    )
    assert resp.status_code == 200
    for item in resp.json()["items"]:
        assert item["category"] in VALID_CATEGORIES, item


async def test_happy_path_items_sorted(client: AsyncClient, mock_rag_ok):
    """Categories appear in CATEGORY_ORDER. Duplicates within a category are OK."""
    resp = await client.get(
        ENDPOINT,
        params={"disaster_type": "Flood", "severity": "High", "region_name": "Cairo"},
    )
    assert resp.status_code == 200
    categories = [i["category"] for i in resp.json()["items"]]

    # Returned order must be non-decreasing in the canonical rank
    rank = {c: idx for idx, c in enumerate(EXPECTED_ORDER)}
    ranks = [rank[c] for c in categories]
    assert ranks == sorted(ranks), (
        f"items not sorted by category. order={categories}"
    )


# ─────────────────────────────────────────────────────────────────────────────
#  4 — Fallback: Groq raises -> DB table serves -> endpoint still 200 with items
# ─────────────────────────────────────────────────────────────────────────────

async def test_fallback_to_db_when_groq_unavailable(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_rag_groq_down,
):
    """Forces GroqUnavailableError, seeds 5 DB rows, asserts endpoint returns
    items that match the seeded DB content — not a mocked 6-item list.

    Uses (Earthquake, Critical) — a bucket guaranteed empty in the dev DB —
    so the assertion can't be contaminated by previously committed rows in
    other (disaster_type, severity) buckets."""
    await _seed_fallback_rows(
        db_session, disaster_type="Earthquake", severity=SeverityLevel.critical,
    )

    resp = await client.get(
        ENDPOINT,
        params={"disaster_type": "Earthquake", "severity": "Critical", "region_name": "Tokyo"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # 5 (not 6) — proves the DB path served the response, not any mock.
    assert len(body["items"]) == 5, (
        f"expected 5 items from DB seed, got {len(body['items'])} — fallback not exercised"
    )

    returned_titles = {i["title"] for i in body["items"]}
    assert returned_titles == set(SEEDED_FALLBACK_TITLES), (
        f"returned titles do not match seeded DB rows.\n"
        f"  seeded:   {set(SEEDED_FALLBACK_TITLES)}\n"
        f"  returned: {returned_titles}"
    )

    # Sort order is enforced by recommendation_service._fallback_from_db
    categories = [i["category"] for i in body["items"]]
    rank = {c: idx for idx, c in enumerate(EXPECTED_ORDER)}
    assert [rank[c] for c in categories] == sorted([rank[c] for c in categories])


async def test_fallback_returns_empty_when_db_has_no_rows(
    client: AsyncClient, mock_rag_groq_down
):
    """No DB rows seeded for (Storm, Critical). Fallback returns []; endpoint
    still returns 200 — never 500."""
    resp = await client.get(
        ENDPOINT,
        params={"disaster_type": "Storm", "severity": "Critical", "region_name": "Manila"},
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == []


# ─────────────────────────────────────────────────────────────────────────────
#  5 — Validation: 422 on bad query params
# ─────────────────────────────────────────────────────────────────────────────

async def test_invalid_disaster_type_returns_422(client: AsyncClient):
    resp = await client.get(
        ENDPOINT,
        params={"disaster_type": "Hurricane", "severity": "High", "region_name": "Cairo"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["query", "disaster_type"]


async def test_invalid_severity_returns_422(client: AsyncClient):
    resp = await client.get(
        ENDPOINT,
        params={"disaster_type": "Flood", "severity": "critical", "region_name": "Cairo"},  # lowercase
    )
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["loc"] == ["query", "severity"]


async def test_missing_region_name_returns_422(client: AsyncClient):
    resp = await client.get(
        ENDPOINT,
        params={"disaster_type": "Flood", "severity": "High"},
    )
    assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
#  6 — Personalisation notice
# ─────────────────────────────────────────────────────────────────────────────

async def test_personalisation_notice_for_user_with_prior_alert(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_rag_ok,
):
    """User has a prior Alert tied to a Subscription whose region matches the
    query. Endpoint must return a non-null personalisation_notice mentioning
    the disaster type and region."""
    token, user_id = await _register_verify_login(
        client, db_session, "user_with_alert@test.com"
    )

    sub = Subscription(
        user_id           = user_id,
        region_name       = "Northern Africa",
        latitude          = 30.06,
        longitude         = 31.24,
        unsubscribe_token = secrets.token_urlsafe(32),
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)

    alert = Alert(
        subscription_id = sub.id,
        user_id         = user_id,
        alert_type      = AlertType.high_risk_immediate,
        disaster_type   = "Flood",
        severity_level  = SeverityLevel.high,
        message_body    = "Prior alert from a previous prediction cycle",
        status          = AlertStatus.sent,
    )
    db_session.add(alert)
    await db_session.commit()

    resp = await client.get(
        ENDPOINT,
        params={"disaster_type": "Flood", "severity": "High", "region_name": "Northern Africa"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["personalisation_notice"] is not None
    notice = body["personalisation_notice"]
    assert "previously warned" in notice.lower()
    assert "Flood" in notice
    assert "Northern Africa" in notice


async def test_no_personalisation_notice_for_authenticated_user_without_prior_alert(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_rag_ok,
):
    """Authenticated user has never been alerted for this (disaster_type,
    region) → personalisation_notice is null."""
    token, _ = await _register_verify_login(
        client, db_session, "user_no_alert@test.com"
    )

    resp = await client.get(
        ENDPOINT,
        params={"disaster_type": "Flood", "severity": "High", "region_name": "Northern Africa"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["personalisation_notice"] is None


async def test_no_personalisation_notice_for_guest(
    client: AsyncClient,
    mock_rag_ok,
):
    """Guests (no Authorization header) skip the personalisation check entirely."""
    resp = await client.get(
        ENDPOINT,
        params={"disaster_type": "Flood", "severity": "High", "region_name": "Northern Africa"},
    )
    assert resp.status_code == 200
    assert resp.json()["personalisation_notice"] is None


async def test_personalisation_skipped_when_region_does_not_match(
    client: AsyncClient,
    db_session: AsyncSession,
    mock_rag_ok,
):
    """Prior alert exists for the user — but for a DIFFERENT region. Notice
    must be null (proves the join filter on Subscription.region_name works)."""
    token, user_id = await _register_verify_login(
        client, db_session, "user_other_region@test.com"
    )

    sub = Subscription(
        user_id           = user_id,
        region_name       = "Eastern Asia",
        latitude          = 35.0,
        longitude         = 135.0,
        unsubscribe_token = secrets.token_urlsafe(32),
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)

    alert = Alert(
        subscription_id = sub.id,
        user_id         = user_id,
        alert_type      = AlertType.high_risk_immediate,
        disaster_type   = "Flood",
        severity_level  = SeverityLevel.high,
        status          = AlertStatus.sent,
    )
    db_session.add(alert)
    await db_session.commit()

    resp = await client.get(
        ENDPOINT,
        params={"disaster_type": "Flood", "severity": "High", "region_name": "Northern Africa"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["personalisation_notice"] is None
