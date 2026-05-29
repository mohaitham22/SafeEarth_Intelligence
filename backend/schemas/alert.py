from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from models.enums import AlertStatus, AlertType, SeverityLevel


class DispatchRequest(BaseModel):
    """Body for POST /alerts/dispatch — sent by n8n or an admin."""

    alert_type: AlertType = AlertType.weekly_digest
    # Required only for high_risk_immediate dispatches
    region_name: Optional[str] = Field(default=None, max_length=255)
    disaster_type: Optional[str] = Field(default=None, max_length=100)
    severity_level: Optional[SeverityLevel] = None


class DispatchResponse(BaseModel):
    queued: int
    message: str


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    subscription_id: UUID
    user_id: UUID
    alert_type: AlertType
    disaster_type: Optional[str]
    severity_level: Optional[SeverityLevel]
    message_body: Optional[str]
    sent_at: Optional[datetime]
    status: AlertStatus


class AlertHistoryResponse(BaseModel):
    items: list[AlertResponse]
    total: int
    page: int
    page_size: int
