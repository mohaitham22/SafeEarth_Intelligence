"""
backend/tests/test_regions.py

Tests for Phase 2, Step 7: GET /api/v1/regions/* endpoints.
All region endpoints are public and serve precomputed JSON from emdat_lookup.

The load_emdat_data autouse fixture in conftest.py calls emdat_lookup.load_all()
once per session — ASGITransport does not fire ASGI lifespan events, so that
session-scoped fixture is the correct substitute.
"""
import pytest
from httpx import AsyncClient


async def test_trends_returns_correct_structure(client: AsyncClient):
    """/regions/trends — must have a decades list and at least Flood + Storm keys."""
    resp = await client.get("/api/v1/regions/trends")
    assert resp.status_code == 200
    data = resp.json()

    assert data["decades"] == [1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]
    assert "Flood" in data
    assert "Storm" in data
    assert isinstance(data["Flood"], list)
    assert len(data["Flood"]) == 8  # one count per decade


async def test_continent_stats_returns_continents(client: AsyncClient):
    """/regions/continent-stats — must include all 5 continents."""
    resp = await client.get("/api/v1/regions/continent-stats")
    assert resp.status_code == 200
    data = resp.json()

    assert {"Africa", "Americas", "Asia", "Europe", "Oceania"}.issubset(set(data.keys()))


async def test_insurance_gap_values_in_range(client: AsyncClient):
    """/regions/insurance-gap — every ratio must be in [0.0, 1.0]."""
    resp = await client.get("/api/v1/regions/insurance-gap")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data) > 0
    for dtype, ratio in data.items():
        assert 0.0 <= ratio <= 1.0, f"{dtype}: ratio {ratio!r} out of [0, 1]"


async def test_seasonal_peaks_valid(client: AsyncClient):
    """/regions/seasonal-peaks — every month number must be 1–12."""
    resp = await client.get("/api/v1/regions/seasonal-peaks")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data) > 0
    for dtype, months in data.items():
        for m in months:
            assert 1 <= m <= 12, f"{dtype}: invalid month {m}"


async def test_secondary_disasters_count_threshold(client: AsyncClient):
    """/regions/secondary-disasters — every entry must have count >= 50."""
    resp = await client.get("/api/v1/regions/secondary-disasters")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data) > 0
    for dtype, associations in data.items():
        for entry in associations:
            assert entry["count"] >= 50, (
                f"{dtype} → {entry['type']}: count {entry['count']} below threshold 50"
            )


async def test_timeseries_year_count(client: AsyncClient):
    """/regions/timeseries — Flood must have exactly 62 by_year entries (1960–2021)."""
    resp = await client.get("/api/v1/regions/timeseries")
    assert resp.status_code == 200
    data = resp.json()

    assert "by_year" in data
    assert "Flood" in data["by_year"]
    assert len(data["by_year"]["Flood"]) == 62


async def test_regions_stats_with_country(client: AsyncClient):
    """/regions/stats with country — 200 and data_source is one of the 3 valid tiers."""
    resp = await client.get(
        "/api/v1/regions/stats",
        params={"disaster_type": "Flood", "country": "Egypt"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["data_source"] in ("country", "region", "global")
    assert "n_events" in data
    assert data["n_events"] > 0


async def test_regions_stats_without_country(client: AsyncClient):
    """/regions/stats without country — falls through to global tier."""
    resp = await client.get(
        "/api/v1/regions/stats",
        params={"disaster_type": "Flood"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["data_source"] == "global"
    assert data["country_used"] is None


async def test_regions_stats_unknown_disaster_returns_400(client: AsyncClient):
    """/regions/stats with an unknown disaster type must return 400."""
    resp = await client.get(
        "/api/v1/regions/stats",
        params={"disaster_type": "Banana"},
    )
    assert resp.status_code == 400


async def test_regions_stats_missing_param_returns_422(client: AsyncClient):
    """/regions/stats with no query params — missing required disaster_type → 422."""
    resp = await client.get("/api/v1/regions/stats")
    assert resp.status_code == 422


async def test_risk_map_returns_valid_points(client: AsyncClient):
    """/regions/risk-map — every point has valid in-range lat/lon, risk_score
    in [0, 100], and disaster_type is one of the 8 EM-DAT types. Cache-Control
    is set so the edge cache can serve it cheaply."""
    resp = await client.get("/api/v1/regions/risk-map")
    assert resp.status_code == 200
    assert "max-age=3600" in resp.headers.get("cache-control", "")

    data = resp.json()
    assert isinstance(data, list)
    assert len(data) > 0  # generator should produce >= 1 point

    valid_types = {
        "Flood", "Storm", "Earthquake", "Wildfire",
        "Volcanic activity", "Landslide", "Drought", "Extreme temperature",
    }
    for p in data:
        assert -90  <= p["lat"] <= 90,  f"bad lat: {p}"
        assert -180 <= p["lon"] <= 180, f"bad lon: {p}"
        assert 0.0  <= p["risk_score"] <= 100.0, f"bad risk_score: {p}"
        assert p["disaster_type"] in valid_types, f"bad type: {p}"
