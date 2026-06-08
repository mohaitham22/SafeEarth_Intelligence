"""
egypt_prediction_service.py — monthly Egypt disaster-risk predictions for n8n.

Drives GET /api/egypt-predictions, which an n8n workflow calls on the 1st of each
month, filters for riskLevel == "High", and exports to CSV.

Architecture rules respected (see backend/ml/predictor.py cardinal rules):
  - Uses the already-loaded ML models via predictor.predict_impact() — one call
    runs the XGBoost classifier (argmax type + confidence) AND the impact
    regressors (deaths/injuries/affected/damage) blended with EM-DAT medians.
    Models are NEVER re-instantiated here; load_models() ran at startup.
  - Uses recommendation_service for the safety note (the RAG/Groq pipeline with
    automatic DB fallback) — never touches rag.recommender or the table directly.
  - All logic lives in this service; the router stays thin.
"""
from __future__ import annotations

import calendar
import logging
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from ml import predictor
from services import recommendation_service

logger = logging.getLogger("safeearth")

# Exact EM-DAT country string so predict_impact() hits the country-tier impact
# lookup; continent feeds the classifier's continent feature.
EGYPT_COUNTRY   = "Egypt"
EGYPT_CONTINENT = "Africa"

# Egypt governorate centroids (capital-city coordinates). A fixed in-process
# lookup — NO external geocoding API is ever called. Each day of the month is
# assigned one governorate (cycled), so every prediction object has a real
# region + lat/lon that the classifier actually ran at. Egypt has 27 governorates.
EGYPT_GOVERNORATES: list[dict] = [
    {"region": "Cairo",           "latitude": 30.04, "longitude": 31.24},
    {"region": "Giza",            "latitude": 30.01, "longitude": 31.21},
    {"region": "Alexandria",      "latitude": 31.20, "longitude": 29.92},
    {"region": "Aswan",           "latitude": 24.09, "longitude": 32.90},
    {"region": "Luxor",           "latitude": 25.69, "longitude": 32.64},
    {"region": "Port Said",       "latitude": 31.26, "longitude": 32.30},
    {"region": "Suez",            "latitude": 29.97, "longitude": 32.53},
    {"region": "Ismailia",        "latitude": 30.60, "longitude": 32.27},
    {"region": "Dakahlia",        "latitude": 31.05, "longitude": 31.38},
    {"region": "Sharqia",         "latitude": 30.59, "longitude": 31.50},
    {"region": "Gharbia",         "latitude": 30.79, "longitude": 31.00},
    {"region": "Beheira",         "latitude": 30.85, "longitude": 30.34},
    {"region": "Qena",            "latitude": 26.16, "longitude": 32.72},
    {"region": "Sohag",           "latitude": 26.56, "longitude": 31.70},
    {"region": "Asyut",           "latitude": 27.18, "longitude": 31.18},
    {"region": "Minya",           "latitude": 28.10, "longitude": 30.75},
    {"region": "Faiyum",          "latitude": 29.31, "longitude": 30.84},
    {"region": "Beni Suef",       "latitude": 29.07, "longitude": 31.10},
    {"region": "Matrouh",         "latitude": 31.35, "longitude": 27.23},
    {"region": "Red Sea",         "latitude": 27.26, "longitude": 33.81},
    {"region": "North Sinai",     "latitude": 31.13, "longitude": 33.80},
    {"region": "South Sinai",     "latitude": 28.24, "longitude": 33.62},
    {"region": "Kafr El Sheikh",  "latitude": 31.11, "longitude": 30.94},
    {"region": "Damietta",        "latitude": 31.42, "longitude": 31.81},
    {"region": "Monufia",         "latitude": 30.55, "longitude": 30.99},
    {"region": "Qalyubia",        "latitude": 30.18, "longitude": 31.20},
    {"region": "New Valley",      "latitude": 25.45, "longitude": 30.55},
]

_GENERIC_NOTE = "Monitor official alerts and follow local civil-defense guidance for {dtype}."


def assign_risk_level(confidence: float) -> str:
    """Map a model confidence score to a risk-level label.

    Standalone helper used everywhere a riskLevel is produced (including the
    placeholder rows) so the thresholds can never drift. n8n filters on the exact
    strings "High" / "Medium" / "Low" (case-sensitive).
    """
    if confidence >= 0.75:
        return "High"
    elif confidence >= 0.50:
        return "Medium"
    else:
        return "Low"


