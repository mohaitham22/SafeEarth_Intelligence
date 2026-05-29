"""
GET /recommendations — public route, calls recommendation_service only.

Logic-free per CLAUDE.md ("Business logic lives in /services/").
The router validates query params, runs the optional personalisation check,
and shapes the response. RAG/fallback orchestration lives in the service.
"""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_optional_user
from database import get_db
from models.alert import Alert
from models.subscription import Subscription
from models.user import User
from schemas.recommendation import RecommendationQuery, RecommendationResponse
from services import recommendation_service

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("", response_model=RecommendationResponse)
async def get_recommendations(
    query:        Annotated[RecommendationQuery, Query()],
    db:           Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[Optional[User], Depends(get_optional_user)],
) -> RecommendationResponse:
    items = await recommendation_service.get_recommendations(
        disaster_type = query.disaster_type,
        severity      = query.severity,
        region_name   = query.region_name,
        db            = db,
    )

    notice = await _personalisation_notice(
        current_user  = current_user,
        disaster_type = query.disaster_type,
        region_name   = query.region_name,
        db            = db,
    )

    return RecommendationResponse(items=items, personalisation_notice=notice)


async def _personalisation_notice(
    *,
    current_user:  Optional[User],
    disaster_type: str,
    region_name:   str,
    db:            AsyncSession,
) -> Optional[str]:
    """Return a notice string if the user has a prior alert for the same
    (disaster_type, region_name). Guests always get None."""
    if current_user is None:
        return None

    stmt = (
        select(Alert.id)
        .join(Subscription, Alert.subscription_id == Subscription.id)
        .where(
            Alert.user_id          == current_user.id,
            Alert.disaster_type    == disaster_type,
            Subscription.region_name == region_name,
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is None:
        return None

    return (
        f"You were previously warned about a {disaster_type} risk in {region_name}. "
        f"Review the recommendations below carefully."
    )
