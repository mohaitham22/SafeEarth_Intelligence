import asyncio
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import AsyncSessionLocal
from models.enums import PaymentStatus, UserRole
from models.payment import Payment
from models.premium_plan import PremiumPlan
from models.subscription import Subscription
from models.user import User
from services.payment_service import get_payment_service

logger = logging.getLogger(__name__)

FREE_SUBSCRIPTION_LIMIT = 3


async def create_checkout(user: User, plan_name: str, db: AsyncSession) -> dict:
    """Create a payment checkout session and record a pending payment row.

    Payments table rule: this is the ONLY place that INSERTs a new payment row.
    handle_webhook_event only UPDATEs existing rows — never inserts.
    """
    result = await db.execute(
        select(PremiumPlan).where(
            PremiumPlan.name == plan_name,
            PremiumPlan.is_active.is_(True),
        )
    )
    plan = result.scalar_one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plan '{plan_name}' not found or not active.",
        )

    svc = get_payment_service()
    checkout = await svc.create_checkout_session(
        user_id=str(user.id),
        plan_id=str(plan.id),
        plan_name=plan.name,
        amount_usd=plan.price_usd,
    )

    settings = get_settings()
    payment = Payment(
        user_id=user.id,
        plan_id=plan.id,
        provider=settings.payment_provider,
        provider_transaction_id=checkout["session_id"],
        amount_usd=plan.price_usd,
        status=PaymentStatus.pending,
    )
    db.add(payment)
    await db.commit()

    logger.info(
        "Checkout created: user=%s plan=%s session_id=%s",
        user.id,
        plan.name,
        checkout["session_id"],
    )
    return {
        "checkout_url": checkout["checkout_url"],
        "session_id": checkout["session_id"],
        "plan_name": plan.name,
    }


async def handle_webhook_event(
    raw_body: bytes,
    signature_header: str,
    db: AsyncSession,
) -> dict:
    """Process an incoming payment webhook.

    Security contract: verify_webhook_signature is called FIRST, before any DB read
    or write. HTTPException 400 from a bad signature propagates directly to the caller.

    Idempotent: duplicate webhook delivery for an already-succeeded payment is silently
    ignored (returns {"received": True}) rather than erroring.

    Payment record rule: only UPDATEs the existing row (created in create_checkout).
    Never inserts a new row here.

    Only "payment.success" events trigger role upgrade. All other event types are
    logged and acknowledged to keep the endpoint forward-compatible with future provider
    events (refund, dispute, etc.) without requiring code changes.
    """
    svc = get_payment_service()
    # HTTPException 400 from bad/missing signature propagates — never caught here.
    event = await svc.verify_webhook_signature(raw_body, signature_header)

    event_type = event.get("type", "")
    logger.info("Webhook received: type=%s", event_type)

    if event_type != "payment.success":
        return {"received": True}

    session_id = event.get("session_id")
    pay_result = await db.execute(
        select(Payment).where(Payment.provider_transaction_id == session_id)
    )
    payment = pay_result.scalar_one_or_none()

    if payment is None:
        # Unknown session — could be a test ping or a duplicate from a failed delivery.
        logger.warning("Webhook: no payment row for session_id=%s — skipped", session_id)
        return {"received": True}

    if payment.status == PaymentStatus.succeeded:
        # Already processed — idempotent duplicate delivery.
        logger.info("Webhook: payment %s already succeeded — skipped", payment.id)
        return {"received": True}

    plan_result = await db.execute(
        select(PremiumPlan).where(PremiumPlan.id == payment.plan_id)
    )
    plan = plan_result.scalar_one()

    now = datetime.now(timezone.utc)
    payment.status = PaymentStatus.succeeded
    payment.premium_activated_at = now
    payment.premium_expires_at = now + timedelta(days=plan.duration_days)

    provider_txn = event.get("provider_transaction_id")
    if provider_txn and provider_txn != session_id:
        payment.provider_transaction_id = provider_txn

    user_result = await db.execute(select(User).where(User.id == payment.user_id))
    user = user_result.scalar_one()
    user.role = UserRole.premium

    await db.commit()

    logger.info(
        "Webhook: user %s upgraded to premium via payment %s (expires %s)",
        user.id,
        payment.id,
        payment.premium_expires_at.date(),
    )
    return {
        "received": True,
        "upgraded": True,
        "user_id": str(user.id),
        "expires_at": payment.premium_expires_at.isoformat(),
    }


