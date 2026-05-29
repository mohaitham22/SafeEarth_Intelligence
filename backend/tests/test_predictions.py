"""
Phase 3 — prediction API tests.

All tests mock `ml.predictor.predict()` via monkeypatch so they run without
requiring `backend/saved_models/*.pkl` to exist. The router + service +
DB persistence layers are exercised end-to-end through ASGITransport;
the only thing replaced is the ML inference call itself.

Run with:
    py -3.12 -m pytest backend/tests/test_predictions.py -v
"""
from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from models.prediction import Prediction
from models.user import User


# ── Constants ────────────────────────────────────────────────────────────────

PREDICT_BODY: dict[str, Any] = {
    "latitude":      30.06,
    "longitude":     31.24,
    "region_name":   "Northern Africa",
    "country":       "Egypt",
    "continent":     "Africa",
    "disaster_type": "Flood",
    "season":        7,
}

FORECAST_BODY: dict[str, Any] = {
    "latitude":      30.06,
    "longitude":     31.24,
    "region_name":   "Northern Africa",
    "country":       "Egypt",
    "continent":     "Africa",
    "disaster_type": "Flood",
    "force_refresh": False,
}

# Default response returned by the mocked predictor — shape matches what the
# real `ml.predictor.predict()` returns. Individual tests override fields via
# the `mock_predict` fixture's configure() callable.
DEFAULT_MOCK_RESPONSE: dict[str, Any] = {
    "disaster_type":               "Flood",
    "probability_score":           0.55,
    "severity_level":              "Medium",
    "risk_score":                  42.3,
    "estimated_deaths":            10,
    "estimated_injuries":          20,
    "estimated_affected":          5_000,
    "estimated_damage_usd":        15_000,        # thousands USD
    "uninsured_loss_usd":          12_000,        # thousands USD
    "shap_explanation":            [
        {"feature": "latitude",  "contribution_pct": 50.0},
        {"feature": "longitude", "contribution_pct": 30.0},
        {"feature": "month_sin", "contribution_pct": 20.0},
    ],
    "secondary_disaster_warning":  "Floods historically trigger Landslides",
    "seasonal_peak_months":        [6, 7, 8],
    "data_quality":                "full",
    "data_source":                 "country",
    "country_used":                "Egypt",
    "n_events":                    100,
}

# Six fixed recommendations the mocked recommendation_service returns. Shape
# matches schemas.recommendation.RecommendationItem (Pydantic validates each
# item when PredictionResponse serialises the dict).
MOCK_RECOMMENDATIONS: list[dict[str, Any]] = [
    {"category": "evacuation", "title": "Move to higher ground",  "body": "Evacuate to higher ground immediately."},
    {"category": "evacuation", "title": "Pre-plan two routes",    "body": "Know two routes out that avoid known flood zones."},
    {"category": "kit",        "title": "72-hour go-bag",         "body": "Water, food, torch, meds, IDs, radio."},
    {"category": "shelter",    "title": "Upper-floor shelter",    "body": "If trapped, move to the highest floor with an exit."},
    {"category": "medical",    "title": "Avoid floodwater",       "body": "Wash with clean water; seek care for any wound."},
    {"category": "contact",    "title": "Call emergency line",    "body": "Notify your national emergency number and Red Cross."},
]


# ── Mock fixture for ml.predictor.predict() + recommendation_service ────────

@pytest.fixture
def mock_predict(monkeypatch):
    """Patch `ml.predictor.predict` AND `recommendation_service.get_for_prediction`.

    Without the pkl files we cannot run real inference, and without a live RAG
    pipeline we cannot fetch real recommendations. Both are mocked so the
    router + service + DB persistence layers are exercised end-to-end through
    ASGITransport.

    Returns a `configure(**overrides)` callable for predictor overrides; the
    recommendation fixture always returns MOCK_RECOMMENDATIONS.
    """
    state: dict[str, Any] = {"override": {}, "raise": None}

    def fake_predict(*args, **kwargs):
        if state["raise"] is not None:
            raise state["raise"]
        merged = {**DEFAULT_MOCK_RESPONSE, **state["override"]}
        if "disaster_type" in kwargs:
            merged["disaster_type"] = kwargs["disaster_type"]
        return merged

    async def fake_get_for_prediction(*args, **kwargs):
        return [dict(item) for item in MOCK_RECOMMENDATIONS]

    monkeypatch.setattr("ml.predictor.predict", fake_predict)
    # predictor_service.py does `from services import recommendation_service`,
    # so we patch the attribute on the recommendation_service module — that's
    # the same object predictor_service references at call time.
    monkeypatch.setattr(
        "services.recommendation_service.get_for_prediction",
        fake_get_for_prediction,
    )
    # Phase 6: dispatch_critical_alert now has real logic (DB + email). Mock it
    # here so Critical-severity prediction tests stay fast and don't spin up
    # real fan-out sessions. The real function is tested in test_alerts.py.
    async def fake_dispatch_critical_alert(**_kwargs):
        pass

    monkeypatch.setattr(
        "services.alert_service.dispatch_critical_alert",
        fake_dispatch_critical_alert,
    )

    def configure(*, _raise: Exception | None = None, **overrides):
        state["raise"] = _raise
        state["override"] = overrides

    return configure