def _governorate_for_day(day_index: int) -> dict:
    """Pick a governorate for a day index, cycling through the list."""
    return EGYPT_GOVERNORATES[day_index % len(EGYPT_GOVERNORATES)]


async def _safety_note(
    *,
    disaster_type: str,
    risk_level:    str,
    region:        str,
    db:            AsyncSession,
    cache:         dict[tuple[str, str], str],
) -> str:
    """Return a one-line safety note from the RAG pipeline (Groq → DB fallback).

    Deduped by (disaster_type, risk_level) so a 28–31 day month fires only a
    handful of RAG calls, not 30. Degrade-not-fail: any RAG/DB error yields a
    generic note so a single day's note never breaks the whole response.
    """
    key = (disaster_type, risk_level)
    if key in cache:
        return cache[key]

    note = _GENERIC_NOTE.format(dtype=disaster_type)
    try:
        items = await recommendation_service.get_recommendations(
            disaster_type = disaster_type,
            severity      = risk_level,
            region_name   = region,
            db            = db,
        )
        if items and items[0].body.strip():
            note = items[0].body.strip()
    except Exception:  # noqa: BLE001
        logger.exception(
            "Egypt safetyNote RAG lookup failed for (%s, %s) — using generic note",
            disaster_type, risk_level,
        )

    cache[key] = note
    return note


def _placeholder(day: date, gov: dict) -> dict:
    """Row used when a single day's ML inference fails (never crashes the response)."""
    return {
        "date":               day.isoformat(),
        "disasterType":       "Unknown",
        "riskLevel":          assign_risk_level(0.0),   # "Low"
        "confidenceScore":    0.0,
        "region":             gov["region"],
        "latitude":           gov["latitude"],
        "longitude":          gov["longitude"],
        "estimatedDeaths":    0,
        "estimatedInjuries":  0,
        "estimatedAffected":  0,
        "estimatedDamageUSD": 0.0,
        "safetyNote":         "Prediction unavailable",
    }


async def generate_month_predictions(*, db: AsyncSession) -> list[dict]:
    """One prediction object per day of the CURRENT calendar month.

    Always spans the full current month (start_date .. end_date inclusive),
    independent of the endpoint's `days` query param, per the n8n contract.
    """
    today      = date.today()
    start_date = today.replace(day=1)
    last_day   = calendar.monthrange(today.year, today.month)[1]
    end_date   = today.replace(day=last_day)

    predictions: list[dict] = []
    note_cache:  dict[tuple[str, str], str] = {}

    current   = start_date
    day_index = 0
    while current <= end_date:
        gov = _governorate_for_day(day_index)
        try:
            impact = predictor.predict_impact(
                lat        = gov["latitude"],
                lon        = gov["longitude"],
                season     = current.month,
                continent  = EGYPT_CONTINENT,
                year       = current.year,
                day_offset = day_index,
                country    = EGYPT_COUNTRY,
                region     = gov["region"],
            )

            disaster_type = impact["predicted_disaster_type"]
            confidence    = float(impact["probability"])
            risk_level    = assign_risk_level(confidence)
            # predict_impact returns damage in THOUSANDS USD (DB column units);
            # the API field is labelled USD, so convert to full dollars.
            damage_usd    = float(impact["estimated_damage_usd"]) * 1000.0

            safety_note = await _safety_note(
                disaster_type = disaster_type,
                risk_level    = risk_level,
                region        = gov["region"],
                db            = db,
                cache         = note_cache,
            )

            predictions.append({
                "date":               current.isoformat(),
                "disasterType":       disaster_type,
                "riskLevel":          risk_level,
                "confidenceScore":    round(confidence, 4),
                "region":             gov["region"],
                "latitude":           gov["latitude"],
                "longitude":          gov["longitude"],
                "estimatedDeaths":    int(impact["estimated_deaths"]),
                "estimatedInjuries":  int(impact["estimated_injuries"]),
                "estimatedAffected":  int(impact["estimated_affected"]),
                "estimatedDamageUSD": round(damage_usd, 2),
                "safetyNote":         safety_note,
            })
        except Exception:  # noqa: BLE001
            logger.exception(
                "Egypt prediction failed for %s (%s) — inserting placeholder row",
                current.isoformat(), gov["region"],
            )
            predictions.append(_placeholder(current, gov))

        current   += timedelta(days=1)
        day_index += 1

    return predictions
