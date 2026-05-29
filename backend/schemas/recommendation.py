"""
Pydantic v2 schemas for the /recommendations endpoint and for the
`recommendations` field embedded in prediction responses.

Phase 4 (RAG pipeline) populates these via:
  PDF -> ChromaDB cosine search -> Groq LLM -> 6 calibrated recommendations

Until then, the prediction service returns `recommendations: []` so the API
shape matches the CLAUDE.md Feature 1 contract.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


RecommendationCategory = Literal["evacuation", "kit", "shelter", "medical", "contact"]
SeverityLiteral        = Literal["Low", "Medium", "High", "Critical"]

# Mirrors DisasterType in schemas/prediction.py — duplicated here to avoid the
# circular import (prediction.py already imports RecommendationItem from this file).
# If the 8-type EM-DAT taxonomy ever changes, update both Literals together.
DisasterTypeLiteral = Literal[
    "Flood", "Storm", "Earthquake", "Wildfire",
    "Volcanic activity", "Landslide", "Drought", "Extreme temperature",
]


class RecommendationItem(BaseModel):
    category: RecommendationCategory
    title:    str
    body:     str


class RecommendationQuery(BaseModel):
    """Query params for GET /recommendations — validated at the schema boundary."""
    disaster_type: DisasterTypeLiteral
    severity:      SeverityLiteral
    region_name:   str = Field(..., min_length=1, max_length=255)


class RecommendationResponse(BaseModel):
    """Returned by GET /recommendations — typically 6 items sorted
    evacuation -> kit -> shelter -> medical -> contact. Fewer when the DB
    fallback table has no matching rows seeded yet."""
    items: List[RecommendationItem]
    personalisation_notice: Optional[str] = None
