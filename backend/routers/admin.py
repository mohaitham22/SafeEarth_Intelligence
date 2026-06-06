from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from core.deps import require_admin
from database import get_db
from ml import emdat_lookup
from ml import model_info
from models.user import User
from schemas.ad import AdAdminItem, AdCreate, AdUpdate
from schemas.admin import (
    AdminUsersResponse,
    DispatchPreviewResponse,
    ModelStatsResponse,
    PerClassF1,
    PatchUserRequest,
    SiteStatsResponse,
    AdminUserItem,
)
from services import admin_service, ad_service

# health_router has NO prefix — registered at /api/v1/health in main.py.
health_router = APIRouter(tags=["health"])


@health_router.api_route("/health", methods=["GET", "HEAD"])
async def health_check(request: Request):
    return {
        "status":        "ok",
        "timestamp":     datetime.now(timezone.utc).isoformat(),
        "models_loaded": getattr(request.app.state, "models_loaded", False),
        "rag_loaded":    getattr(request.app.state, "rag_loaded",    False),
    }


# router has prefix="/admin" — registered at /api/v1/admin/... in main.py.
router = APIRouter(prefix="/admin", tags=["admin"])

_SEVEN_FILES = [
    "emdat_stats.json",
    "secondary_disasters.json",
    "seasonal_peaks.json",
    "insurance_ratios.json",
    "trends.json",
    "continent_stats.json",
    "timeseries.json",
]


@router.get("/data-status")
async def data_status(_: User = Depends(require_admin)):
    """Confirms EM-DAT data loaded at startup. Useful on Render to verify JSON files shipped."""
    data_dir = get_settings().data_generated_dir
    return {
        "loaded":              bool(emdat_lookup.EMDAT_STATS),
        "disaster_types":      sorted(emdat_lookup.EMDAT_STATS.get("global", {}).keys()),
        "countries_with_data": len(emdat_lookup.EMDAT_STATS.get("by_country", {})),
        "regions_with_data":   len(emdat_lookup.EMDAT_STATS.get("by_region", {})),
        "files_present":       [f for f in _SEVEN_FILES if (data_dir / f).exists()],
    }


# ── User Management ────────────────────────────────────────────────────────────

@router.get("/users", response_model=AdminUsersResponse)
async def list_users(
    page:        int           = 1,
    page_size:   int           = 20,
    role:        Optional[str] = None,
    is_verified: Optional[bool] = None,
    search:      Optional[str] = None,
    db:          AsyncSession  = Depends(get_db),
    _:           User          = Depends(require_admin),
):
    """Paginated user list with optional role/verified/search filters."""
    return await admin_service.list_users(
        db,
        page=page,
        page_size=page_size,
        role=role,
        is_verified=is_verified,
        search=search,
    )


@router.patch("/users/{user_id}", response_model=AdminUserItem)
async def patch_user(
    user_id: UUID,
    body:    PatchUserRequest,
    db:      AsyncSession = Depends(get_db),
    current: User         = Depends(require_admin),
):
    """Update a user's role and/or is_verified. Cannot change your own role."""
    return await admin_service.update_user(
        db,
        user_id=user_id,
        patch=body,
        acting_user_id=current.id,
    )


# ── Site Stats ─────────────────────────────────────────────────────────────────

@router.get("/stats", response_model=SiteStatsResponse)
async def site_stats(
    db: AsyncSession = Depends(get_db),
    _:  User         = Depends(require_admin),
):
    """Aggregate counts: users, predictions, subscriptions, alerts, payments, email logs."""
    return await admin_service.get_site_stats(db)


# ── Model Stats ────────────────────────────────────────────────────────────────

@router.get("/model-stats", response_model=ModelStatsResponse)
async def model_stats(
    request: Request,
    _:       User = Depends(require_admin),
):
    """ML v4.2 metrics + live pipeline status from app.state."""
    return ModelStatsResponse(
        version       = model_info.MODEL_VERSION,
        macro_f1      = model_info.MACRO_F1,
        weighted_f1   = model_info.WEIGHTED_F1,
        accuracy      = model_info.ACCURACY,
        feature_count = model_info.FEATURE_COUNT,
        ensemble      = model_info.ENSEMBLE,
        per_class_f1  = [PerClassF1(**entry) for entry in model_info.PER_CLASS_F1],
        models_loaded = getattr(request.app.state, "models_loaded", False),
        rag_loaded    = getattr(request.app.state, "rag_loaded",    False),
    )


# ── Dispatch Preview ───────────────────────────────────────────────────────────

@router.get("/alerts/dispatch-preview", response_model=DispatchPreviewResponse)
async def dispatch_preview(
    db: AsyncSession = Depends(get_db),
    _:  User         = Depends(require_admin),
):
    """Dry-run: how many active subscriptions and premium users exist right now."""
    return await admin_service.get_dispatch_preview(db)


# ── Studio: Ads CRUD ──────────────────────────────────────────────────────────

@router.get("/ads", response_model=list[AdAdminItem])
async def list_all_ads(
    db: AsyncSession = Depends(get_db),
    _:  User         = Depends(require_admin),
):
    """All ads (including inactive) for the Studio editor."""
    ads = await ad_service.list_all_ads(db)
    return [AdAdminItem.model_validate(a) for a in ads]


@router.post("/ads", response_model=AdAdminItem, status_code=201)
async def create_ad(
    body: AdCreate,
    db:   AsyncSession = Depends(get_db),
    _:    User         = Depends(require_admin),
):
    """Create a new ad."""
    ad = await ad_service.create_ad(db, body=body)
    return AdAdminItem.model_validate(ad)


@router.patch("/ads/{ad_id}", response_model=AdAdminItem)
async def update_ad(
    ad_id: UUID,
    body:  AdUpdate,
    db:    AsyncSession = Depends(get_db),
    _:     User         = Depends(require_admin),
):
    """Update any subset of ad fields."""
    ad = await ad_service.update_ad(db, ad_id=ad_id, body=body)
    return AdAdminItem.model_validate(ad)


@router.post("/ads/{ad_id}/image", response_model=AdAdminItem)
async def upload_ad_image(
    ad_id:   UUID,
    request: Request,
    upload:  UploadFile = File(...),
    db:      AsyncSession = Depends(get_db),
    _:       User         = Depends(require_admin),
):
    """Upload an image for an ad. Saves to static/ads/, updates image_url."""
    settings     = get_settings()
    api_base_url = settings.api_base_url if hasattr(settings, "api_base_url") else str(request.base_url).rstrip("/")
    ad = await ad_service.upload_ad_image(db, ad_id=ad_id, upload=upload, api_base_url=api_base_url)
    return AdAdminItem.model_validate(ad)


@router.delete("/ads/{ad_id}")
async def delete_ad(
    ad_id: UUID,
    db:    AsyncSession = Depends(get_db),
    _:     User         = Depends(require_admin),
):
    """Soft-delete an ad (sets is_active=False)."""
    await ad_service.deactivate_ad(db, ad_id=ad_id)
    return {"deleted": True}
