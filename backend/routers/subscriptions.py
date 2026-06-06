from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_current_user
from database import get_db
from models.user import User
from schemas.subscription import (
    SubscriptionCreate,
    SubscriptionListItem,
    SubscriptionLookupResponse,
    SubscriptionResponse,
)
from services import subscription_service

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.post(
    "",
    response_model=SubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_subscription(
    body: SubscriptionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    subscription = await subscription_service.create_subscription(
        db=db,
        user=current_user,
        region_name=body.region_name,
        latitude=body.latitude,
        longitude=body.longitude,
        alert_frequency=body.alert_frequency,
    )
    await db.commit()
    await db.refresh(subscription)
    return subscription


@router.get(
    "",
    response_model=list[SubscriptionListItem],
)
async def list_subscriptions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await subscription_service.list_subscriptions(db=db, user_id=current_user.id)


@router.get(
    "/lookup/{token}",
    response_model=SubscriptionLookupResponse,
)
async def lookup_by_token(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Public, read-only lookup by unsubscribe token — no side effects.

    Lets the email unsubscribe page name the region and show whether it is still
    active so the user can confirm before the actual DELETE. Distinct path from
    DELETE /{token} and GET "" — no wildcard shadowing.
    """
    subscription = await subscription_service.get_by_token(db=db, token=token)
    if subscription is None:
        raise HTTPException(
            status_code=404,
            detail="Unsubscribe link is invalid or already used.",
        )
    return SubscriptionLookupResponse(
        region_name=subscription.region_name,
        is_active=subscription.is_active,
    )


@router.delete(
    "/{token}",
    status_code=status.HTTP_200_OK,
)
async def unsubscribe_by_token(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """One-click unsubscribe — no authentication required. Token comes from the email link."""
    subscription = await subscription_service.deactivate_by_token(db=db, token=token)
    await db.commit()
    return {"status": "unsubscribed", "region_name": subscription.region_name}
