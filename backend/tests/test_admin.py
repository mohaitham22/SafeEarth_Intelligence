"""
Tests for the admin panel (backend phase — admin CRUD + stats + model-stats + Studio).

All tests require DB (uses the rollback-session pattern from conftest.py).
"""
from __future__ import annotations

import secrets
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ad import Ad
from models.enums import UserRole
from models.user import User

# ── Endpoints ─────────────────────────────────────────────────────────────────

REGISTER    = "/api/v1/auth/register"
LOGIN       = "/api/v1/auth/login"
VERIFY      = "/api/v1/auth/verify-email"
USERS       = "/api/v1/admin/users"
STATS       = "/api/v1/admin/stats"
MODEL_STATS = "/api/v1/admin/model-stats"
PREVIEW     = "/api/v1/admin/alerts/dispatch-preview"
ADMIN_ADS   = "/api/v1/admin/ads"
PUBLIC_ADS  = "/api/v1/ads"


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _register_and_login(
    client: AsyncClient,
    db_session: AsyncSession,
    email: str,
    role: str = "subscriber",
    password: str = "TestPass123",
) -> str:
    await client.post(REGISTER, json={"email": email, "password": password, "full_name": "T"})
    result = await db_session.execute(select(User).where(User.email == email))
    user = result.scalar_one()
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


# ─────────────────────────────────────────────────────────────────────────────
# 1. GET /admin/users — requires admin
# ─────────────────────────────────────────────────────────────────────────────

async def test_get_users_requires_admin(client: AsyncClient, db_session: AsyncSession):
    token = await _register_and_login(client, db_session, "admin_sub@test.com")
    resp  = await client.get(USERS, headers=_auth(token))
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# 2. GET /admin/users — paginated list returned for admin
# ─────────────────────────────────────────────────────────────────────────────

