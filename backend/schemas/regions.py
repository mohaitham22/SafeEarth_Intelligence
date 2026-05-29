from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# /regions/stats — strongly typed contract
# ---------------------------------------------------------------------------

class RegionStatsResponse(BaseModel):
    median_deaths: int | None = None
    median_injuries: int | None = None
    median_affected: int | None = None
    median_damage_000usd: int | None = None
    n_events: int
    deaths_coverage: float
    injuries_coverage: float
    affected_coverage: float
    damage_coverage: float
    data_source: str          # "country" | "region" | "global"
    country_used: str | None = None


# ---------------------------------------------------------------------------
# Supporting sub-models for complex passthrough responses
# ---------------------------------------------------------------------------

class ContinentEntry(BaseModel):
    total_events: int
    top_disaster: str
    median_deaths: int | None = None
    median_damage_000usd: int | None = None


class SecondaryDisasterEntry(BaseModel):
    type: str
    count: int


class TimeseriesYearEntry(BaseModel):
    year: int
    events: int
    deaths: int | None = None
    affected: int | None = None
    damage_000usd: int | None = None


class TimeseriesDecadeEntry(BaseModel):
    decade: int
    events: int
    deaths: int | None = None
    affected: int | None = None
    damage_000usd: int | None = None


# ---------------------------------------------------------------------------
# Type aliases for passthrough JSON endpoints
# Routers return these dicts directly without response_model validation —
# the aliases document the contract for the frontend TypeScript types.
# ---------------------------------------------------------------------------

# {decades: list[int], "Flood": list[int], ...}  — keys are disaster types + "decades"
TrendsResponse = dict[str, Any]

# {continent: {total_events, top_disaster, median_deaths, median_damage_000usd}}
ContinentStatsResponse = dict[str, ContinentEntry]

# {disaster_type: float}  — e.g. {"Flood": 0.26, "Earthquake": 0.17}
InsuranceGapResponse = dict[str, float]

# {disaster_type: list[int]}  — month numbers 1–12
SeasonalPeaksResponse = dict[str, list[int]]

# {disaster_type: [{type: str, count: int}]}
SecondaryDisastersResponse = dict[str, list[SecondaryDisasterEntry]]


class TimeseriesResponse(BaseModel):
    by_year: dict[str, list[TimeseriesYearEntry]]
    by_decade: dict[str, list[TimeseriesDecadeEntry]]


# ---------------------------------------------------------------------------
# /regions/risk-map — heat-points for the public Leaflet map
# ---------------------------------------------------------------------------

class RiskMapPoint(BaseModel):
    """One historical disaster event with valid lat/lon and a composite risk
    score in [0, 100]. risk_score uses the CLAUDE.md formula with the
    probability term fixed at 1.0 (these are historical events, not
    predictions). Pre-sampled offline by scripts/generate_emdat_stats.py
    (3 of the 8 EM-DAT types — Drought, Wildfire, Extreme temperature — are
    omitted because EM-DAT has no point coordinates for them)."""
    lat:           float
    lon:           float
    risk_score:    float
    disaster_type: str


RiskMapResponse = list[RiskMapPoint]
