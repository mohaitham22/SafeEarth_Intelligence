"""
backend/ml/emdat_lookup.py

Loads all 8 precomputed JSON files into memory at FastAPI startup.
Call load_all() ONCE from the lifespan context manager in main.py — NEVER per-request.

Usage (in main.py lifespan):
    from ml import emdat_lookup
    emdat_lookup.load_all()

Usage (in any service):
    from ml.emdat_lookup import resolve_impact_stats, get_secondary_warning
    impact = resolve_impact_stats("Flood", country="Egypt")
"""
import json
import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_EVENTS = 5  # minimum n_events to trust country/region tier; fall back to global otherwise

# Absolute path to project root, derived from this file's location:
# backend/ml/emdat_lookup.py → backend/ml/ → backend/ → project_root/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# Module-level globals (all start empty — populated by load_all() at startup)
# ---------------------------------------------------------------------------

EMDAT_STATS: dict         = {}
SECONDARY_DISASTERS: dict = {}
SEASONAL_PEAKS: dict      = {}
INSURANCE_RATIOS: dict    = {}
TRENDS: dict              = {}
CONTINENT_STATS: dict     = {}
TIMESERIES: dict          = {}
RISK_MAP_POINTS: list     = []  # [{lat, lon, risk_score, disaster_type}, ...]
COUNTRIES: dict           = {}  # {default: {...}, continents: {cont: [{name, label, lat, lon, ...}]}}

# country name (as it appears in EM-DAT) → sub-continental region string
# e.g. "Egypt" → "Northern Africa", "Japan" → "Eastern Asia"
# Built during load_all() from the train CSV (Country + Region columns only).
COUNTRY_TO_REGION: dict = {}

# ---------------------------------------------------------------------------
# Startup loader
# ---------------------------------------------------------------------------

def load_all(data_dir: Path = Path("data/generated")) -> None:
    """Load all 8 precomputed JSON files into module-level globals.

    Called ONCE from the FastAPI lifespan context manager.
    Raises FileNotFoundError if any file is missing, with a message directing
    the user to run scripts/generate_emdat_stats.py first.
    """
    global EMDAT_STATS, SECONDARY_DISASTERS, SEASONAL_PEAKS, INSURANCE_RATIOS
    global TRENDS, CONTINENT_STATS, TIMESERIES, COUNTRY_TO_REGION, RISK_MAP_POINTS
    global COUNTRIES

    files = {
        "emdat_stats":         "emdat_stats.json",
        "secondary_disasters": "secondary_disasters.json",
        "seasonal_peaks":      "seasonal_peaks.json",
        "insurance_ratios":    "insurance_ratios.json",
        "trends":              "trends.json",
        "continent_stats":     "continent_stats.json",
        "timeseries":          "timeseries.json",
        "risk_map":            "risk_map.json",
        "countries":           "countries.json",
    }

    loaded: dict = {}
    for key, filename in files.items():
        path = data_dir / filename
        if not path.exists():
            raise FileNotFoundError(
                f"Missing generated file: {path}\n"
                f"Run this first:  python scripts/generate_emdat_stats.py"
            )
        with open(path, encoding="utf-8") as fp:
            loaded[key] = json.load(fp)
        log.info("  Loaded %-35s  (%.1f KB)", filename, path.stat().st_size / 1024)

    EMDAT_STATS         = loaded["emdat_stats"]
    SECONDARY_DISASTERS = loaded["secondary_disasters"]
    SEASONAL_PEAKS      = loaded["seasonal_peaks"]
    INSURANCE_RATIOS    = loaded["insurance_ratios"]
    TRENDS              = loaded["trends"]
    CONTINENT_STATS     = loaded["continent_stats"]
    TIMESERIES          = loaded["timeseries"]
    RISK_MAP_POINTS     = loaded["risk_map"]
    COUNTRIES           = loaded["countries"]

    # Build COUNTRY_TO_REGION from the train CSV (Country + Region columns only).
    # Uses the most-frequent Region value per country to handle any inconsistencies.
    train_csv = (
        _PROJECT_ROOT / "data" / "train" / "1900_2021_DISASTERS.xlsx - train data.csv"
    )
    if train_csv.exists():
        df_loc = pd.read_csv(train_csv, usecols=["Country", "Region"], low_memory=False)
        COUNTRY_TO_REGION = (
            df_loc.dropna(subset=["Country", "Region"])
            .groupby("Country")["Region"]
            .agg(lambda x: x.mode().iloc[0])
            .to_dict()
        )
        log.info("  COUNTRY_TO_REGION: %d countries mapped", len(COUNTRY_TO_REGION))
    else:
        log.warning(
            "Train CSV not found at %s — COUNTRY_TO_REGION will be empty. "
            "Region-tier lookup will always fall through to global.",
            train_csv,
        )

    log.info(
        "emdat_lookup: all 8 files loaded into memory  (risk_map: %d points).",
        len(RISK_MAP_POINTS),
    )