async def get_user_payment_history(
    user: User,
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Return paginated payment history for the requesting user (read-only)."""
    offset = (page - 1) * page_size

    count_result = await db.execute(
        select(Payment).where(Payment.user_id == user.id)
    )
    total = len(count_result.scalars().all())

    rows_result = await db.execute(
        select(Payment)
        .where(Payment.user_id == user.id)
        .order_by(Payment.created_at.desc())
        .limit(page_size)
        .offset(offset)
    )
    payments = rows_result.scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "payments": payments,
    }


async def downgrade_expired_premium(db: AsyncSession) -> int:
    """Downgrade users whose premium has expired to subscriber role.

    Keeps payment.premium_expires_at intact for audit trail — never erased.
    Deactivates oldest excess subscriptions (beyond FREE_SUBSCRIPTION_LIMIT of 3).
    Returns count of users downgraded. Idempotent — safe to run repeatedly.
    """
    now = datetime.now(timezone.utc)

    # Subquery: user_ids that still have an active (non-expired) succeeded payment
    active_plan_subq = (
        select(Payment.user_id)
        .where(
            Payment.status == PaymentStatus.succeeded,
            Payment.premium_expires_at > now,
        )
        .scalar_subquery()
    )

    result = await db.execute(
        select(User).where(
            User.role == UserRole.premium,
            ~User.id.in_(active_plan_subq),
        )
    )
    expired_users = result.scalars().all()

    downgraded = 0
    for user in expired_users:
        # Fetch most recent succeeded payment for logging (audit only — not erased)
        pay_q = await db.execute(
            select(Payment)
            .where(
                Payment.user_id == user.id,
                Payment.status == PaymentStatus.succeeded,
            )
            .order_by(Payment.premium_expires_at.desc())
            .limit(1)
        )
        recent_payment = pay_q.scalar_one_or_none()
        expired_at = recent_payment.premium_expires_at if recent_payment else None

        user.role = UserRole.subscriber

        # Deactivate oldest excess active subscriptions (oldest first by created_at)
        subs_result = await db.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user.id,
                Subscription.is_active.is_(True),
            )
            .order_by(Subscription.created_at.asc())
        )
        active_subs = subs_result.scalars().all()

        if len(active_subs) > FREE_SUBSCRIPTION_LIMIT:
            excess_count = len(active_subs) - FREE_SUBSCRIPTION_LIMIT
            for sub in active_subs[:excess_count]:
                sub.is_active = False
            logger.info(
                "Expiry: deactivated %d excess subscriptions for user %s",
                excess_count,
                user.email,
            )

        logger.info(
            "Expiry: downgraded user %s to subscriber (expired_at=%s)",
            user.email,
            expired_at,
        )
        downgraded += 1

    if downgraded:
        await db.commit()

    return downgraded


async def run_expiry_loop() -> None:
    """Run premium expiry check once per 24 hours.

    Started as asyncio.create_task() in FastAPI lifespan.
    Uses its own AsyncSessionLocal session (same pattern as dispatch_critical_alert).
    Catches all exceptions so a DB error never kills the loop.
    """
    while True:
        await asyncio.sleep(86_400)  # sleep FIRST, then check
        try:
            async with AsyncSessionLocal() as db:
                n = await downgrade_expired_premium(db)
                if n:
                    logger.info("Expiry loop: downgraded %d expired premium users", n)
        except Exception:
            logger.exception("Expiry loop: unhandled exception — loop continues")
