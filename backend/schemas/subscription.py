from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from models.enums import AlertFrequency


class SubscriptionCreate(BaseModel):
    region_name: str = Field(..., min_length=1, max_length=255)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    alert_frequency: AlertFrequency = AlertFrequency.weekly


class SubscriptionResponse(BaseModel):
    """Full response — includes unsubscribe_token. Used only on POST (creation)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    region_name: str
    latitude: float
    longitude: float
    alert_frequency: AlertFrequency
    is_active: bool
    unsubscribe_token: str
    created_at: datetime


class SubscriptionListItem(BaseModel):
    """Authenticated list representation — includes unsubscribe_token for dashboard use."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    region_name: str
    latitude: float
    longitude: float
    alert_frequency: AlertFrequency
    is_active: bool
    unsubscribe_token: str
    created_at: datetime