# ---------------------------------------------------------------------------
# Core 3-tier lookup
# ---------------------------------------------------------------------------

def resolve_impact_stats(disaster_type: str, country: str | None = None) -> dict:
    """3-tier impact lookup: country (n≥5) → region (n≥5) → global.

    Args:
        disaster_type: One of the 8 valid EM-DAT types. Strip whitespace before passing.
        country:       EM-DAT country name (e.g. "Egypt"), or None for global-only lookup.

    Returns:
        Stats dict with all 9 coverage/median fields plus:
            data_source:  "country" | "region" | "global"
            country_used: the country argument (or None)

    Raises:
        KeyError: if disaster_type is not present in the global tier.
    """
    dtype = disaster_type.strip()

    global_tier = EMDAT_STATS.get("global", {})
    if dtype not in global_tier:
        raise KeyError(
            f"Unknown disaster type: {dtype!r}. "
            f"Valid types: {sorted(global_tier.keys())}"
        )

    def _trusted(stats: dict) -> bool:
        return stats.get("n_events", 0) >= MIN_EVENTS

    # Tier 1 — country
    if country:
        entry = EMDAT_STATS.get("by_country", {}).get(country, {}).get(dtype)
        if entry and _trusted(entry):
            return {**entry, "data_source": "country", "country_used": country}

    # Tier 2 — sub-continental region (derived from country via COUNTRY_TO_REGION)
    if country:
        region = COUNTRY_TO_REGION.get(country)
        if region:
            entry = EMDAT_STATS.get("by_region", {}).get(region, {}).get(dtype)
            if entry and _trusted(entry):
                return {**entry, "data_source": "region", "country_used": country}

    # Tier 3 — global (guaranteed to exist because we validated dtype above)
    return {**global_tier[dtype], "data_source": "global", "country_used": country}


# ---------------------------------------------------------------------------
# Accessors
# ---------------------------------------------------------------------------

def get_insurance_ratio(disaster_type: str) -> float:
    """Return insurance coverage ratio for a disaster type.
    Defaults to 0.20 if the type has no data (Volcanic activity has no usable rows).
    """
    return INSURANCE_RATIOS.get(disaster_type.strip(), 0.20)


def get_secondary_warning(disaster_type: str) -> str | None:
    """Return a formatted secondary-disaster warning string, or None.

    Format (from emdat-lookup-usage.md skill):
        "{Type}s historically trigger {secondary}s ({N:,} recorded co-occurrences in EM-DAT data)"

    Returns None if no association meets the >= 50 co-occurrence threshold.
    """
    associations = SECONDARY_DISASTERS.get(disaster_type.strip(), [])
    if not associations:
        return None
    top = associations[0]  # generator sorts descending by count
    return (
        f"{disaster_type}s historically trigger {top['type'].lower()}s "
        f"({top['count']:,} recorded co-occurrences in EM-DAT data)"
    )


def get_seasonal_peaks(disaster_type: str) -> list[int]:
    """Return peak month numbers (1–12) for a disaster type, or empty list."""
    return SEASONAL_PEAKS.get(disaster_type.strip(), [])


def get_trends() -> dict:
    """Return full trends dict: {decades: [...], disaster_type: [counts_per_decade]}."""
    return TRENDS


def get_continent_stats() -> dict:
    """Return full continent stats dict: {continent: {total_events, top_disaster, ...}}."""
    return CONTINENT_STATS


def get_timeseries() -> dict:
    """Return full timeseries dict: {by_year: {...}, by_decade: {...}}."""
    return TIMESERIES


def get_risk_map_points() -> list[dict]:
    """Return the pre-sampled risk map points loaded from risk_map.json.

    Each point: {"lat": float, "lon": float, "risk_score": float (0-100),
                 "disaster_type": str}
    """
    return RISK_MAP_POINTS


def get_countries() -> dict:
    """Return the continent→country picker table loaded from countries.json.

    Shape: {"default": {continent, name, label, lat, lon},
            "continents": {<continent>: [{name, label, iso, lat, lon, n_events}]}}
    `name` is the exact EM-DAT country string (matches by_country keys).
    """
    return COUNTRIES