# ── Auth helpers ─────────────────────────────────────────────────────────────

async def _register_and_login(
    client: AsyncClient,
    db_session,
    email: str,
    password: str = "TestPass99!",
) -> str:
    """Register → verify → login. Returns access token."""
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Test User"},
    )
    assert resp.status_code == 201, resp.text

    result = await db_session.execute(
        select(User.verification_token).where(User.email == email)
    )
    token = result.scalar_one()

    resp = await client.post("/api/v1/auth/verify-email", json={"token": token})
    assert resp.status_code == 200, resp.text

    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
async def auth_client(client, db_session):
    """`AsyncClient` with a verified Subscriber's JWT in the default headers."""
    token = await _register_and_login(client, db_session, "predict_test@example.com")
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


# ─────────────────────────────────────────────────────────────────────────────
#  1, 16 — Auth required
# ─────────────────────────────────────────────────────────────────────────────

async def test_predict_unauthenticated(client, mock_predict):
    """No Authorization header → 401."""
    resp = await client.post("/api/v1/predictions/predict", json=PREDICT_BODY)
    assert resp.status_code == 401


async def test_predict_guest_blocked(client, mock_predict):
    """Guest (no token) cannot reach the predict endpoint."""
    resp = await client.post("/api/v1/predictions/predict", json=PREDICT_BODY)
    assert resp.status_code in (401, 403)


# ─────────────────────────────────────────────────────────────────────────────
#  2 — Success path: full response shape
# ─────────────────────────────────────────────────────────────────────────────

REQUIRED_FIELDS = (
    "id", "disaster_type", "probability_score", "severity_level",
    "risk_score", "estimated_deaths", "estimated_injuries",
    "estimated_affected", "estimated_damage_usd", "uninsured_loss_usd",
    "shap_explanation", "secondary_disaster_warning",
    "seasonal_peak_months", "data_quality", "data_source",
    "n_events", "recommendations", "model_version", "created_at",
)


async def test_predict_as_subscriber_success(auth_client, mock_predict):
    resp = await auth_client.post("/api/v1/predictions/predict", json=PREDICT_BODY)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for field in REQUIRED_FIELDS:
        assert field in data, f"missing field: {field}"
    # Phase 4: recommendations field is populated by the RAG pipeline
    # (mocked here — recommendation_service.get_for_prediction returns
    # MOCK_RECOMMENDATIONS). Previously this field was [].
    assert len(data["recommendations"]) == len(MOCK_RECOMMENDATIONS)
    assert data["recommendations"][0]["category"] == "evacuation"
    assert data["recommendations"][-1]["category"] == "contact"
    for item in data["recommendations"]:
        assert {"category", "title", "body"} <= set(item.keys())


# ─────────────────────────────────────────────────────────────────────────────
#  3 — Probability range
# ─────────────────────────────────────────────────────────────────────────────

async def test_predict_probability_between_0_and_1(auth_client, mock_predict):
    mock_predict(probability_score=0.55, severity_level="Medium")
    resp = await auth_client.post("/api/v1/predictions/predict", json=PREDICT_BODY)
    assert resp.status_code == 200
    p = resp.json()["probability_score"]
    assert 0.0 <= p <= 1.0


# ─────────────────────────────────────────────────────────────────────────────
#  4–7 — Each severity bucket round-trips through the persistence layer
# ─────────────────────────────────────────────────────────────────────────────

async def test_predict_severity_low(auth_client, mock_predict):
    mock_predict(probability_score=0.20, severity_level="Low")
    resp = await auth_client.post("/api/v1/predictions/predict", json=PREDICT_BODY)
    assert resp.status_code == 200
    assert resp.json()["severity_level"] == "Low"


async def test_predict_severity_medium(auth_client, mock_predict):
    mock_predict(probability_score=0.45, severity_level="Medium")
    resp = await auth_client.post("/api/v1/predictions/predict", json=PREDICT_BODY)
    assert resp.status_code == 200
    assert resp.json()["severity_level"] == "Medium"