async def test_get_users_returns_paginated_list(
    client: AsyncClient, db_session: AsyncSession
):
    token = await _register_and_login(client, db_session, "admin_list@test.com", role="admin")
    resp  = await client.get(f"{USERS}?page=1&page_size=5", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "items"     in data
    assert "total"     in data
    assert "page"      in data
    assert "page_size" in data
    assert isinstance(data["items"], list)
    assert data["total"] >= 1     # at least the admin we just registered


# ─────────────────────────────────────────────────────────────────────────────
# 3. GET /admin/users — role filter
# ─────────────────────────────────────────────────────────────────────────────

async def test_get_users_role_filter(client: AsyncClient, db_session: AsyncSession):
    token = await _register_and_login(client, db_session, "admin_filt@test.com", role="admin")
    # Register a premium user so the filter has someone to return
    await _register_and_login(client, db_session, "admin_filt_prem@test.com", role="premium")

    resp = await client.get(f"{USERS}?role=premium", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert all(item["role"] == "premium" for item in data["items"])


# ─────────────────────────────────────────────────────────────────────────────
# 4. PATCH /admin/users/{id} — role change
# ─────────────────────────────────────────────────────────────────────────────

async def test_patch_user_role(client: AsyncClient, db_session: AsyncSession):
    admin_token = await _register_and_login(
        client, db_session, "admin_patch@test.com", role="admin"
    )
    # Register a target subscriber
    await _register_and_login(client, db_session, "admin_target@test.com")
    result = await db_session.execute(
        select(User).where(User.email == "admin_target@test.com")
    )
    target = result.scalar_one()

    resp = await client.patch(
        f"{USERS}/{target.id}",
        json={"role": "premium"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "premium"

    await db_session.refresh(target)
    assert target.role == UserRole.premium


# ─────────────────────────────────────────────────────────────────────────────
# 5. PATCH /admin/users/{id} — cannot change own role
# ─────────────────────────────────────────────────────────────────────────────

async def test_patch_user_cannot_change_own_role(
    client: AsyncClient, db_session: AsyncSession
):
    admin_token = await _register_and_login(
        client, db_session, "admin_self@test.com", role="admin"
    )
    result = await db_session.execute(
        select(User).where(User.email == "admin_self@test.com")
    )
    admin = result.scalar_one()

    resp = await client.patch(
        f"{USERS}/{admin.id}",
        json={"role": "subscriber"},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# 6. GET /admin/stats — requires admin
# ─────────────────────────────────────────────────────────────────────────────

async def test_get_stats_requires_admin(client: AsyncClient, db_session: AsyncSession):
    token = await _register_and_login(client, db_session, "admin_stats_sub@test.com")
    resp  = await client.get(STATS, headers=_auth(token))
    assert resp.status_code == 403


# ─────────────────────────────────────────────────────────────────────────────
# 7. GET /admin/stats — returns all expected top-level keys
# ─────────────────────────────────────────────────────────────────────────────

async def test_get_stats_returns_expected_keys(
    client: AsyncClient, db_session: AsyncSession
):
    token = await _register_and_login(client, db_session, "admin_stats@test.com", role="admin")
    resp  = await client.get(STATS, headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "users"         in data
    assert "predictions"   in data
    assert "subscriptions" in data
    assert "alerts"        in data
    assert "payments"      in data
    assert "email_logs"    in data
    # Spot-check nested keys
    assert "total"   in data["users"]
    assert "by_role" in data["users"]
    assert "total"   in data["predictions"]


# ─────────────────────────────────────────────────────────────────────────────
# 8. GET /admin/model-stats — contains expected ML metrics
# ─────────────────────────────────────────────────────────────────────────────

async def test_get_model_stats_contains_macro_f1(
    client: AsyncClient, db_session: AsyncSession
):
    token = await _register_and_login(
        client, db_session, "admin_model@test.com", role="admin"
    )
    resp = await client.get(MODEL_STATS, headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"]       == "v4.2"
    assert abs(data["macro_f1"]  - 0.7052) < 0.001
    assert abs(data["weighted_f1"] - 0.7587) < 0.001
    assert data["feature_count"] == 16
    assert "XGBoost" in data["ensemble"]
    assert len(data["per_class_f1"]) == 8


# ─────────────────────────────────────────────────────────────────────────────
# 9. POST /admin/ads — requires admin; new ad appears in public GET /ads
# ─────────────────────────────────────────────────────────────────────────────

async def test_create_ad_requires_admin(client: AsyncClient, db_session: AsyncSession):
    token = await _register_and_login(client, db_session, "admin_ad_sub@test.com")
    resp  = await client.post(
        ADMIN_ADS, json={"title": "Test Ad"}, headers=_auth(token)
    )
    assert resp.status_code == 403


async def test_create_ad_appears_in_public_get(
    client: AsyncClient, db_session: AsyncSession
):
    token = await _register_and_login(
        client, db_session, "admin_ad_create@test.com", role="admin"
    )
    resp = await client.post(
        ADMIN_ADS,
        json={"title": "Visible Ad", "is_active": True, "sort_order": 99},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    new_id = resp.json()["id"]

    public = await client.get(PUBLIC_ADS)
    assert public.status_code == 200
    ids = [a["id"] for a in public.json()]
    assert new_id in ids


# ─────────────────────────────────────────────────────────────────────────────
# 10. DELETE /admin/ads/{id} — soft-deletes; ad disappears from public view
# ─────────────────────────────────────────────────────────────────────────────

async def test_delete_ad_soft_removes(client: AsyncClient, db_session: AsyncSession):
    token = await _register_and_login(
        client, db_session, "admin_ad_del@test.com", role="admin"
    )
    create = await client.post(
        ADMIN_ADS,
        json={"title": "Delete Me", "is_active": True},
        headers=_auth(token),
    )
    assert create.status_code == 201
    ad_id = create.json()["id"]

    delete = await client.delete(f"{ADMIN_ADS}/{ad_id}", headers=_auth(token))
    assert delete.status_code == 200
    assert delete.json()["deleted"] is True

    # Should be gone from public view
    public = await client.get(PUBLIC_ADS)
    ids = [a["id"] for a in public.json()]
    assert ad_id not in ids

    # But still in admin list (soft-delete)
    admin_list = await client.get(ADMIN_ADS, headers=_auth(token))
    admin_ids  = [a["id"] for a in admin_list.json()]
    assert ad_id in admin_ids
