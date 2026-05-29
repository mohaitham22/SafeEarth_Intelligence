import json
import uuid
from abc import ABC, abstractmethod
from decimal import Decimal

from fastapi import HTTPException, status

from config import get_settings


class PaymentService(ABC):
    """Abstract payment provider interface.

    Concrete implementations: MockPaymentService (v1).
    Real provider (Stripe/Paymob) = drop-in subclass, selected via PAYMENT_PROVIDER env var.
    Never instantiate a subclass directly — always use get_payment_service().
    """

    @abstractmethod
    async def create_checkout_session(
        self,
        user_id: str,
        plan_id: str,
        plan_name: str,
        amount_usd: Decimal,
    ) -> dict:
        """Create a hosted checkout session for the given plan.

        Returns at minimum:
            {"checkout_url": str, "session_id": str}

        The checkout_url is what the frontend redirects the user to.
        The session_id is stored and later matched against the incoming webhook.
        """

    @abstractmethod
    async def verify_webhook_signature(
        self,
        payload: bytes,
        signature_header: str,
    ) -> dict:
        """Verify the webhook signature and return the parsed event dict.

        MUST be called before any DB write in the webhook handler.
        Raises HTTPException 400 if signature is absent or invalid.

        Returned event dict shape (contract with premium_service.handle_webhook_event):
            {
                "type":                   "payment.success" | "payment.failed",
                "session_id":             str,   # matches session_id from create_checkout_session
                "user_id":                str,   # UUID string of the user
                "plan_id":                str,   # UUID string of the plan
                "amount_usd":             float,
                "provider_transaction_id": str,  # provider-assigned ID
            }
        """


class MockPaymentService(PaymentService):
    """Mock payment provider for v1 development and testing.

    Security contract (mirrors real providers):
    - checkout: returns a fake URL with a deterministic session_id
    - webhook: any non-empty X-Mock-Signature header is accepted as valid;
      empty/missing → HTTPException 400 (enforces "verify FIRST" discipline in tests)

    Webhook payload format (test callers must send):
        JSON body with keys: type, session_id, user_id, plan_id,
                             amount_usd, provider_transaction_id (optional)
    """

    async def create_checkout_session(
        self,
        user_id: str,
        plan_id: str,
        plan_name: str,
        amount_usd: Decimal,
    ) -> dict:
        settings = get_settings()
        session_id = f"mock_{uuid.uuid4().hex[:16]}"
        checkout_url = (
            f"{settings.frontend_url}/mock-checkout?session_id={session_id}"
            f"&plan={plan_name}&amount={amount_usd}"
        )
        return {"checkout_url": checkout_url, "session_id": session_id}

    async def verify_webhook_signature(
        self,
        payload: bytes,
        signature_header: str,
    ) -> dict:
        if not signature_header:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing X-Mock-Signature header. Webhook signature required.",
            )

        try:
            event = json.loads(payload)
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid webhook payload: {exc}",
            ) from exc

        event.setdefault("provider_transaction_id", f"mock_txn_{uuid.uuid4().hex[:12]}")
        return event


def get_payment_service() -> PaymentService:
    """Factory — the single creation point for PaymentService instances.

    Reads PAYMENT_PROVIDER from settings.
    Never instantiate a PaymentService subclass anywhere else.
    """
    settings = get_settings()
    provider = (settings.payment_provider or "mock").lower().strip()

    if provider == "mock":
        return MockPaymentService()

    raise NotImplementedError(
        f"Payment provider '{provider}' is not implemented. "
        "Supported in v1: 'mock'. "
        "To add Stripe or Paymob: subclass PaymentService, implement both abstract methods, "
        "and add an elif branch here. Set PAYMENT_PROVIDER in .env."
    )
