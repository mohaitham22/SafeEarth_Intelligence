"""
backend/tests/test_data_pipeline.py

Tests for Phase 2: EM-DAT lookup loaded at startup + /admin/data-status endpoint.
The client fixture triggers the FastAPI lifespan, so load_all() runs for every test here.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def test_emdat_lookup_loaded_at_startup(client: AsyncClient):
    """load_all() must run before the first request — data is non-empty."""
    from ml import emdat_lookup

    assert emdat_lookup.EMDAT_STATS, "EMDAT_STATS is empty — load_all() did not run"
    assert emdat_lookup.SECONDARY_DISASTERS, "SECONDARY_DISASTERS is empty"
    assert emdat_lookup.SEASONAL_PEAKS, "SEASONAL_PEAKS is empty"
    assert emdat_lookup.INSURANCE_RATIOS, "INSURANCE_RATIOS is empty"
    assert emdat_lookup.TRENDS, "TRENDS is empty"
    assert emdat_lookup.CONTINENT_STATS, "CONTINENT_STATS is empty"
    assert emdat_lookup.TIMESERIES, "TIMESERIES is empty"
    assert emdat_lookup.COUNTRY_TO_REGION, "COUNTRY_TO_REGION is empty"


async def test_data_status_rejects_unauthenticated(client: AsyncClient):
    """Unauthenticated request to /admin/data-status must be rejected."""
    resp = await client.get("/api/v1/admin/data-status")
    assert resp.status_code in (401, 403)


async def test_data_status_rejects_non_admin(client: AsyncClient, db_session: AsyncSession):
    """A regular subscriber must be rejected (403)."""
    from core.security import hash_password
    from models.enums import UserRole
    from models.user import User

    user = User(
        email="subscriber_ds@example.com",
        password_hash=hash_password("Pass123!"),
        full_name="Regular User",
        role=UserRole.subscriber,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()

    login = await client.post("/api/v1/auth/login", json={
        "email": "subscriber_ds@example.com",
        "password": "Pass123!",
    })
    assert login.status_code == 200
    token = login.json()["access_token"]

    resp = await client.get(
        "/api/v1/admin/data-status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


async def test_data_status_as_admin(client: AsyncClient, db_session: AsyncSession):
    """Admin user sees full data-status payload with all 7 files loaded."""
    from core.security import hash_password
    from models.enums import UserRole
    from models.user import User

    admin = User(
        email="admin_ds@example.com",
        password_hash=hash_password("AdminPass123!"),
        full_name="Admin DS",
        role=UserRole.admin,
        is_verified=True,
    )
    db_session.add(admin)
    await db_session.commit()

    login = await client.post("/api/v1/auth/login", json={
        "email": "admin_ds@example.com",
        "password": "AdminPass123!",
    })
    assert login.status_code == 200
    token = login.json()["access_token"]

    resp = await client.get(
        "/api/v1/admin/data-status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["loaded"] is True
    assert len(data["disaster_types"]) == 8
    assert set(data["disaster_types"]) == {
        "Drought", "Earthquake", "Extreme temperature",
        "Flood", "Landslide", "Storm", "Volcanic activity", "Wildfire",
    }
    assert data["countries_with_data"] == 225
    assert data["regions_with_data"] == 23
    assert len(data["files_present"]) == 7
