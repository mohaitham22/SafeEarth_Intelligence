from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.alert import Alert
from models.payment import Payment
from models.prediction import Prediction
from models.premium_email_log import PremiumEmailLog
from models.subscription import Subscription
from models.user import User
from models.enums import AlertStatus, PaymentStatus, UserRole
from schemas.admin import (
    AdminUserItem,
    AdminUsersResponse,
    DispatchPreviewResponse,
    SiteStatsResponse,
    UserStats,
    UserCountsByRole,
    PredictionStats,
    SubscriptionStats,
    AlertStats,
    PaymentStats,
    EmailLogStats,
)


async def list_users(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    role: Optional[str] = None,
    is_verified: Optional[bool] = None,
    search: Optional[str] = None,
) -> AdminUsersResponse:
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    if is_verified is not None:
        stmt = stmt.where(User.is_verified == is_verified)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            User.email.ilike(pattern) | User.full_name.ilike(pattern)
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total: int = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(stmt)).scalars().all()

    # Fetch latest payment expiry per user for the premium_expires_at field
    user_ids = [u.id for u in rows]
    expiry_map: dict[UUID, Optional[datetime]] = {}
    if user_ids:
        pay_stmt = (
            select(Payment.user_id, func.max(Payment.premium_expires_at))
            .where(Payment.user_id.in_(user_ids))
            .where(Payment.status == PaymentStatus.succeeded)
            .group_by(Payment.user_id)
        )
        for uid, exp in (await db.execute(pay_stmt)).all():
            expiry_map[uid] = exp

    items = []
    for u in rows:
        items.append(
            AdminUserItem(
                id=u.id,
                email=u.email,
                full_name=u.full_name,
                role=u.role.value,
                is_verified=u.is_verified,
                premium_expires_at=expiry_map.get(u.id),
                created_at=u.created_at,
            )
        )

    return AdminUsersResponse(items=items, total=total, page=page, page_size=page_size)


async def update_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    patch: "PatchUserRequest",  # type: ignore[name-defined]
    acting_user_id: UUID,
) -> AdminUserItem:
    from schemas.admin import PatchUserRequest  # local to avoid circular at module load

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    if user_id == acting_user_id:
        raise HTTPException(status_code=403, detail="Cannot change your own role.")

    if patch.role is not None:
        try:
            user.role = UserRole(patch.role)
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid role '{patch.role}'.")
    if patch.is_verified is not None:
        user.is_verified = patch.is_verified

    await db.commit()
    await db.refresh(user)

    # Fetch latest expiry
    pay_stmt = (
        select(func.max(Payment.premium_expires_at))
        .where(Payment.user_id == user.id)
        .where(Payment.status == PaymentStatus.succeeded)
    )
    premium_expires_at = (await db.execute(pay_stmt)).scalar_one_or_none()

    return AdminUserItem(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.value,
        is_verified=user.is_verified,
        premium_expires_at=premium_expires_at,
        created_at=user.created_at,
    )


async def get_site_stats(db: AsyncSession) -> SiteStatsResponse:
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # --- Users ---
    total_users = (await db.execute(select(func.count(User.id)))).scalar_one()
    verified_users = (
        await db.execute(select(func.count(User.id)).where(User.is_verified.is_(True)))
    ).scalar_one()

    role_rows = (
        await db.execute(select(User.role, func.count(User.id)).group_by(User.role))
    ).all()
    by_role = UserCountsByRole()
    for role, cnt in role_rows:
        if role == UserRole.subscriber:
            by_role.subscriber = cnt
        elif role == UserRole.premium:
            by_role.premium = cnt
        elif role == UserRole.admin:
            by_role.admin = cnt

    # --- Predictions ---
    total_preds = (await db.execute(select(func.count(Prediction.id)))).scalar_one()
    forecast_preds = (
        await db.execute(
            select(func.count(Prediction.id)).where(Prediction.forecast_batch_id.isnot(None))
        )
    ).scalar_one()
    recent_preds = (
        await db.execute(
            select(func.count(Prediction.id)).where(Prediction.created_at >= week_ago)
        )
    ).scalar_one()

    # --- Subscriptions ---
    active_subs = (
        await db.execute(select(func.count(Subscription.id)).where(Subscription.is_active.is_(True)))
    ).scalar_one()

    # --- Alerts ---
    total_alerts = (
        await db.execute(
            select(func.count(Alert.id)).where(Alert.status == AlertStatus.sent)
        )
    ).scalar_one()
    recent_alerts = (
        await db.execute(
            select(func.count(Alert.id))
            .where(Alert.status == AlertStatus.sent)
            .where(Alert.sent_at >= week_ago)
        )
    ).scalar_one()

    # --- Payments ---
    pay_rows = (
        await db.execute(
            select(func.count(Payment.id), func.sum(Payment.amount_usd))
            .where(Payment.status == PaymentStatus.succeeded)
        )
    ).one()
    succeeded_payments = pay_rows[0] or 0
    revenue = Decimal(pay_rows[1] or 0)

    # --- Email logs ---
    total_logs = (await db.execute(select(func.count(PremiumEmailLog.id)))).scalar_one()

    return SiteStatsResponse(
        users=UserStats(total=total_users, verified=verified_users, by_role=by_role),
        predictions=PredictionStats(
            total=total_preds, forecasts=forecast_preds, last_7_days=recent_preds
        ),
        subscriptions=SubscriptionStats(active=active_subs),
        alerts=AlertStats(total_sent=total_alerts, last_7_days=recent_alerts),
        payments=PaymentStats(
            total_succeeded=succeeded_payments,
            revenue_usd=f"{revenue:.2f}",
        ),
        email_logs=EmailLogStats(total=total_logs),
    )


async def get_dispatch_preview(db: AsyncSession) -> DispatchPreviewResponse:
    active_subs = (
        await db.execute(
            select(func.count(Subscription.id)).where(Subscription.is_active.is_(True))
        )
    ).scalar_one()

    premium_users = (
        await db.execute(
            select(func.count(User.id)).where(
                User.role.in_([UserRole.premium, UserRole.admin])
            )
        )
    ).scalar_one()

    return DispatchPreviewResponse(
        active_subscriptions=active_subs,
        premium_users=premium_users,
    )
