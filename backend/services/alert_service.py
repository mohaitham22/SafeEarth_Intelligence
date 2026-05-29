"""
Alert fan-out business logic (Phase 6).

Two dispatch paths:
  dispatch_critical_alert — called via BackgroundTasks when /predict returns Critical.
      Creates its own DB session (request session is gone). Emails awaited inline
      (we're already in background, nothing to block).

  dispatch_alerts — called from POST /alerts/dispatch (n8n or admin manual trigger).
      Uses the request's shared DB session. Alert rows committed before returning;
      Premium emails scheduled as additional BackgroundTasks so the HTTP response
      is not delayed by network calls.

Fan-out rule (both paths):
  Free Subscriber → in-app Alert row only. No email.
  Premium / Admin  → Alert row + Resend HTML email + PremiumEmailLog row.

Resilience: per-subscription errors are caught, logged, and skipped.
The whole fan-out never aborts because one user's email failed.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import BackgroundTasks
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import AsyncSessionLocal
from models.alert import Alert
from models.enums import (
    AlertFrequency,
    AlertStatus,
    AlertType,
    EmailStatus,
    EmailType,
    SeverityLevel,
)
from models.premium_email_log import PremiumEmailLog
from models.subscription import Subscription
from services import email_service

logger = logging.getLogger(__name__)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _parse_severity(severity: str) -> Optional[SeverityLevel]:
    try:
        return SeverityLevel(severity)
    except ValueError:
        logger.warning("dispatch: unknown severity string '%s'", severity)
        return None


def _build_message(
    disaster_type: Optional[str],
    severity: Optional[str],
    region_name: str,
) -> str:
    dtype = disaster_type or "disaster"
    sev   = severity or ""
    return f"{sev} {dtype} risk detected in {region_name}. Review your safety plan.".strip()


async def _send_email_and_log(
    *,
    db: AsyncSession,
    user,
    subscription: Subscription,
    alert: Alert,
    alert_type: AlertType,
    disaster_type: Optional[str],
    severity_level: Optional[SeverityLevel],
) -> None:
    """Send a Resend email and insert a PremiumEmailLog row — all in the SAME session.

    Used by dispatch_critical_alert (already in background, so awaiting email is fine).
    Any email failure sets the log status to 'failed' but never raises.
    """
    email_type  = (
        EmailType.immediate_high_risk
        if alert_type == AlertType.high_risk_immediate
        else EmailType.weekly_digest_premium
    )
    severity_str = severity_level.value if severity_level else ""
    disaster_str = disaster_type or "disaster"
    subject = f"[SafeEarth Alert] {severity_str} {disaster_str} risk — take action now"

    context = {
        "full_name":         user.full_name or "",
        "disaster_type":     disaster_str,
        "severity_level":    severity_str,
        "region_name":       subscription.region_name,
        "risk_score":        0,
        "unsubscribe_token": subscription.unsubscribe_token,
    }

    try:
        message_id   = await email_service.send_premium_alert_email(user.email, context)
        email_status = EmailStatus.sent
    except Exception as exc:
        logger.error("Premium email send failed for user %s: %s", user.id, exc)
        message_id   = None
        email_status = EmailStatus.failed

    log = PremiumEmailLog(
        id                = uuid.uuid4(),
        user_id           = user.id,
        alert_id          = alert.id,
        resend_message_id = message_id,
        email_type        = email_type,
        subject           = subject,
        status            = email_status,
    )
    db.add(log)
    await db.flush()


async def _send_premium_email_background(
    *,
    user_id:           uuid.UUID,
    alert_id:          uuid.UUID,
    email:             str,
    full_name:         Optional[str],
    unsubscribe_token: str,
    region_name:       str,
    alert_type:        AlertType,
    disaster_type:     Optional[str],
    severity_level:    Optional[SeverityLevel],
) -> None:
    """BackgroundTask: send Resend email + insert PremiumEmailLog with its own DB session.

    Used by dispatch_alerts (n8n path) so the HTTP response is not blocked by email sends.
    Creates a fresh AsyncSessionLocal — the request session is still open at this point
    but we must NOT share it across tasks.
    """
    email_type   = (
        EmailType.immediate_high_risk
        if alert_type == AlertType.high_risk_immediate
        else EmailType.weekly_digest_premium
    )
    severity_str = severity_level.value if severity_level else ""
    disaster_str = disaster_type or "disaster"
    subject = f"[SafeEarth Alert] {severity_str} {disaster_str} risk — take action now"

    context = {
        "full_name":         full_name or "",
        "disaster_type":     disaster_str,
        "severity_level":    severity_str,
        "region_name":       region_name,
        "risk_score":        0,
        "unsubscribe_token": unsubscribe_token,
    }

    try:
        message_id   = await email_service.send_premium_alert_email(email, context)
        email_status = EmailStatus.sent
    except Exception as exc:
        logger.error("Background premium email failed for user %s: %s", user_id, exc)
        message_id   = None
        email_status = EmailStatus.failed

    try:
        async with AsyncSessionLocal() as db:
            log = PremiumEmailLog(
                id                = uuid.uuid4(),
                user_id           = user_id,
                alert_id          = alert_id,
                resend_message_id = message_id,
                email_type        = email_type,
                subject           = subject,
                status            = email_status,
            )
            db.add(log)
            await db.commit()
    except Exception as exc:
        logger.error("PremiumEmailLog insert failed for user %s: %s", user_id, exc)


# ── Public API ─────────────────────────────────────────────────────────────────

async def dispatch_critical_alert(
    *,
    prediction_id: uuid.UUID,
    user_id:       Optional[uuid.UUID],
    disaster_type: str,
    severity:      str,
    region_name:   Optional[str] = None,
) -> None:
    """Fan out an immediate high-risk alert to all active subscriptions in the region.

    Called via BackgroundTasks from POST /predictions/predict when severity == Critical.
    Signature is STABLE — do not change it (predictions router depends on this shape).

    Creates its own DB session. Per-subscription errors are logged and skipped;
    the fan-out always completes.
    """
    if region_name is None:
        logger.warning("dispatch_critical_alert: region_name is None — skipping fan-out")
        return

    severity_level = _parse_severity(severity)

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Subscription)
                .options(selectinload(Subscription.user))
                .where(
                    Subscription.is_active.is_(True),
                    Subscription.region_name == region_name,
                )
            )
            subscriptions = result.scalars().all()

            for sub in subscriptions:
                user = sub.user
                try:
                    alert = Alert(
                        id               = uuid.uuid4(),
                        subscription_id  = sub.id,
                        user_id          = sub.user_id,
                        alert_type       = AlertType.high_risk_immediate,
                        disaster_type    = disaster_type,
                        severity_level   = severity_level,
                        message_body     = _build_message(disaster_type, severity, sub.region_name),
                        sent_at          = datetime.now(timezone.utc),
                        status           = AlertStatus.sent,
                    )
                    db.add(alert)
                    await db.flush()

                    role_val = user.role.value if hasattr(user.role, "value") else user.role
                    if role_val in ("premium", "admin"):
                        await _send_email_and_log(
                            db             = db,
                            user           = user,
                            subscription   = sub,
                            alert          = alert,
                            alert_type     = AlertType.high_risk_immediate,
                            disaster_type  = disaster_type,
                            severity_level = severity_level,
                        )

                except Exception as exc:
                    logger.error(
                        "dispatch_critical_alert: sub %s failed: %s", sub.id, exc
                    )

            await db.commit()

    except Exception as exc:
        logger.error("dispatch_critical_alert: session-level failure: %s", exc)


async def dispatch_alerts(
    *,
    db:             AsyncSession,
    background_tasks: BackgroundTasks,
    alert_type:     AlertType,
    region_name:    Optional[str]     = None,
    disaster_type:  Optional[str]     = None,
    severity_level: Optional[SeverityLevel] = None,
) -> int:
    """Fan out alerts to matching active subscriptions (n8n weekly digest or manual admin trigger).

    Alert rows are committed before returning so background email tasks can safely
    reference alert.id. Premium emails are scheduled as BackgroundTasks so the
    HTTP response from POST /alerts/dispatch is not blocked by Resend network calls.

    Returns the number of Alert rows created.
    """
    query = (
        select(Subscription)
        .options(selectinload(Subscription.user))
        .where(Subscription.is_active.is_(True))
    )
    if alert_type == AlertType.weekly_digest:
        query = query.where(Subscription.alert_frequency == AlertFrequency.weekly)
    if region_name:
        query = query.where(Subscription.region_name == region_name)

    result      = await db.execute(query)
    subscriptions = result.scalars().all()

    severity_str = severity_level.value if severity_level else ""
    queued = 0

    for sub in subscriptions:
        user = sub.user
        try:
            alert = Alert(
                id               = uuid.uuid4(),
                subscription_id  = sub.id,
                user_id          = sub.user_id,
                alert_type       = alert_type,
                disaster_type    = disaster_type,
                severity_level   = severity_level,
                message_body     = _build_message(disaster_type, severity_str, sub.region_name),
                sent_at          = datetime.now(timezone.utc),
                status           = AlertStatus.sent,
            )
            db.add(alert)
            await db.flush()

            role_val = user.role.value if hasattr(user.role, "value") else user.role
            if role_val in ("premium", "admin"):
                background_tasks.add_task(
                    _send_premium_email_background,
                    user_id           = user.id,
                    alert_id          = alert.id,
                    email             = user.email,
                    full_name         = user.full_name,
                    unsubscribe_token = sub.unsubscribe_token,
                    region_name       = sub.region_name,
                    alert_type        = alert_type,
                    disaster_type     = disaster_type,
                    severity_level    = severity_level,
                )

            queued += 1

        except Exception as exc:
            logger.error("dispatch_alerts: sub %s failed: %s", sub.id, exc)

    await db.commit()
    return queued


async def get_alert_history(
    *,
    db:        AsyncSession,
    user_id:   uuid.UUID,
    page:      int = 1,
    page_size: int = 10,
) -> tuple[list[Alert], int]:
    """Return paginated alert history for a user, newest first."""
    if page < 1:
        page = 1
    page_size = min(page_size, 100)
    offset    = (page - 1) * page_size

    count_result = await db.execute(
        select(sa_func.count(Alert.id)).where(Alert.user_id == user_id)
    )
    total = count_result.scalar_one()

    rows_result = await db.execute(
        select(Alert)
        .where(Alert.user_id == user_id)
        .order_by(Alert.sent_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = list(rows_result.scalars().all())

    return items, total
