from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from schemas.recommendation import RecommendationItem


# 8 valid EM-DAT disaster types — rejected at the schema boundary with 422 otherwise.
DisasterType = Literal[
    "Flood", "Storm", "Earthquake", "Wildfire",
    "Volcanic activity", "Landslide", "Drought", "Extreme temperature",
]


class SHAPFeature(BaseModel):
    feature: str
    contribution_pct: float


class PredictRequest(BaseModel):
    latitude:      float            = Field(..., ge=-90,  le=90)
    longitude:     float            = Field(..., ge=-180, le=180)
    region_name:   Optional[str]    = Field(default=None, max_length=255)
    country:       str              = Field(..., min_length=1, max_length=255)
    continent:     str              = Field(..., min_length=1, max_length=100)
    disaster_type: DisasterType     = Field(..., description="One of the 8 valid EM-DAT disaster types")
    season:        Union[str, int]  = Field(
        default=0,
        description='Season name ("spring"/"summer"/"autumn"/"fall"/"winter"), '
                    'integer month 1–12, or 0 for current month',
    )


class PredictionResponse(BaseModel):
    id:                          uuid.UUID
    disaster_type:               str
    probability_score:           float
    severity_level:              str
    risk_score:                  float
    estimated_deaths:            int
    estimated_injuries:          int
    estimated_affected:          int
    estimated_damage_usd:        int
    uninsured_loss_usd:          int
    shap_explanation:            List[SHAPFeature]
    secondary_disaster_warning:  Optional[str]
    seasonal_peak_months:        List[int]
    data_quality:                str
    data_source:                 str
    country_used:                Optional[str]
    n_events:                    int
    recommendations:             List[RecommendationItem] = []
    model_version:               str
    created_at:                  datetime

    model_config = {"from_attributes": True}


class ForecastDayResponse(PredictionResponse):
    forecast_day_offset: int
    date: str


class ForecastRequest(BaseModel):
    latitude:      float           = Field(..., ge=-90,  le=90)
    longitude:     float           = Field(..., ge=-180, le=180)
    region_name:   Optional[str]   = Field(default=None, max_length=255)
    country:       str             = Field(..., min_length=1, max_length=255)
    continent:     str             = Field(..., min_length=1, max_length=100)
    disaster_type: DisasterType    = Field(..., description="One of the 8 valid EM-DAT disaster types")
    force_refresh: bool            = False


class PredictionHistoryItem(BaseModel):
    id:                uuid.UUID
    disaster_type:     Optional[str]
    severity_level:    Optional[str]
    probability_score: Optional[float]
    risk_score:        Optional[float]
    region_name:       Optional[str]
    latitude:          Optional[float]
    longitude:         Optional[float]
    created_at:        datetime

    model_config = {"from_attributes": True}


class PredictionHistoryResponse(BaseModel):
    items:      List[PredictionHistoryItem]
    total:      int
    page:       int
    page_size:  int


# ── /predictions/classify ─────────────────────────────────────────────────────

class ClassifyRequest(BaseModel):
    latitude:   float            = Field(..., ge=-90,  le=90)
    longitude:  float            = Field(..., ge=-180, le=180)
    continent:  str              = Field(..., min_length=1, max_length=100)
    country:    Optional[str]    = Field(default=None, max_length=255)
    year:       int              = Field(..., ge=1900, le=2100)
    season:     Union[str, int]  = Field(
        default=0,
        description='Season name or integer month 1–12 (0 = current month)',
    )
    magnitude:  Optional[float]  = Field(default=None)


class DisasterProbability(BaseModel):
    disaster_type: str
    probability:   float


class ClassifyResponse(BaseModel):
    ranked:          List[DisasterProbability]
    top_type:        str
    top_probability: float
    model_version:   str


# ── /predictions/impact ───────────────────────────────────────────────────────

class ImpactRequest(BaseModel):
    latitude:     float            = Field(..., ge=-90,  le=90)
    longitude:    float            = Field(..., ge=-180, le=180)
    continent:    str              = Field(..., min_length=1, max_length=100)
    year:         int              = Field(..., ge=1900, le=2100)
    season:       Union[str, int]  = Field(default=0)
    region_name:  Optional[str]    = Field(default=None)
    country:      Optional[str]    = Field(default=None)


class ImpactResponse(BaseModel):
    predicted_disaster_type: str
    probability:             float
    expected_events:         int
    estimated_deaths:        int
    estimated_injuries:      int
    estimated_affected:      int
    estimated_damage_usd:    int   # thousands USD
    uninsured_loss_usd:      int   # thousands USD
    data_source:             str
    model_version:           str
