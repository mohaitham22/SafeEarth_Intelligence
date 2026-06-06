from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AdResponse(BaseModel):
    """Public ad payload returned by GET /ads (active rows only)."""
    model_config = ConfigDict(from_attributes=True)

    id:         UUID
    title:      str
    body:       Optional[str]
    image_url:  Optional[str]
    link_url:   Optional[str]
    cta_label:  Optional[str]
    sort_order: int


class AdAdminItem(AdResponse):
    """Admin view of an ad — includes is_active + created_at (inactive ads visible)."""
    is_active:  bool
    created_at: datetime


class AdCreate(BaseModel):
    title:      str = Field(min_length=1, max_length=255)
    body:       Optional[str] = None
    image_url:  Optional[str] = Field(default=None, max_length=1000)
    link_url:   Optional[str] = Field(default=None, max_length=1000)
    cta_label:  Optional[str] = Field(default=None, max_length=100)
    sort_order: int = 0
    is_active:  bool = True


class AdUpdate(BaseModel):
    title:      Optional[str] = Field(default=None, min_length=1, max_length=255)
    body:       Optional[str] = None
    image_url:  Optional[str] = Field(default=None, max_length=1000)
    link_url:   Optional[str] = Field(default=None, max_length=1000)
    cta_label:  Optional[str] = Field(default=None, max_length=100)
    sort_order: Optional[int] = None
    is_active:  Optional[bool] = None
