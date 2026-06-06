from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator


class MonthlyDispatchRequest(BaseModel):
    year: Optional[int] = Field(default=None, ge=2000, le=2100)
    month: Optional[int] = Field(default=None, ge=1, le=12)

    @model_validator(mode="after")
    def _both_or_neither(self) -> "MonthlyDispatchRequest":
        if (self.year is None) != (self.month is None):
            raise ValueError("Provide both year and month, or neither (defaults to previous month).")
        return self


class MonthlyDispatchResponse(BaseModel):
    dispatched: int
    skipped: int
    period: str          # "YYYY-MM"
    queued_in_background: bool
