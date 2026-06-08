"""
backend/routers/egypt_predictions.py

Monthly Egypt disaster-risk predictions for an n8n workflow that runs on the 1st
of every month: it pre-flights GET /api/egypt-predictions/health, then calls
GET /api/egypt-predictions?days=30, splits out data.predictions, filters
riskLevel == "High", and exports a CSV.

Registered WITHOUT the /api/v1 prefix in main.py because the n8n contract calls
the bare /api/egypt-predictions paths. The router stays thin — all ML/RAG work
lives in services/egypt_prediction_service.py.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services import egypt_prediction_service

router = APIRouter(tags=["egypt-predictions"])


@router.get("/api/egypt-predictions")
async def get_egypt_predictions(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Predictions for every day of the CURRENT calendar month.

    The `days` query param is accepted for n8n compatibility but does NOT affect
    the date range — the response always spans the full current month (1st → last
    day), per the agreed contract.

    Response shape (n8n's Split Out node reads `data.predictions`):
        {"data": {"predictions": [ {...one object per day...} ]}}
    """
    predictions = await egypt_prediction_service.generate_month_predictions(db=db)
    return {"data": {"predictions": predictions}}


@router.get("/api/egypt-predictions/health")
async def egypt_predictions_health():
    """Pre-flight check called by n8n before the main endpoint."""
    today = date.today()
    return {"status": "ok", "month": today.strftime("%Y-%m")}
