from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import require_subscriber
from database import get_db
from models.user import User
from schemas.premium import CheckoutRequest, CheckoutResponse, WebhookResponse
from services import premium_service

router = APIRouter(prefix="/premium", tags=["premium"])


@router.post("/checkout", response_model=CheckoutResponse, status_code=status.HTTP_201_CREATED)
async def checkout(
    body: CheckoutRequest,
    current_user: User = Depends(require_subscriber),
    db: AsyncSession = Depends(get_db),
):
    result = await premium_service.create_checkout(
        user=current_user,
        plan_name=body.plan_name,
        db=db,
    )
    return result


@router.post("/webhook", response_model=WebhookResponse, status_code=status.HTTP_200_OK)
async def webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    sig = request.headers.get("X-Mock-Signature", "")
    await premium_service.handle_webhook_event(body, sig, db)
    return WebhookResponse(received=True)
