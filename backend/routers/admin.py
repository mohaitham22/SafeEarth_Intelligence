from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Request

from config import get_settings
from core.deps import require_admin
from ml import emdat_lookup
from models.user import User

# health_router has NO prefix — registered at /api/v1/health in main.py.
# CLAUDE.md spec: GET /health (public, <200ms, pinged by UptimeRobot every 14 min).
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
    """Debug endpoint — confirms EM-DAT data loaded at startup.
    Useful on Render to verify the generated JSON files shipped correctly."""
    data_dir = get_settings().data_generated_dir
    return {
        "loaded":               bool(emdat_lookup.EMDAT_STATS),
        "disaster_types":       sorted(emdat_lookup.EMDAT_STATS.get("global", {}).keys()),
        "countries_with_data":  len(emdat_lookup.EMDAT_STATS.get("by_country", {})),
        "regions_with_data":    len(emdat_lookup.EMDAT_STATS.get("by_region", {})),
        "files_present":        [f for f in _SEVEN_FILES if (data_dir / f).exists()],
    }


@router.get("/stub")
async def admin_stub():
    # Phase 7: GET /users, PATCH /users/{id}, GET /model-stats, POST /alerts/trigger
    return {"status": "not_implemented", "phase": 7}
