from __future__ import annotations

import io
import uuid
from datetime import timezone
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import require_premium, require_subscriber
from database import get_db
from models.prediction import Prediction
from models.user import User
from schemas.prediction import (
    ClassifyRequest,
    ClassifyResponse,
    ForecastDayResponse,
    ForecastRequest,
    ImpactRequest,
    ImpactResponse,
    PredictRequest,
    PredictionHistoryItem,
    PredictionHistoryResponse,
    PredictionResponse,
)
from services import alert_service, pdf_service, predictor_service

router  = APIRouter(prefix="/predictions", tags=["predictions"])
limiter = Limiter(key_func=get_remote_address)

# Subscriber-or-above guard now lives in core/deps.py (require_subscriber) — the
# single source of truth, built on core/permissions.py.


# ── POST /predictions/predict ─────────────────────────────────────────────────

@router.post("/predict", response_model=PredictionResponse, status_code=status.HTTP_200_OK)
@limiter.limit("60/minute")
async def predict(
    request: Request,
    body: PredictRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_subscriber),
    db: AsyncSession    = Depends(get_db),
):
    result = await predictor_service.run_prediction_for_request(
        latitude      = body.latitude,
        longitude     = body.longitude,
        region_name   = body.region_name,
        country       = body.country,
        continent     = body.continent,
        disaster_type = body.disaster_type,
        season        = body.season,
        user_id       = current_user.id,
        db            = db,
    )

    # Critical severity -> fan out alerts in the background (Phase 6 stub).
    # Never block the response on alert dispatch.
    if result.get("severity_level") == "Critical":
        background_tasks.add_task(
            alert_service.dispatch_critical_alert,
            prediction_id = result["id"],
            user_id       = current_user.id,
            disaster_type = result["disaster_type"],
            severity      = result["severity_level"],
            region_name   = body.region_name,
        )

    return result


# ── POST /predictions/forecast-30d ───────────────────────────────────────────

@router.post("/forecast-30d", response_model=List[ForecastDayResponse], status_code=status.HTTP_200_OK)
@limiter.limit("8/hour")
async def forecast_30d(
    request: Request,
    body: ForecastRequest,
    current_user: User = Depends(require_subscriber),
    db: AsyncSession    = Depends(get_db),
):
    results = await predictor_service.run_forecast_30d(
        latitude      = body.latitude,
        longitude     = body.longitude,
        region_name   = body.region_name,
        country       = body.country,
        continent     = body.continent,
        disaster_type = body.disaster_type,
        user_id       = current_user.id,
        db            = db,
        force_refresh = body.force_refresh,
    )
    return results


# ── POST /predictions/classify ────────────────────────────────────────────────

@router.post("/classify", response_model=ClassifyResponse, status_code=status.HTTP_200_OK)
@limiter.limit("60/minute")
async def classify(
    request: Request,
    body: ClassifyRequest,
    current_user: User = Depends(require_subscriber),
):
    """Return ranked probabilities for all 8 disaster types. Does not save to DB."""
    result = predictor_service.run_classify(
        latitude  = body.latitude,
        longitude = body.longitude,
        continent = body.continent,
        country   = body.country,
        year      = body.year,
        season    = body.season,
        magnitude = body.magnitude,
    )
    return result


# ── POST /predictions/impact ───────────────────────────────────────────────────

@router.post("/impact", response_model=ImpactResponse, status_code=status.HTTP_200_OK)
@limiter.limit("60/minute")
async def impact(
    request: Request,
    body: ImpactRequest,
    current_user: User = Depends(require_subscriber),
):
    """Return impact estimates for the most likely disaster type. Does not save to DB."""
    result = predictor_service.run_impact(
        latitude    = body.latitude,
        longitude   = body.longitude,
        continent   = body.continent,
        year        = body.year,
        season      = body.season,
        region_name = body.region_name,
        country     = body.country,
    )
    return result


# ── GET /predictions/history ──────────────────────────────────────────────────

@router.get("/history", response_model=PredictionHistoryResponse)
async def prediction_history(
    page: int = 1,
    page_size: int = 10,
    current_user: User = Depends(require_subscriber),
    db: AsyncSession    = Depends(get_db),
):
    if page < 1:
        page = 1
    page_size = min(page_size, 100)
    offset = (page - 1) * page_size

    count_q = await db.execute(
        select(func.count(Prediction.id))
        .where(
            Prediction.user_id == current_user.id,
            Prediction.forecast_batch_id.is_(None),  # exclude forecast rows
        )
    )
    total = count_q.scalar_one()

    rows_q = await db.execute(
        select(Prediction)
        .where(
            Prediction.user_id == current_user.id,
            Prediction.forecast_batch_id.is_(None),
        )
        .order_by(Prediction.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = rows_q.scalars().all()

    return PredictionHistoryResponse(
        items=[PredictionHistoryItem.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── GET /predictions/forecast-30d/pdf ────────────────────────────────────────

@router.get("/forecast-30d/pdf")
async def forecast_30d_pdf(
    current_user: User = Depends(require_premium),
    db: AsyncSession    = Depends(get_db),
):
    """Download the most recent 30-day forecast batch as a PDF (Premium only)."""
    days = await predictor_service.get_latest_forecast_days(
        db=db, user_id=current_user.id
    )
    if not days:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No forecast found. Run a 30-day forecast first.",
        )

    batch_id   = days[0].forecast_batch_id
    region_name = days[0].region_name if days else None
    pdf_bytes = pdf_service.generate_forecast_pdf(days, current_user.full_name, region_name)

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=forecast_{batch_id}.pdf"},
    )


# ── GET /predictions/{id}/pdf ─────────────────────────────────────────────────

@router.get("/{prediction_id}/pdf")
async def prediction_pdf(
    prediction_id: uuid.UUID,
    current_user: User = Depends(require_premium),
    db: AsyncSession    = Depends(get_db),
):
    """Download a single prediction as a PDF report (Premium only)."""
    result = await db.execute(
        select(Prediction).where(Prediction.id == prediction_id)
    )
    row = result.scalar_one_or_none()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction not found")
    if row.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    pdf_bytes = pdf_service.generate_prediction_pdf(row, current_user.full_name)

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=prediction_{prediction_id}.pdf"},
    )


# ── GET /predictions/{id} ─────────────────────────────────────────────────────

@router.get("/{prediction_id}", response_model=PredictionResponse)
async def get_prediction(
    prediction_id: uuid.UUID,
    current_user: User = Depends(require_subscriber),
    db: AsyncSession    = Depends(get_db),
):
    result = await db.execute(
        select(Prediction).where(
            Prediction.id      == prediction_id,
            Prediction.user_id == current_user.id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction not found")

    return {
        "id":                          row.id,
        "disaster_type":               row.disaster_type,
        "probability_score":           row.probability_score,
        "severity_level":              row.severity_level.value if row.severity_level else None,
        "risk_score":                  row.risk_score,
        "estimated_deaths":            row.estimated_deaths,
        "estimated_injuries":          row.estimated_injuries,
        "estimated_affected":          row.estimated_affected,
        "estimated_damage_usd":        row.estimated_damage_usd,
        "uninsured_loss_usd":          row.uninsured_loss_usd,
        "shap_explanation":            row.shap_explanation or [],
        "secondary_disaster_warning":  row.secondary_disaster_warning,
        "seasonal_peak_months":        row.seasonal_peak_months or [],
        "data_quality":                row.data_quality.value if row.data_quality else "full",
        "data_source":                 "global",
        "country_used":                None,
        "n_events":                    0,
        "recommendations":             [],
        "model_version":               row.model_version,
        "created_at":                  row.created_at,
    }
