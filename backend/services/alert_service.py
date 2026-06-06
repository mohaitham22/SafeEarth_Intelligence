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

import calendar
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import BackgroundTasks, HTTPException
from schemas.monthly_dispatch import MonthlyDispatchResponse
from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.permissions import Feature, can
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
from models.user import User
from services import email_service, predictor_service

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


def _evaluate_subscription(sub: Subscription) -> Optional[tuple[str, float, str]]:
    """Run the classifier at the subscription's coordinates to get its current risk.

    Returns (disaster_type, probability, severity_str) for the most likely disaster
    at the region right now, or None if the model is unavailable (cold start / tests)
    or anything fails. Degrade-not-fail: callers fall back to a generic alert.

    This is what actually ties a subscribed region to the alerting pipeline — the
    alert reflects the region's own modelled risk, not some other user's prediction.
    """
    try:
        from ml import predictor          # noqa: PLC0415 — loaded once at startup
        from ml.geo import continent_from_latlon  # noqa: PLC0415

        now       = datetime.now(timezone.utc)
        continent = continent_from_latlon(sub.latitude, sub.longitude)
        result    = predictor.classify_all_types(
            lat       = sub.latitude,
            lon       = sub.longitude,
            magnitude = None,
            season    = now.month,
            continent = continent,
            year      = now.year,
        )
        top_type = result["top_type"]
        prob     = float(result["top_probability"])
        return top_type, prob, predictor.probability_to_severity(prob)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "dispatch: risk eval failed for subscription %s (%s) — using fallback",
            getattr(sub, "id", "?"), exc,
        )
        return None


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

                    if can(user, Feature.RECEIVE_EMAIL_ALERTS):
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
    # Frequency routing: weekly digest → weekly subs; immediate dispatch → immediate subs.
    if alert_type == AlertType.weekly_digest:
        query = query.where(Subscription.alert_frequency == AlertFrequency.weekly)
    elif alert_type == AlertType.high_risk_immediate:
        query = query.where(Subscription.alert_frequency == AlertFrequency.immediate)
    if region_name:
        query = query.where(Subscription.region_name == region_name)

    result        = await db.execute(query)
    subscriptions = result.scalars().all()

    queued = 0

    for sub in subscriptions:
        user = sub.user
        try:
            # Tie the alert to THIS region's modelled risk. Degrade-not-fail: if the
            # model is unavailable, fall back to any values the caller supplied.
            evaluated = _evaluate_subscription(sub)
            if evaluated is not None:
                sub_dtype, _prob, sev_str = evaluated
                sub_sev = _parse_severity(sev_str)
            else:
                sub_dtype = disaster_type
                sub_sev   = severity_level

            # Weekly digest always sends (a digest); immediate only fires for genuine
            # High/Critical risk so users aren't pinged with low-risk noise.
            if alert_type == AlertType.high_risk_immediate and sub_sev not in (
                SeverityLevel.high, SeverityLevel.critical
            ):
                continue

            sev_display = sub_sev.value if sub_sev else ""
            alert = Alert(
                id               = uuid.uuid4(),
                subscription_id  = sub.id,
                user_id          = sub.user_id,
                alert_type       = alert_type,
                disaster_type    = sub_dtype,
                severity_level   = sub_sev,
                message_body     = _build_message(sub_dtype, sev_display, sub.region_name),
                sent_at          = datetime.now(timezone.utc),
                status           = AlertStatus.sent,
            )
            db.add(alert)
            await db.flush()

            if can(user, Feature.RECEIVE_EMAIL_ALERTS):
                background_tasks.add_task(
                    _send_premium_email_background,
                    user_id           = user.id,
                    alert_id          = alert.id,
                    email             = user.email,
                    full_name         = user.full_name,
                    unsubscribe_token = sub.unsubscribe_token,
                    region_name       = sub.region_name,
                    alert_type        = alert_type,
                    disaster_type     = sub_dtype,
                    severity_level    = sub_sev,
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


async def _send_monthly_digest_background(
    *,
    user_id:    uuid.UUID,
    email:      str,
    full_name:  Optional[str],
    period:     str,            # "YYYY-MM"
    alert_rows: list[dict],     # serialisable snapshots — not ORM objects
) -> None:
    """BackgroundTask: send monthly digest email + insert PremiumEmailLog with own session."""
    context = {
        "full_name":   full_name or "",
        "period":      period,
        "alert_rows":  alert_rows,  # [{date, region, disaster_type, severity, message}]
    }
    try:
        message_id   = await email_service.send_monthly_digest_email(email, context)
        email_status = EmailStatus.sent
    except Exception as exc:  # noqa: BLE001
        logger.error("Monthly digest email failed for user %s: %s", user_id, exc)
        message_id   = None
        email_status = EmailStatus.failed

    try:
        async with AsyncSessionLocal() as db:
            log = PremiumEmailLog(
                id                = uuid.uuid4(),
                user_id           = user_id,
                alert_id          = None,
                resend_message_id = message_id,
                email_type        = EmailType.custom,
                subject           = f"[SafeEarth] Your alert summary for {period}",
                status            = email_status,
            )
            db.add(log)
            await db.commit()
    except Exception as exc:
        logger.error("PremiumEmailLog insert failed for monthly digest user %s: %s", user_id, exc)


async def dispatch_monthly_digest(
    *,
    year:             Optional[int],
    month:            Optional[int],
    db:               AsyncSession,
    background_tasks: BackgroundTasks,
) -> MonthlyDispatchResponse:
    """Fan out a monthly digest email to every premium user who had ≥1 alert that month.

    Called from POST /alerts/monthly-dispatch (require_dispatch_auth).
    Defaults to the previous calendar month when year/month are omitted.
    Raises HTTP 400 for future months.
    Each email is a BackgroundTask — the HTTP response is immediate.
    """
    now = datetime.now(timezone.utc)

    if year is None or month is None:
        # Default: previous calendar month
        if now.month == 1:
            target_year, target_month = now.year - 1, 12
        else:
            target_year, target_month = now.year, now.month - 1
    else:
        target_year, target_month = year, month

    # Reject future months
    if (target_year, target_month) > (now.year, now.month):
        raise HTTPException(status_code=400, detail="Cannot dispatch for a future month.")
    if (target_year, target_month) == (now.year, now.month):
        # Allow current month (partial digest is fine)
        pass

    period = f"{target_year:04d}-{target_month:02d}"
    _, last_day = calendar.monthrange(target_year, target_month)

    month_start = datetime(target_year, target_month, 1, tzinfo=timezone.utc)
    month_end   = datetime(target_year, target_month, last_day, 23, 59, 59, tzinfo=timezone.utc)

    # Pull all sent alerts in the window, joined to user for role/email
    stmt = (
        select(Alert, User)
        .join(User, Alert.user_id == User.id)
        .where(
            Alert.status == AlertStatus.sent,
            Alert.sent_at >= month_start,
            Alert.sent_at <= month_end,
        )
        .order_by(Alert.user_id, Alert.sent_at.asc())
    )
    rows = (await db.execute(stmt)).all()

    # Group by user — only premium/admin users get the digest email
    # user_meta: user_id → User; user_alert_rows: user_id → list[dict]
    user_meta:       dict[uuid.UUID, User]       = {}
    user_alert_rows: dict[uuid.UUID, list[dict]] = {}
    for alert, user in rows:
        if not can(user, Feature.RECEIVE_EMAIL_ALERTS):
            continue
        if user.id not in user_meta:
            user_meta[user.id]       = user
            user_alert_rows[user.id] = []
        # Resolve region_name by querying if needed — use the alert's message as fallback
        region_name = ""
        if alert.subscription_id:
            sub_q = await db.execute(
                select(Subscription).where(Subscription.id == alert.subscription_id)
            )
            sub = sub_q.scalar_one_or_none()
            if sub:
                region_name = sub.region_name
        user_alert_rows[user.id].append({
            "date":          alert.sent_at.strftime("%Y-%m-%d") if alert.sent_at else "",
            "region":        region_name,
            "disaster_type": alert.disaster_type or "",
            "severity":      alert.severity_level.value if alert.severity_level else "",
            "message":       (alert.message_body or "")[:120],
        })

    dispatched = 0
    skipped    = 0

    for uid, user in user_meta.items():
        alert_list = user_alert_rows.get(uid, [])
        if not alert_list:
            skipped += 1
            continue
        background_tasks.add_task(
            _send_monthly_digest_background,
            user_id    = user.id,
            email      = user.email,
            full_name  = user.full_name,
            period     = period,
            alert_rows = alert_list,
        )
        dispatched += 1

    return MonthlyDispatchResponse(
        dispatched           = dispatched,
        skipped              = skipped,
        period               = period,
        queued_in_background = True,
    )


async def email_latest_forecast(
    *,
    db:   AsyncSession,
    user: User,
) -> dict:
    """Email a Premium user an HTML alert summarising their most recent 30-day
    forecast (the highest-risk day), reusing the Resend premium-alert pipeline.

    Called by POST /alerts/email-forecast — the dashboard fires it automatically
    right after a premium user generates an alert forecast. The 30 rows were just
    persisted by run_forecast_30d, so we read the most recent batch and summarise
    its peak day.

    Raises HTTPException(404) if the user has no forecast yet. Degrade-not-fail on
    the send itself: a Resend failure logs status='failed' but never raises (the
    PremiumEmailLog row is still written and the endpoint still returns).
    """
    days = await predictor_service.get_latest_forecast_days(db=db, user_id=user.id)
    if not days:
        raise HTTPException(
            status_code=404,
            detail="No forecast found. Run a 30-day forecast first.",
        )

    # Highest-risk day = max probability (severity is a function of probability).
    peak          = max(days, key=lambda d: d.probability_score or 0.0)
    region_name   = peak.region_name or "your region"
    disaster_str  = peak.disaster_type or "disaster"
    severity_str  = peak.severity_level.value if peak.severity_level else ""
    risk_score    = peak.risk_score or 0
    probability   = peak.probability_score or 0.0
    peak_day      = (peak.forecast_day_offset or 0) + 1

    # A valid one-click unsubscribe link needs the subscription's token. Because
    # the premium alert forecast is subscription-driven, an active subscription for
    # this region normally exists; fall back to "" if not (the email is still sent).
    unsubscribe_token = ""
    if peak.region_name:
        token_q = await db.execute(
            select(Subscription.unsubscribe_token).where(
                Subscription.user_id == user.id,
                Subscription.is_active.is_(True),
                Subscription.region_name == peak.region_name,
            )
        )
        unsubscribe_token = token_q.scalars().first() or ""

    message_body = (
        f"Your 30-day outlook for {region_name} shows peak {severity_str} "
        f"{disaster_str} risk on day {peak_day} "
        f"({probability * 100:.0f}% probability). Review your safety plan."
    ).strip()

    context = {
        "full_name":         user.full_name or "",
        "disaster_type":     disaster_str,
        "severity_level":    severity_str,
        "region_name":       region_name,
        "risk_score":        risk_score,
        "message_body":      message_body,
        "unsubscribe_token": unsubscribe_token,
    }

    try:
        message_id   = await email_service.send_premium_alert_email(user.email, context)
        email_status = EmailStatus.sent
    except Exception as exc:  # noqa: BLE001 — degrade-not-fail
        logger.error("email_latest_forecast: send failed for user %s: %s", user.id, exc)
        message_id   = None
        email_status = EmailStatus.failed

    subject = f"[SafeEarth Alert] {severity_str} {disaster_str} risk — 30-day outlook"
    log = PremiumEmailLog(
        id                = uuid.uuid4(),
        user_id           = user.id,
        alert_id          = None,
        resend_message_id = message_id,
        email_type        = EmailType.custom,
        subject           = subject,
        status            = email_status,
    )
    db.add(log)
    await db.commit()

    return {
        "sent":           email_status == EmailStatus.sent,
        "message_id":     message_id,
        "to":             user.email,
        "peak_day":       peak_day,
        "disaster_type":  disaster_str,
        "severity_level": severity_str,
        "region_name":    region_name,
    }