async def test_predict_severity_high(auth_client, mock_predict):
    mock_predict(probability_score=0.65, severity_level="High")
    resp = await auth_client.post("/api/v1/predictions/predict", json=PREDICT_BODY)
    assert resp.status_code == 200
    assert resp.json()["severity_level"] == "High"


async def test_predict_severity_critical(auth_client, mock_predict):
    mock_predict(probability_score=0.85, severity_level="Critical")
    resp = await auth_client.post("/api/v1/predictions/predict", json=PREDICT_BODY)
    assert resp.status_code == 200
    assert resp.json()["severity_level"] == "Critical"


# ─────────────────────────────────────────────────────────────────────────────
#  8 — Risk score range
# ─────────────────────────────────────────────────────────────────────────────

async def test_predict_risk_score_between_0_and_100(auth_client, mock_predict):
    mock_predict(risk_score=42.3)
    resp = await auth_client.post("/api/v1/predictions/predict", json=PREDICT_BODY)
    assert resp.status_code == 200
    score = resp.json()["risk_score"]
    assert 0.0 <= score <= 100.0


# ─────────────────────────────────────────────────────────────────────────────
#  9 — SHAP top-3 features
# ─────────────────────────────────────────────────────────────────────────────

async def test_predict_shap_has_3_features(auth_client, mock_predict):
    resp = await auth_client.post("/api/v1/predictions/predict", json=PREDICT_BODY)
    assert resp.status_code == 200
    shap = resp.json()["shap_explanation"]
    assert len(shap) == 3
    for item in shap:
        assert "feature" in item and "contribution_pct" in item


# ─────────────────────────────────────────────────────────────────────────────
#  10 — SHAP contributions sum to ~100
# ─────────────────────────────────────────────────────────────────────────────

async def test_predict_shap_contributions_sum_to_100(auth_client, mock_predict):
    resp = await auth_client.post("/api/v1/predictions/predict", json=PREDICT_BODY)
    assert resp.status_code == 200
    total = sum(item["contribution_pct"] for item in resp.json()["shap_explanation"])
    assert abs(total - 100.0) < 0.5, f"shap contributions sum to {total}, expected ~100"


# ─────────────────────────────────────────────────────────────────────────────
#  11 — Persists to DB
# ─────────────────────────────────────────────────────────────────────────────

async def test_predict_saves_to_db(auth_client, db_session, mock_predict):
    before = (await db_session.execute(select(func.count(Prediction.id)))).scalar_one()
    resp = await auth_client.post("/api/v1/predictions/predict", json=PREDICT_BODY)
    assert resp.status_code == 200
    after = (await db_session.execute(select(func.count(Prediction.id)))).scalar_one()
    assert after == before + 1


# ─────────────────────────────────────────────────────────────────────────────
#  12 — Unknown disaster type → 422 (Literal validator at schema boundary)
# ─────────────────────────────────────────────────────────────────────────────

async def test_predict_unknown_disaster_type(auth_client, mock_predict):
    body = {**PREDICT_BODY, "disaster_type": "Hurricane"}
    resp = await auth_client.post("/api/v1/predictions/predict", json=body)
    assert resp.status_code in (400, 422)


# ─────────────────────────────────────────────────────────────────────────────
#  13 — History is per-user
# ─────────────────────────────────────────────────────────────────────────────

async def test_history_returns_only_user_predictions(client, db_session, mock_predict):
    token_a = await _register_and_login(client, db_session, "user_a@test.com")
    token_b = await _register_and_login(client, db_session, "user_b@test.com")

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User A → 2 predictions, User B → 1 prediction
    for _ in range(2):
        r = await client.post(
            "/api/v1/predictions/predict",
            json=PREDICT_BODY,
            headers=headers_a,
        )
        assert r.status_code == 200, r.text

    r = await client.post(
        "/api/v1/predictions/predict",
        json=PREDICT_BODY,
        headers=headers_b,
    )
    assert r.status_code == 200, r.text

    hist_a = await client.get("/api/v1/predictions/history", headers=headers_a)
    hist_b = await client.get("/api/v1/predictions/history", headers=headers_b)
    assert hist_a.json()["total"] == 2
    assert hist_b.json()["total"] == 1


# ─────────────────────────────────────────────────────────────────────────────
#  14 — Forecast returns 30 items
# ─────────────────────────────────────────────────────────────────────────────

async def test_forecast_30d_returns_30_items(auth_client, mock_predict):
    body = {**FORECAST_BODY, "force_refresh": True}
    resp = await auth_client.post("/api/v1/predictions/forecast-30d", json=body)
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 30


# ─────────────────────────────────────────────────────────────────────────────
#  15 — Forecast cache: second call returns same 30 without inserting new rows
# ─────────────────────────────────────────────────────────────────────────────

