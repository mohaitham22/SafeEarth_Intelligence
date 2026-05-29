"""
Subscription business logic.

Enforces per-role limits server-side:
  - Subscriber (free): max 3 active subscriptions
  - Premium:           max 10 active subscriptions

Token generation for one-click unsubscribe (no login required):
  Every subscription gets a unique secrets.token_urlsafe(32) at creation time.
  DELETE /subscriptions/{token} validates the token without requiring auth.
"""
from __future__ import annotations

import secrets
import uuid

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.enums import AlertFrequency, UserRole
from models.subscription import Subscription
from models.user import User


MAX_SUBSCRIPTIONS: dict[str, int] = {
    UserRole.subscriber.value: 3,
    UserRole.premium.value: 10,
    UserRole.admin.value: 10,
}


async def create_subscription(
    *,
    db: AsyncSession,
    user: User,
    region_name: str,
    latitude: float,
    longitude: float,
    alert_frequency: AlertFrequency = AlertFrequency.weekly,
) -> Subscription:
    role_val = user.role.value if hasattr(user.role, "value") else user.role
    limit = MAX_SUBSCRIPTIONS.get(role_val, 3)

    active_count_result = await db.execute(
        select(func.count()).where(
            Subscription.user_id == user.id,
            Subscription.is_active.is_(True),
        )
    )
    active_count = active_count_result.scalar_one()

    if active_count >= limit:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Subscription limit reached ({limit} active). "
                "Upgrade to Premium for up to 10 subscriptions."
            ),
        )

    subscription = Subscription(
        id=uuid.uuid4(),
        user_id=user.id,
        region_name=region_name,
        latitude=latitude,
        longitude=longitude,
        alert_frequency=alert_frequency,
        is_active=True,
        unsubscribe_token=secrets.token_urlsafe(32),
    )
    db.add(subscription)
    await db.flush()
    return subscription


async def list_subscriptions(
    *,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[Subscription]:
    result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == user_id, Subscription.is_active.is_(True))
        .order_by(Subscription.created_at.desc())
    )
    return list(result.scalars().all())


async def deactivate_by_token(
    *,
    db: AsyncSession,
    token: str,
) -> Subscription:
    result = await db.execute(
        select(Subscription).where(Subscription.unsubscribe_token == token)
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        raise HTTPException(
            status_code=404,
            detail="Unsubscribe link is invalid or already used.",
        )
    if not subscription.is_active:
        # Idempotent — one-click unsubscribe links may be clicked more than once.
        return subscription
    subscription.is_active = False
    await db.flush()
    return subscription


async def deactivate_by_id(
    *,
    db: AsyncSession,
    subscription_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Subscription:
    result = await db.execute(
        select(Subscription).where(
            Subscription.id == subscription_id,
            Subscription.user_id == user_id,
        )
    )
    subscription = result.scalar_one_or_none()
    if subscription is None:
        raise HTTPException(status_code=404, detail="Subscription not found.")
    if not subscription.is_active:
        raise HTTPException(status_code=409, detail="Subscription is already inactive.")
    subscription.is_active = False
    await db.flush()
    return subscription
