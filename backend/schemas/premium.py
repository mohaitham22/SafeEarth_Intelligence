from typing import Literal

from pydantic import BaseModel


class CheckoutRequest(BaseModel):
    plan_name: Literal["monthly", "yearly"]


class CheckoutResponse(BaseModel):
    checkout_url: str
    session_id: str
    plan_name: str


class WebhookResponse(BaseModel):
    received: bool
