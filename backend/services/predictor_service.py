"""
predictor_service.py — orchestrates ML inference end-to-end.

Call run_prediction_for_request() from the router.
Never import ml.predictor inside a router.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ml import predictor
from ml.predictor import MODEL_VERSION
from models.enums import DataQuality, SeverityLevel
from models.prediction import Prediction
from services import recommendation_service

logger = logging.getLogger("safeearth")


def _str_to_severity(s: str) -> SeverityLevel:
    return {
        "Low":      SeverityLevel.low,
        "Medium":   SeverityLevel.medium,
        "High":     SeverityLevel.high,
        "Critical": SeverityLevel.critical,
    }[s]


async def run_prediction_for_request(
    *,
    latitude:      float,
    longitude:     float,
    region_name:   Optional[str],
    country:       str,
    continent:     str,
    disaster_type: str,
    season:        Union[str, int],
    magnitude:     Optional[float],
    user_id:       Optional[uuid.UUID],
    db:            AsyncSession,
    day_offset:    int = 0,
    forecast_batch_id: Optional[uuid.UUID] = None,
    fetch_recommendations: bool = True,
) -> dict:
    """Run full prediction pipeline and save to DB. Returns complete response dict.

    fetch_recommendations: forecast loop sets this to False to skip 30 RAG calls;
    run_forecast_30d does a single dedup-by-severity enrichment pass afterwards.
    """
    effective_season = season
    if season == 0 or season == "0":
        effective_season = datetime.now(timezone.utc).month

    ml = predictor.predict(
        lat          = latitude,
        lon          = longitude,
        disaster_type= disaster_type,
        magnitude    = magnitude,
        season       = effective_season,
        continent    = continent,
        day_offset   = day_offset,
        country      = country,
        region       = region_name,
    )

    row = Prediction(
        user_id                    = user_id,
        region_name                = region_name,
        latitude                   = latitude,
        longitude                  = longitude,
        disaster_type              = ml["disaster_type"],
        probability_score          = ml["probability_score"],
        severity_level             = _str_to_severity(ml["severity_level"]),
        risk_score                 = ml["risk_score"],
        estimated_deaths           = ml["estimated_deaths"],
        estimated_injuries         = ml["estimated_injuries"],
        estimated_affected         = ml["estimated_affected"],
        estimated_damage_usd       = ml["estimated_damage_usd"],
        uninsured_loss_usd         = ml["uninsured_loss_usd"],
        shap_explanation           = ml["shap_explanation"],
        secondary_disaster_warning = ml["secondary_disaster_warning"],
        seasonal_peak_months       = ml["seasonal_peak_months"],
        data_quality               = DataQuality.full,
        model_version              = MODEL_VERSION,
        forecast_batch_id          = forecast_batch_id,
        forecast_day_offset        = day_offset if forecast_batch_id is not None else None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    recommendations: list[dict] = []
    if fetch_recommendations:
        recommendations = await _safe_get_recommendations(
            disaster_type = ml["disaster_type"],
            severity      = ml["severity_level"],
            region_name   = region_name,
            db            = db,
        )

    return _build_response(row, ml, recommendations)


async def run_forecast_30d(
    *,
    latitude:      float,
    longitude:     float,
    region_name:   Optional[str],
    country:       str,
    continent:     str,
    disaster_type: str,
    user_id:       Optional[uuid.UUID],
    db:            AsyncSession,
    force_refresh: bool = False,
) -> list[dict]:
    """Run 30-day forecast. Checks DB cache (24h) unless force_refresh=True."""

    if not force_refresh and user_id is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        result = await db.execute(
            select(Prediction)
            .where(
                Prediction.user_id          == user_id,
                Prediction.latitude         == latitude,
                Prediction.longitude        == longitude,
                Prediction.disaster_type    == disaster_type,
                Prediction.forecast_batch_id.isnot(None),
                Prediction.created_at       >= cutoff,
            )
            .order_by(Prediction.forecast_day_offset)
            .limit(30)
        )
        cached = result.scalars().all()
        if len(cached) == 30:
            results = [_build_response_minimal(r) for r in cached]
            await _enrich_with_recommendations_by_severity(
                results=results, disaster_type=disaster_type,
                region_name=region_name, db=db,
            )
            return results

    batch_id = uuid.uuid4()
    results  = []

    for day_offset in range(30):
        forecast_date  = datetime.now(timezone.utc) + timedelta(days=day_offset)
        forecast_month = forecast_date.month
        day_result = await run_prediction_for_request(
            latitude      = latitude,
            longitude     = longitude,
            region_name   = region_name,
            country       = country,
            continent     = continent,
            disaster_type = disaster_type,
            season        = forecast_month,
            magnitude     = None,
            user_id       = user_id,
            db            = db,
            day_offset    = day_offset,
            forecast_batch_id     = batch_id,
            fetch_recommendations = False,
        )
        day_result["forecast_day_offset"] = day_offset
        day_result["date"] = forecast_date.date().isoformat()
        results.append(day_result)

    await _enrich_with_recommendations_by_severity(
        results=results, disaster_type=disaster_type,
        region_name=region_name, db=db,
    )
    return results


async def _safe_get_recommendations(
    *,
    disaster_type: str,
    severity:      str,
    region_name:   Optional[str],
    db:            AsyncSession,
) -> list[dict]:
    """Wrap recommendation_service.get_for_prediction so a RAG failure can never
    cause a prediction endpoint to 500 — degrades to [] and logs."""
    try:
        return await recommendation_service.get_for_prediction(
            disaster_type = disaster_type,
            severity      = severity,
            region_name   = region_name or "",
            db            = db,
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "Recommendation fetch failed for (%s, %s, %s) — returning [] so prediction does not 500",
            disaster_type, severity, region_name,
        )
        return []


async def _enrich_with_recommendations_by_severity(
    *,
    results:       list[dict],
    disaster_type: str,
    region_name:   Optional[str],
    db:            AsyncSession,
) -> None:
    """Mutate results in place to populate `recommendations`. Dedupes by severity
    so a 30-day forecast fires at most 4 RAG calls (one per unique severity),
    not 30. Safe to call after either the cached or fresh-loop forecast path."""
    cache: dict[str, list[dict]] = {}
    for r in results:
        sev = r.get("severity_level") or "Medium"
        if sev not in cache:
            cache[sev] = await _safe_get_recommendations(
                disaster_type = disaster_type,
                severity      = sev,
                region_name   = region_name,
                db            = db,
            )
        r["recommendations"] = cache[sev]


def _build_response(row: Prediction, ml: dict, recommendations: list[dict]) -> dict:
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
        "data_source":                 ml.get("data_source", "global"),
        "country_used":                ml.get("country_used"),
        "n_events":                    ml.get("n_events", 0),
        "recommendations":             recommendations,
        "model_version":               row.model_version,
        "created_at":                  row.created_at,
    }


def _build_response_minimal(row: Prediction, recommendations: Optional[list[dict]] = None) -> dict:
    """Build response from a cached Prediction row (no fresh emdat lookup needed).
    Recommendations default to [] — run_forecast_30d enriches them in a batched
    dedup-by-severity pass after building all 30 cached responses."""
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
        "recommendations":             recommendations if recommendations is not None else [],
        "model_version":               row.model_version,
        "created_at":                  row.created_at,
        "forecast_day_offset":         row.forecast_day_offset,
        "date": (
            (row.created_at + timedelta(days=row.forecast_day_offset or 0)).date().isoformat()
        ),
    }


# ── Non-DB inference helpers ──────────────────────────────────────────────────

def run_classify(
    *,
    latitude:  float,
    longitude: float,
    continent: str,
    year:      int,
    season:    Union[str, int] = 0,
    magnitude: Optional[float] = None,
) -> dict:
    """Return ranked probabilities for all 8 disaster types. Never saves to DB."""
    effective_season = season
    if season == 0 or season == "0":
        effective_season = datetime.now(timezone.utc).month
    return predictor.classify_all_types(
        lat       = latitude,
        lon       = longitude,
        magnitude = magnitude,
        season    = effective_season,
        continent = continent,
        year      = year,
    )


def run_impact(
    *,
    latitude:    float,
    longitude:   float,
    continent:   str,
    year:        int,
    season:      Union[str, int] = 0,
    region_name: Optional[str] = None,
    country:     Optional[str] = None,
) -> dict:
    """Return impact estimates (auto-selects top disaster type). Never saves to DB."""
    effective_season = season
    if season == 0 or season == "0":
        effective_season = datetime.now(timezone.utc).month
    return predictor.predict_impact(
        lat       = latitude,
        lon       = longitude,
        season    = effective_season,
        continent = continent,
        year      = year,
        country   = country,
        region    = region_name,
    )