async def test_forecast_30d_cache(auth_client, db_session, mock_predict):
    body = {**FORECAST_BODY, "force_refresh": False}

    # First call — should insert 30 rows tagged with a forecast_batch_id
    r1 = await auth_client.post("/api/v1/predictions/forecast-30d", json=body)
    assert r1.status_code == 200, r1.text
    assert len(r1.json()) == 30

    count1 = (await db_session.execute(
        select(func.count(Prediction.id)).where(Prediction.forecast_batch_id.isnot(None))
    )).scalar_one()
    assert count1 == 30

    # Second call — must hit the 24h cache, return 30, not insert anything new
    r2 = await auth_client.post("/api/v1/predictions/forecast-30d", json=body)
    assert r2.status_code == 200, r2.text
    assert len(r2.json()) == 30

    count2 = (await db_session.execute(
        select(func.count(Prediction.id)).where(Prediction.forecast_batch_id.isnot(None))
    )).scalar_one()
    assert count2 == 30, f"cache miss — inserted {count2 - 30} extra rows on second call"


# ─────────────────────────────────────────────────────────────────────────────
#  /classify and /impact — new exploratory endpoints (no DB write)
# ─────────────────────────────────────────────────────────────────────────────

CLASSIFY_BODY: dict[str, Any] = {
    "latitude":  30.06,
    "longitude": 31.24,
    "continent": "Africa",
    "year":      2024,
    "season":    7,
}

IMPACT_BODY: dict[str, Any] = {
    "latitude":    30.06,
    "longitude":   31.24,
    "continent":   "Africa",
    "year":        2024,
    "season":      7,
    "region_name": "Northern Africa",
    "country":     "Egypt",
}

MOCK_CLASSIFY_RESPONSE: dict[str, Any] = {
    "ranked": [
        {"disaster_type": "Flood",    "probability": 0.50},
        {"disaster_type": "Storm",    "probability": 0.20},
        {"disaster_type": "Earthquake", "probability": 0.10},
        {"disaster_type": "Drought",  "probability": 0.07},
        {"disaster_type": "Wildfire", "probability": 0.05},
        {"disaster_type": "Landslide", "probability": 0.04},
        {"disaster_type": "Volcanic activity", "probability": 0.02},
        {"disaster_type": "Extreme temperature", "probability": 0.02},
    ],
    "top_type": "Flood",
    "top_probability": 0.50,
    "model_version": "v4.2",
}

MOCK_IMPACT_RESPONSE: dict[str, Any] = {
    "predicted_disaster_type": "Flood",
    "probability": 0.50,
    "expected_events": 5,
    "estimated_deaths": 10,
    "estimated_injuries": 20,
    "estimated_affected": 5000,
    "estimated_damage_usd": 15000,
    "uninsured_loss_usd": 10000,
    "data_source": "country",
    "model_version": "v4.2",
}


@pytest.fixture
def mock_classify_impact(monkeypatch):
    """Patch classify_all_types and predict_impact on the predictor module."""
    monkeypatch.setattr("ml.predictor.classify_all_types", lambda **_kwargs: MOCK_CLASSIFY_RESPONSE)
    monkeypatch.setattr("ml.predictor.predict_impact",     lambda **_kwargs: MOCK_IMPACT_RESPONSE)


async def test_classify_unauthenticated(client, mock_classify_impact):
    """/classify without token → 401."""
    resp = await client.post("/api/v1/predictions/classify", json=CLASSIFY_BODY)
    assert resp.status_code == 401


async def test_classify_returns_8_types(auth_client, mock_classify_impact):
    """/classify returns 8 ranked types whose probabilities roughly sum to 1."""
    resp = await auth_client.post("/api/v1/predictions/classify", json=CLASSIFY_BODY)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "ranked" in data and "top_type" in data and "top_probability" in data
    assert len(data["ranked"]) == 8
    total = sum(item["probability"] for item in data["ranked"])
    assert abs(total - 1.0) < 0.01, f"probabilities sum to {total}, expected ~1"


async def test_impact_unauthenticated(client, mock_classify_impact):
    """/impact without token → 401."""
    resp = await client.post("/api/v1/predictions/impact", json=IMPACT_BODY)
    assert resp.status_code == 401


async def test_impact_returns_required_fields(auth_client, mock_classify_impact):
    """/impact returns all expected impact fields."""
    resp = await auth_client.post("/api/v1/predictions/impact", json=IMPACT_BODY)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for field in (
        "predicted_disaster_type", "probability", "expected_events",
        "estimated_deaths", "estimated_injuries", "estimated_affected",
        "estimated_damage_usd", "uninsured_loss_usd", "data_source", "model_version",
    ):
        assert field in data, f"missing field: {field}"
