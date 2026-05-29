from fastapi import APIRouter, HTTPException, Query, Response

from ml import emdat_lookup
from schemas.regions import RegionStatsResponse, RiskMapPoint

router = APIRouter(prefix="/regions", tags=["regions"])

_CACHE_1H = "public, max-age=3600"


@router.get("/trends")
async def get_trends(response: Response):
    """Disaster event frequency per decade (1950–2020), one list per disaster type."""
    response.headers["Cache-Control"] = _CACHE_1H
    return emdat_lookup.get_trends()


@router.get("/continent-stats")
async def get_continent_stats(response: Response):
    """Aggregated EM-DAT stats per continent: total events, top disaster, medians."""
    response.headers["Cache-Control"] = _CACHE_1H
    return emdat_lookup.get_continent_stats()


@router.get("/insurance-gap")
async def get_insurance_gap(response: Response):
    """Median insurance coverage ratio per disaster type (insured / total damage)."""
    response.headers["Cache-Control"] = _CACHE_1H
    return emdat_lookup.INSURANCE_RATIOS


@router.get("/seasonal-peaks")
async def get_seasonal_peaks(response: Response):
    """Peak months (1–12) per disaster type — months with ≥1.2× average event count."""
    response.headers["Cache-Control"] = _CACHE_1H
    return emdat_lookup.SEASONAL_PEAKS


@router.get("/secondary-disasters")
async def get_secondary_disasters(response: Response):
    """Historical co-occurrence associations (≥50 events) per primary disaster type."""
    response.headers["Cache-Control"] = _CACHE_1H
    return emdat_lookup.SECONDARY_DISASTERS


@router.get("/timeseries")
async def get_timeseries(response: Response):
    """Year-by-year and decade-by-decade event counts and median impact metrics."""
    response.headers["Cache-Control"] = _CACHE_1H
    return emdat_lookup.get_timeseries()


@router.get("/risk-map", response_model=list[RiskMapPoint])
async def get_risk_map(response: Response):
    """Pre-sampled heat-points for the public Leaflet risk map.

    Each point is one historical disaster event with valid lat/lon and a
    composite risk score in [0, 100]. Generated offline; never recomputed at
    runtime. Cached for 1 hour at the edge."""
    response.headers["Cache-Control"] = _CACHE_1H
    return emdat_lookup.get_risk_map_points()


@router.get("/stats", response_model=RegionStatsResponse)
async def get_region_stats(
    response: Response,
    disaster_type: str = Query(..., description="One of the 8 EM-DAT disaster types"),
    country: str | None = Query(None, description="EM-DAT country name (e.g. Egypt)"),
):
    """3-tier impact lookup: country (n≥5) → sub-continental region (n≥5) → global.

    Returns median deaths/injuries/affected/damage plus coverage rates and data_source.
    Raises 422 if disaster_type is missing, 400 if the type is not in the EM-DAT dataset.
    """
    response.headers["Cache-Control"] = _CACHE_1H
    try:
        return emdat_lookup.resolve_impact_stats(disaster_type.strip(), country)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
