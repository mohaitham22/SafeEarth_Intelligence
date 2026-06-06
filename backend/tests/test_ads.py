"""
Tests for the public GET /ads endpoint (home-page promotional content).
"""
from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from models.ad import Ad

ADS = "/api/v1/ads"


async def test_list_ads_is_public_and_returns_active_only(
    client: AsyncClient, db_session: AsyncSession
):
    db_session.add_all([
        Ad(title="ACTIVE_TEST_AD", is_active=True, sort_order=500),
        Ad(title="INACTIVE_TEST_AD", is_active=False, sort_order=501),
    ])
    await db_session.flush()

    resp = await client.get(ADS)  # no auth header — public
    assert resp.status_code == 200

    titles = [a["title"] for a in resp.json()]
    assert "ACTIVE_TEST_AD" in titles
    assert "INACTIVE_TEST_AD" not in titles


async def test_list_ads_sets_cache_header(client: AsyncClient):
    resp = await client.get(ADS)
    assert resp.status_code == 200
    assert "max-age" in resp.headers.get("cache-control", "")


async def test_list_ads_ordered_by_sort_order(
    client: AsyncClient, db_session: AsyncSession
):
    db_session.add_all([
        Ad(title="AD_ORDER_B", is_active=True, sort_order=901),
        Ad(title="AD_ORDER_A", is_active=True, sort_order=900),
    ])
    await db_session.flush()

    resp = await client.get(ADS)
    titles = [a["title"] for a in resp.json()]
    # A (sort_order 900) must appear before B (901).
    assert titles.index("AD_ORDER_A") < titles.index("AD_ORDER_B")
