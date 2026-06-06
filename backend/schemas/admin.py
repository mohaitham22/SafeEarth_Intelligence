from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AdminUserItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: Optional[str]
    role: str
    is_verified: bool
    premium_expires_at: Optional[datetime] = None
    created_at: datetime


class AdminUsersResponse(BaseModel):
    items: list[AdminUserItem]
    total: int
    page: int
    page_size: int


class PatchUserRequest(BaseModel):
    role: Optional[str] = None
    is_verified: Optional[bool] = None


class DispatchPreviewResponse(BaseModel):
    active_subscriptions: int
    premium_users: int


class PerClassF1(BaseModel):
    type: str
    f1: float
    support: int


class ModelStatsResponse(BaseModel):
    version: str
    macro_f1: float
    weighted_f1: float
    accuracy: float
    feature_count: int
    ensemble: dict
    per_class_f1: list[PerClassF1]
    models_loaded: bool
    rag_loaded: bool


class UserCountsByRole(BaseModel):
    subscriber: int = 0
    premium: int = 0
    admin: int = 0


class UserStats(BaseModel):
    total: int
    verified: int
    by_role: UserCountsByRole


class PredictionStats(BaseModel):
    total: int
    forecasts: int
    last_7_days: int


class SubscriptionStats(BaseModel):
    active: int


class AlertStats(BaseModel):
    total_sent: int
    last_7_days: int


class PaymentStats(BaseModel):
    total_succeeded: int
    revenue_usd: str


class EmailLogStats(BaseModel):
    total: int


class SiteStatsResponse(BaseModel):
    users: UserStats
    predictions: PredictionStats
    subscriptions: SubscriptionStats
    alerts: AlertStats
    payments: PaymentStats
    email_logs: EmailLogStats
