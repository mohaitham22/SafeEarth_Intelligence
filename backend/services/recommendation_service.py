"""
recommendation_service.py — orchestrates the runtime RAG pipeline + DB fallback.

Routers and predictor_service call into this module. Never call
rag.recommender or query the recommendations table directly from a router.
"""
from __future__ import annotations

import logging
from typing import get_args

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.enums import SeverityLevel
from models.recommendation import Recommendation
from rag import recommender as rag_recommender
from rag.recommender import GroqUnavailableError, RECOMMENDATION_COUNT
from schemas.recommendation import RecommendationCategory, RecommendationItem

logger = logging.getLogger("safeearth")

# Single source of truth: the order encoded in the RecommendationCategory Literal
CATEGORY_ORDER  = list(get_args(RecommendationCategory))
_CATEGORY_RANK  = {c: i for i, c in enumerate(CATEGORY_ORDER)}

# Same string -> SeverityLevel mapping the predictor service uses (CSV stores
# the capitalised value, members use lowercase names)
_SEVERITY_STR_TO_ENUM: dict[str, SeverityLevel] = {
    "Low":      SeverityLevel.low,
    "Medium":   SeverityLevel.medium,
    "High":     SeverityLevel.high,
    "Critical": SeverityLevel.critical,
}


# ── Public API ────────────────────────────────────────────────────────────────

async def get_recommendations(
    *,
    disaster_type: str,
    severity:      str,
    region_name:   str,
    db:            AsyncSession,
) -> list[RecommendationItem]:
    """Run the RAG pipeline; fall back to the DB on any RAG failure.

    Returns up to RECOMMENDATION_COUNT items, sorted by CATEGORY_ORDER.
    Never re-raises a RAG/Groq failure — those are caught and routed to the
    fallback so the client never sees a 500 caused by Groq.
    """
    try:
        return rag_recommender.get_recommendations(
            disaster_type = disaster_type,
            severity      = severity,
            region_name   = region_name,
        )
    except GroqUnavailableError as exc:
        logger.warning("RAG unavailable, using DB fallback: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected RAG error, using DB fallback: %s", exc, exc_info=True)

    return await _fallback_from_db(disaster_type, severity, db)


async def get_for_prediction(
    *,
    disaster_type: str,
    severity:      str,
    region_name:   str,
    db:            AsyncSession,
) -> list[dict]:
    """Same as get_recommendations() but returns plain dicts for embedding
    in PredictionResponse (`recommendations` field) via model_dump()."""
    items = await get_recommendations(
        disaster_type = disaster_type,
        severity      = severity,
        region_name   = region_name,
        db            = db,
    )
    return [item.model_dump() for item in items]


# ── Private: DB fallback ──────────────────────────────────────────────────────

async def _fallback_from_db(
    disaster_type: str,
    severity:      str,
    db:            AsyncSession,
) -> list[RecommendationItem]:
    """Read static rows from the `recommendations` table keyed by
    (disaster_type, severity_level). Returns up to RECOMMENDATION_COUNT items,
    sorted by CATEGORY_ORDER. Logs a warning if fewer rows exist — never
    fabricates content to reach 6."""
    severity_enum = _SEVERITY_STR_TO_ENUM.get(severity)
    if severity_enum is None:
        logger.warning(
            "Unknown severity %r passed to fallback — returning []", severity
        )
        return []

    stmt = (
        select(Recommendation)
        .where(
            Recommendation.disaster_type  == disaster_type,
            Recommendation.severity_level == severity_enum,
            Recommendation.category.isnot(None),
        )
        .limit(RECOMMENDATION_COUNT)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    items: list[RecommendationItem] = []
    for row in rows:
        if not row.title or not row.body or row.category is None:
            logger.warning("Skipping incomplete fallback row %s", row.id)
            continue
        try:
            items.append(
                RecommendationItem(
                    category = row.category.value,
                    title    = row.title,
                    body     = row.body,
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skipping invalid fallback row %s: %s", row.id, exc)

    if len(items) < RECOMMENDATION_COUNT:
        logger.warning(
            "DB fallback returned %d/%d recommendations for (%s, %s) — seed the table",
            len(items), RECOMMENDATION_COUNT, disaster_type, severity,
        )

    items.sort(key=lambda x: _CATEGORY_RANK.get(x.category, len(CATEGORY_ORDER)))
    return items
