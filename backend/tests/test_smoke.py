from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession


def test_app_starts():
    from main import app
    assert app.title == "SafeEarth Intelligence API"
    assert app.version == "0.1.0"


async def test_health_endpoint(client: AsyncClient):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


async def test_docs_loads(client: AsyncClient):
    response = await client.get("/docs")
    assert response.status_code == 200


async def test_db_connects(db_session: AsyncSession):
    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar() == 1


async def test_premium_plans_seeded(db_session: AsyncSession):
    from models.premium_plan import PremiumPlan

    result = await db_session.execute(select(PremiumPlan).order_by(PremiumPlan.name))
    plans = result.scalars().all()

    assert len(plans) == 2

    by_name = {p.name: p for p in plans}
    assert set(by_name.keys()) == {"monthly", "yearly"}

    assert by_name["monthly"].price_usd == Decimal("5.00")
    assert by_name["monthly"].duration_days == 30
    assert by_name["monthly"].max_subscriptions == 10

    assert by_name["yearly"].price_usd == Decimal("48.00")
    assert by_name["yearly"].duration_days == 365
    assert by_name["yearly"].max_subscriptions == 10
