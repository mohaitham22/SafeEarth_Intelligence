from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_current_user, require_dispatch_auth, require_premium
from database import get_db
from models.user import User
from schemas.alert import (
    AlertHistoryResponse,
    AlertResponse,
    DispatchRequest,
    DispatchResponse,
    EmailForecastResponse,
)
from schemas.monthly_dispatch import MonthlyDispatchRequest, MonthlyDispatchResponse
from services import alert_service

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.post(
    "/dispatch",
    response_model=DispatchResponse,
    dependencies=[Depends(require_dispatch_auth)],
)
async def dispatch_alerts(
    body: DispatchRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigger alert fan-out.

    Called by n8n (X-Dispatch-Secret header) on a weekly schedule, or manually
    by an Admin (Bearer JWT). Alert rows committed before returning; Premium emails
    are dispatched via BackgroundTasks so this endpoint responds immediately.
    """
    queued = await alert_service.dispatch_alerts(
        db=db,
        background_tasks=background_tasks,
        alert_type=body.alert_type,
        region_name=body.region_name,
        disaster_type=body.disaster_type,
        severity_level=body.severity_level,
    )
    return DispatchResponse(
        queued=queued,
        message=f"Alert dispatch queued for {queued} subscription(s).",
    )


@router.post(
    "/email-forecast",
    response_model=EmailForecastResponse,
)
async def email_forecast(
    current_user: User = Depends(require_premium),
    db: AsyncSession = Depends(get_db),
):
    """Email the Premium user an HTML alert summarising their most recent 30-day
    forecast (highest-risk day). Reuses the Resend premium-alert pipeline; the
    dashboard fires this automatically after a premium user generates a forecast.

    404 if the user has no forecast yet. Degrade-not-fail on the send itself.
    """
    return await alert_service.email_latest_forecast(db=db, user=current_user)


@router.post(
    "/monthly-dispatch",
    response_model=MonthlyDispatchResponse,
    dependencies=[Depends(require_dispatch_auth)],
)
async def monthly_dispatch(
    body:             MonthlyDispatchRequest,
    background_tasks: BackgroundTasks,
    db:               AsyncSession = Depends(get_db),
):
    """Fan out monthly digest emails to all premium users who had ≥1 alert in the period.

    Called by n8n on the 1st of each month (X-Dispatch-Secret header) or manually
    by an Admin (Bearer JWT). Defaults to the previous calendar month when year/month
    are omitted. Emails are dispatched via BackgroundTasks — responds immediately.
    """
    return await alert_service.dispatch_monthly_digest(
        year             = body.year,
        month            = body.month,
        db               = db,
        background_tasks = background_tasks,
    )


@router.get(
    "/history",
    response_model=AlertHistoryResponse,
)
async def get_alert_history(
    page: int = 1,
    page_size: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Paginated alert history for the authenticated user (any Subscriber+)."""
    items, total = await alert_service.get_alert_history(
        db=db,
        user_id=current_user.id,
        page=page,
        page_size=page_size,
    )
    return AlertHistoryResponse(
        items=[AlertResponse.model_validate(a) for a in items],
        total=total,
        page=page,
        page_size=page_size,
    )
