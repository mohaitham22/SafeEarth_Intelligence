"""
scripts/generate_emdat_stats.py

Run ONCE before first deployment. Reads the EM-DAT train CSV.
Writes all 9 precomputed JSON files to data/generated/.

Rules (from CLAUDE.md — do not break):
  - NEVER use mean. Always median (np.nanmedian).
  - NEVER read from data/test/.
  - NEVER run at FastAPI startup — offline only.
  - Outliers capped at 99th-percentile PER disaster type before median.
  - n >= 5 trust threshold applied at READ time in emdat_lookup.py, not here.

Usage:
    python scripts/generate_emdat_stats.py
    python scripts/generate_emdat_stats.py --train-csv path/to/csv --out-dir path/to/out
"""
import argparse
import json
import logging
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Exact strings as they appear in the CSV after .strip()
# Source: scripts/inspect_data.py — confirmed 2026-05-20
VALID_DISASTER_TYPES = [
    "Flood",
    "Storm",
    "Earthquake",
    "Wildfire",
    "Volcanic activity",    # lowercase 'a'
    "Landslide",
    "Drought",
    "Extreme temperature",  # CSV has trailing space 'Extreme temperature ' — stripped below
]

# Confirmed exact column names from scripts/inspect_data.py
COL_TYPE      = "Disaster Type"
COL_GROUP     = "Disaster Group"
COL_COUNTRY   = "Country"
COL_REGION    = "Region"        # sub-continental, e.g. "Western Africa"
COL_CONTINENT = "Continent"     # continental,     e.g. "Africa"
COL_YEAR      = "Start Year"
COL_MONTH     = "Start Month"
COL_DEATHS    = "Total Deaths"
COL_INJURED   = "No Injured"
COL_AFFECTED  = "Total Affected"    # use this — NOT the separate "No Affected" column
COL_DAMAGE    = "Total Damages ('000 US$)"
COL_INSURED   = "Insured Damages ('000 US$)"
COL_MAG       = "Dis Mag Value"
COL_ASSOC1    = "Associated Dis"
COL_ASSOC2    = "Associated Dis2"   # second associated-disaster column — combine with ASSOC1
COL_LAT       = "Latitude"
COL_LON       = "Longitude"

IMPACT_COLS = [COL_DEATHS, COL_INJURED, COL_AFFECTED, COL_DAMAGE]

COL_ISO = "ISO"   # 3-letter ISO3 country code (clean, 100% coverage — verified)

# ---------------------------------------------------------------------------
# ISO3 → (lat, lon) country centroid table — used by build_countries() to give
# each EM-DAT country a STABLE representative coordinate for the location picker.
# (Event-median coords are too sparse/jumpy: only ~2.6k of 16k rows have valid
# lat/lon.) Historical/aggregate ISO codes with no clean single centroid
# (SUN/YUG/SCG/CSK/DDR/ANT/AZO/YMD/YMN/...) are intentionally omitted — countries
# without an entry here are dropped from the picker.
# ---------------------------------------------------------------------------

_ISO3_CENTROIDS: dict[str, tuple[float, float]] = {
    # Americas
    "USA": (39.83, -98.58), "CAN": (56.13, -106.35), "MEX": (23.63, -102.55),
    "BRA": (-10.33, -53.20), "ARG": (-38.42, -63.62), "COL": (4.57, -74.30),
    "PER": (-9.19, -75.02), "CHL": (-35.68, -71.54), "BOL": (-16.29, -63.59),
    "ECU": (-1.83, -78.18), "VEN": (6.42, -66.59), "GTM": (15.78, -90.23),
    "CUB": (21.52, -77.78), "HTI": (18.97, -72.29), "DOM": (18.74, -70.16),
    "HND": (15.20, -86.24), "NIC": (12.87, -85.21), "CRI": (9.75, -83.75),
    "PAN": (8.54, -80.78), "SLV": (13.79, -88.90), "PRY": (-23.44, -58.44),
    "URY": (-32.52, -55.77), "JAM": (18.11, -77.30), "PRI": (18.22, -66.59),
    "BHS": (25.03, -77.40), "BLZ": (17.19, -88.50), "GUY": (4.86, -58.93),
    "SUR": (3.92, -56.03), "TTO": (10.69, -61.22), "BRB": (13.19, -59.54),
    "LCA": (13.91, -60.98), "VCT": (12.98, -61.29), "GRD": (12.12, -61.67),
    "DMA": (15.41, -61.37), "ATG": (17.06, -61.80), "KNA": (17.36, -62.78),
    "AIA": (18.22, -63.07), "MSR": (16.74, -62.19), "TCA": (21.69, -71.80),
    "CYM": (19.31, -81.25), "BMU": (32.32, -64.76), "VGB": (18.42, -64.64),
    "VIR": (18.34, -64.90), "MTQ": (14.64, -61.02), "GLP": (16.27, -61.55),
    "GUF": (3.93, -53.13),
    # Africa
    "NGA": (9.08, 8.68), "COD": (-4.04, 21.76), "ETH": (9.15, 40.49),
    "KEN": (-0.02, 37.91), "TZA": (-6.37, 34.89), "ZAF": (-30.56, 22.94),
    "MOZ": (-18.67, 35.53), "UGA": (1.37, 32.29), "SDN": (12.86, 30.22),
    "SOM": (5.15, 46.20), "NER": (17.61, 8.08), "DZA": (28.03, 1.66),
    "MDG": (-18.77, 46.87), "AGO": (-11.20, 17.87), "MWI": (-13.25, 34.30),
    "BFA": (12.24, -1.56), "TCD": (15.45, 18.73), "MLI": (17.57, -3.996),
    "BDI": (-3.37, 29.92), "MAR": (31.79, -7.09), "CMR": (7.37, 12.35),
    "SEN": (14.50, -14.45), "GHA": (7.95, -1.02), "BEN": (9.31, 2.32),
    "RWA": (-1.94, 29.87), "ZWE": (-19.02, 29.15), "ZMB": (-13.13, 27.85),
    "MRT": (21.01, -10.94), "CAF": (6.61, 20.94), "GIN": (9.95, -9.70),
    "EGY": (26.82, 30.80), "GMB": (13.44, -15.31), "COG": (-0.23, 15.83),
    "NAM": (-22.96, 18.49), "SLE": (8.46, -11.78), "CIV": (7.54, -5.55),
    "TGO": (8.62, 0.82), "DJI": (11.83, 42.59), "LSO": (-29.61, 28.23),
    "SSD": (6.88, 31.31), "TUN": (33.89, 9.54), "GNB": (11.80, -15.18),
    "COM": (-11.65, 43.33), "LBR": (6.43, -9.43), "MUS": (-20.35, 57.55),
    "BWA": (-22.33, 24.68), "CPV": (16.00, -24.01), "SWZ": (-26.52, 31.47),
    "REU": (-21.12, 55.54), "GAB": (-0.80, 11.61), "ERI": (15.18, 39.78),
    "SYC": (-4.68, 55.49), "LBY": (26.34, 17.23), "STP": (0.19, 6.61),
    "GNQ": (1.65, 10.27), "SHN": (-15.96, -5.71),
    # Asia
    "CHN": (35.86, 104.20), "IND": (20.59, 78.96), "PHL": (12.88, 121.77),
    "IDN": (-0.79, 113.92), "JPN": (36.20, 138.25), "BGD": (23.68, 90.36),
    "IRN": (32.43, 53.69), "VNM": (14.06, 108.28), "PAK": (30.38, 69.35),
    "AFG": (33.94, 67.71), "TUR": (38.96, 35.24), "THA": (15.87, 100.99),
    "HKG": (22.32, 114.17), "TWN": (23.70, 120.96), "NPL": (28.39, 84.12),
    "KOR": (35.91, 127.77), "LKA": (7.87, 80.77), "MYS": (4.21, 101.98),
    "MMR": (21.91, 95.96), "TJK": (38.86, 71.28), "YEM": (15.55, 48.52),
    "LAO": (19.86, 102.50), "PRK": (40.34, 127.51), "KHM": (12.57, 104.99),
    "MNG": (46.86, 103.85), "IRQ": (33.22, 43.68), "SAU": (23.89, 45.08),
    "KAZ": (48.02, 66.92), "GEO": (42.32, 43.36), "KGZ": (41.20, 74.77),
    "ISR": (31.05, 34.85), "JOR": (30.59, 36.24), "AZE": (40.14, 47.58),
    "SYR": (34.80, 38.997), "CYP": (35.13, 33.43), "LBN": (33.85, 35.86),
    "TLS": (-8.87, 125.73), "ARM": (40.07, 45.04), "BTN": (27.51, 90.43),
    "UZB": (41.38, 64.59), "PSE": (31.95, 35.23), "MAC": (22.20, 113.54),
    "MDV": (3.20, 73.22), "OMN": (21.51, 55.92), "KWT": (29.31, 47.48),
    "TKM": (38.97, 59.56), "ARE": (23.42, 53.85), "BHR": (26.07, 50.56),
    "BRN": (4.54, 114.73), "QAT": (25.35, 51.18), "SGP": (1.35, 103.82),
    # Europe
    "FRA": (46.23, 2.21), "ITA": (41.87, 12.57), "RUS": (61.52, 105.32),
    "GRC": (39.07, 21.82), "ESP": (40.46, -3.75), "ROU": (45.94, 24.97),
    "GBR": (55.38, -3.44), "DEU": (51.17, 10.45), "BEL": (50.50, 4.47),
    "CHE": (46.82, 8.23), "POL": (51.92, 19.15), "AUT": (47.52, 14.55),
    "PRT": (39.40, -8.22), "BGR": (42.73, 25.49), "ALB": (41.15, 20.17),
    "NLD": (52.13, 5.29), "UKR": (48.38, 31.17), "HUN": (47.16, 19.50),
    "HRV": (45.10, 15.20), "CZE": (49.82, 15.47), "SRB": (44.02, 21.01),
    "BIH": (43.92, 17.68), "IRL": (53.41, -8.24), "MKD": (41.61, 21.75),
    "SVK": (48.67, 19.70), "DNK": (56.26, 9.50), "SWE": (60.13, 18.64),
    "MDA": (47.41, 28.37), "LTU": (55.17, 23.88), "BLR": (53.71, 27.95),
    "ISL": (64.96, -19.02), "LUX": (49.82, 6.13), "NOR": (60.47, 8.47),
    "SVN": (46.15, 14.99), "LVA": (56.88, 24.60), "MNE": (42.71, 19.37),
    "EST": (58.60, 25.01), "FIN": (61.92, 25.75), "IMN": (54.24, -4.55),
    # Oceania
    "AUS": (-25.27, 133.78), "PNG": (-6.31, 143.96), "NZL": (-40.90, 174.89),
    "FJI": (-17.71, 178.07), "VUT": (-15.38, 166.96), "SLB": (-9.65, 160.16),
    "NCL": (-20.90, 165.62), "WSM": (-13.76, -172.10), "TON": (-21.18, -175.20),
    "COK": (-21.24, -159.78), "FSM": (7.43, 150.55), "GUM": (13.44, 144.79),
    "PYF": (-17.68, -149.41), "TUV": (-7.11, 177.65), "MHL": (7.13, 171.18),
    "TKL": (-9.20, -171.85), "NIU": (-19.05, -169.87), "ASM": (-14.27, -170.13),
    "KIR": (-3.37, -168.73), "PLW": (7.51, 134.58), "WLF": (-13.77, -177.16),
    "MNP": (15.10, 145.67),
}


def _clean_country_label(name: str) -> str:
    """Human-readable label for the picker. Keeps disambiguating parentheticals
    (e.g. the two Congos / Koreas) but drops the bureaucratic ' (the)' noise."""
    s = str(name).strip()
    s = s.replace(" (the)", "").replace("(the ", "(")
    return s.strip()

# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def safe_median(series: pd.Series) -> float | None:
    """Return float median ignoring NaN. Returns None when all values are NaN."""
    return float(np.nanmedian(series.dropna().values)) if series.notna().any() else None


def _to_int(v: float | None) -> int:
    """Cast safe_median result to native Python int. Returns 0 when None."""
    return int(round(v)) if v is not None else 0


def coverage(series: pd.Series) -> float:
    """Fraction of non-null values — native Python float, 3 dp."""
    return float(round(float(series.notna().mean()), 3))


def compute_stats(group: pd.DataFrame) -> dict:
    """
    Median stats + coverage for one (type, geo-level) group.
    Input data must already be p99-capped at disaster-type level.
    All values are native Python int / float — safe for json.dump().
    """
    return {
        "median_deaths":        _to_int(safe_median(group[COL_DEATHS])),
        "median_injuries":      _to_int(safe_median(group[COL_INJURED])),
        "median_affected":      _to_int(safe_median(group[COL_AFFECTED])),
        "median_damage_000usd": _to_int(safe_median(group[COL_DAMAGE])),
        "n_events":             int(len(group)),
        "deaths_coverage":      coverage(group[COL_DEATHS]),
        "injuries_coverage":    coverage(group[COL_INJURED]),
        "affected_coverage":    coverage(group[COL_AFFECTED]),
        "damage_coverage":      coverage(group[COL_DAMAGE]),
    }

# ---------------------------------------------------------------------------
# Load + clean
# ---------------------------------------------------------------------------

def load_and_clean(csv_path: Path) -> pd.DataFrame:
    """
    Load CSV, normalise Disaster Type, assert Natural group,
    drop fully-unlocation-able rows, filter to 8 valid types.
    """
    log.info("Loading: %s", csv_path)
    df = pd.read_csv(csv_path, low_memory=False)
    log.info("  Raw shape: %d rows x %d cols", *df.shape)

    # Strip whitespace — CSV has 'Extreme temperature ' with a trailing space
    df[COL_TYPE] = df[COL_TYPE].str.strip()

    # Safety assertion: the full dataset is already Natural (confirmed by inspect_data.py)
    n_natural = (df[COL_GROUP] == "Natural").sum()
    if n_natural != len(df):
        log.warning("Expected all rows Natural, got %d/%d — filtering.", n_natural, len(df))
        df = df[df[COL_GROUP] == "Natural"].copy()

    # Drop rows with no location data at all (lat AND lon AND country all missing)
    # Country is 0% missing here — this guard is a safety net for future dataset exports
    no_loc = df[COL_LAT].isna() & df[COL_LON].isna() & df[COL_COUNTRY].isna()
    if no_loc.sum():
        log.warning("Dropping %d rows with no lat/lon and no country.", no_loc.sum())
        df = df[~no_loc].copy()

    # Filter to the 8 types we support (7 others: Epidemic, Fog, Glacial lake outburst, etc.)
    before = len(df)
    df = df[df[COL_TYPE].isin(VALID_DISASTER_TYPES)].copy()
    log.info(
        "  After type filter: %d rows kept, %d dropped (unsupported types)",
        len(df), before - len(df),
    )
    return df


def apply_p99_caps(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cap IMPACT_COLS at the 99th-percentile computed per disaster type globally.

    p99 is computed at disaster-type level (not country/region) so that small
    subgroups share the same cap as the global type distribution.
    This prevents a country with 3 extreme events from having its own p99 floored
    unrealistically low.
    """
    df = df.copy()
    for col in IMPACT_COLS:
        p99_by_type = df.groupby(COL_TYPE)[col].quantile(0.99).to_dict()
        for dtype, cap in p99_by_type.items():
            if pd.notna(cap):
                mask = df[COL_TYPE] == dtype
                df.loc[mask, col] = df.loc[mask, col].clip(upper=cap)
    log.info("  p99 caps applied to: %s", ", ".join(IMPACT_COLS))
    return df

# ---------------------------------------------------------------------------
# Builder 1 — emdat_stats.json  (Phase 2 Step 3a)
# ---------------------------------------------------------------------------

def build_emdat_stats(df: pd.DataFrame) -> dict:
    """
    3-tier impact statistics dictionary.

    Structure:
      {
        "global":     { disaster_type: stats_dict },
        "by_country": { country:       { disaster_type: stats_dict } },
        "by_region":  { region:        { disaster_type: stats_dict } }
      }

    All (country, type) and (region, type) pairs with n_events >= 1 are written.
    The n >= 5 trust threshold is enforced at READ time inside
    emdat_lookup.resolve_impact_stats() — not here.
    """
    log.info("Building emdat_stats.json ...")
    out: dict = {"global": {}, "by_country": {}, "by_region": {}}

    # Global tier
    for dtype, grp in df.groupby(COL_TYPE, sort=True):
        out["global"][str(dtype)] = compute_stats(grp)
    log.info("  global:     %d disaster types", len(out["global"]))

    # Country tier
    for (country, dtype), grp in df.groupby([COL_COUNTRY, COL_TYPE], sort=True):
        c, t = str(country), str(dtype)
        out["by_country"].setdefault(c, {})[t] = compute_stats(grp)
    log.info("  by_country: %d countries with data", len(out["by_country"]))

    # Region tier  (COL_REGION = sub-continental, e.g. "Western Africa")
    for (region, dtype), grp in df.groupby([COL_REGION, COL_TYPE], sort=True):
        r, t = str(region), str(dtype)
        out["by_region"].setdefault(r, {})[t] = compute_stats(grp)
    log.info("  by_region:  %d regions with data", len(out["by_region"]))

    return out

# ---------------------------------------------------------------------------
# Stubs — Steps 3b through 3g (implement in subsequent prompts)
# ---------------------------------------------------------------------------

def build_secondary_disasters(df: pd.DataFrame) -> dict:
    """
    {disaster_type: [{type, count}]}
    Uses COL_ASSOC1 only. Threshold: >= 50 co-occurrences. Sorted descending.
    """
    log.info("Building secondary_disasters.json ...")
    out: dict = {}
    for dtype, grp in df.groupby(COL_TYPE, sort=True):
        counts = (
            grp[COL_ASSOC1]
            .dropna()
            .str.strip()
            .value_counts()
        )
        associations = [
            {"type": str(assoc_type), "count": int(cnt)}
            for assoc_type, cnt in counts.items()
            if int(cnt) >= 50
        ]
        if associations:
            out[str(dtype)] = associations
    log.info("  secondary_disasters: %d types with associations >= 50", len(out))
    return out


def build_seasonal_peaks(df: pd.DataFrame) -> dict:
    """
    {disaster_type: [month_numbers]}
    Peak = months where event count >= 1.2 × (total events / 12).
    Only rows with a non-null Start Month are counted.
    """
    log.info("Building seasonal_peaks.json ...")
    out: dict = {}
    for dtype, grp in df.groupby(COL_TYPE, sort=True):
        monthly = grp[COL_MONTH].dropna()
        if monthly.empty:
            out[str(dtype)] = []
            continue
        counts = monthly.value_counts().reindex(range(1, 13), fill_value=0)
        threshold = (len(monthly) / 12) * 1.2
        peak_months = sorted(int(m) for m, c in counts.items() if c >= threshold)
        out[str(dtype)] = peak_months
    log.info("  seasonal_peaks: %d types written", len(out))
    return out


def build_insurance_ratios(df: pd.DataFrame) -> dict:
    """
    {disaster_type: float}
    median(COL_INSURED / COL_DAMAGE) where both non-null and DAMAGE > 0.
    Ratio clipped to [0, 1]. Types with no usable rows are OMITTED.
    """
    log.info("Building insurance_ratios.json ...")
    out: dict = {}
    for dtype, grp in df.groupby(COL_TYPE, sort=True):
        mask = grp[COL_INSURED].notna() & grp[COL_DAMAGE].notna() & (grp[COL_DAMAGE] > 0)
        usable = grp[mask]
        if usable.empty:
            continue
        ratios = (usable[COL_INSURED] / usable[COL_DAMAGE]).clip(0, 1)
        out[str(dtype)] = round(float(np.nanmedian(ratios.values)), 4)
    log.info("  insurance_ratios: %d types with usable rows", len(out))
    return out


def build_trends(df: pd.DataFrame) -> dict:
    """
    {decades: [1950, 1960, ...], disaster_type: [count_per_decade, ...]}
    Decade range: 1950–2020 (8 values). Rows outside this range excluded.
    """
    log.info("Building trends.json ...")
    DECADES = list(range(1950, 2030, 10))   # 1950, 1960, ..., 2020 → 8 decades
    df_range = df[df[COL_YEAR].between(1950, 2029)].copy()
    df_range["decade"] = (df_range[COL_YEAR] // 10 * 10).astype(int)

    out: dict = {"decades": DECADES}
    for dtype, grp in df_range.groupby(COL_TYPE, sort=True):
        decade_counts = grp["decade"].value_counts().reindex(DECADES, fill_value=0)
        out[str(dtype)] = [int(decade_counts[d]) for d in DECADES]
    log.info("  trends: %d disaster types, %d decades", len(out) - 1, len(DECADES))
    return out


def build_continent_stats(df: pd.DataFrame) -> dict:
    """
    {continent: {total_events, top_disaster, median_deaths, median_damage_000usd}}
    Uses COL_CONTINENT. Medians computed on p99-capped data.
    """
    log.info("Building continent_stats.json ...")
    out: dict = {}
    for continent, grp in df.groupby(COL_CONTINENT, sort=True):
        top_disaster = str(grp[COL_TYPE].value_counts().idxmax())
        events_by_type = {
            str(t): int(ct)
            for t, ct in grp[COL_TYPE].value_counts().items()
        }
        out[str(continent)] = {
            "total_events":        int(len(grp)),
            "top_disaster":        top_disaster,
            "median_deaths":       _to_int(safe_median(grp[COL_DEATHS])),
            "median_damage_000usd": _to_int(safe_median(grp[COL_DAMAGE])),
            "events_by_type":      events_by_type,
        }
    log.info("  continent_stats: %d continents", len(out))
    return out


def _parse_coord(raw: object) -> float | None:
    """
    Parse one EM-DAT lat/lon cell. The raw CSV has two quirks (Phase 3 session notes):
      1. Directional strings: '34.01 N', '78.46 W ', '35.28 S' → cardinal letters S/W → negative
      2. Out-of-range floats: '36100.0' etc. — DMS artefacts — must be rejected
    Returns float or None. Caller decides what to do with None.
    """
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip()
    if not s:
        return None
    # Directional notation: pull out [SNWE], compute sign, then float the rest.
    direction = ""
    if s and s[-1] in "NSEW":
        direction = s[-1]
        s = s[:-1].strip()
    elif " " in s and s.split()[-1] in {"N", "S", "E", "W"}:
        parts = s.split()
        direction = parts[-1]
        s = " ".join(parts[:-1])
    s = s.rstrip(". ").replace(" ", "")
    try:
        val = float(s)
    except ValueError:
        return None
    if direction in ("S", "W"):
        val = -val
    return val


def build_risk_map(df: pd.DataFrame, points_per_type: int = 80, seed: int = 42) -> list[dict]:
    """
    Up to `points_per_type` heat points per disaster type, drawn from rows with
    valid in-range lat/lon. Each point is:
        {"lat": float, "lon": float, "risk_score": float (0-100), "disaster_type": str}

    risk_score formula matches CLAUDE.md / emdat-lookup-usage.md (probability term
    fixed at 1.0 since these are historical events, not predictions):

        risk = (norm_deaths * 0.35 + norm_affected * 0.30 +
                norm_damage * 0.20 + 1.0 * 0.15) * 100

    Each impact metric is normalised against the disaster type's P99 cap, so the
    score is comparable across types. The dataframe is already P99-capped here.
    """
    log.info("Building risk_map.json ...")
    rng = np.random.default_rng(seed)

    work = df.copy()
    work[COL_LAT] = work[COL_LAT].map(_parse_coord)
    work[COL_LON] = work[COL_LON].map(_parse_coord)
    work = work.dropna(subset=[COL_LAT, COL_LON])
    work = work[
        work[COL_LAT].between(-90, 90, inclusive="both") &
        work[COL_LON].between(-180, 180, inclusive="both")
    ]

    points: list[dict] = []
    for dtype, grp in work.groupby(COL_TYPE, sort=True):
        if grp.empty:
            continue

        deaths_p99   = float(grp[COL_DEATHS].max())   or 1.0   # already P99-capped
        affected_p99 = float(grp[COL_AFFECTED].max()) or 1.0
        damage_p99   = float(grp[COL_DAMAGE].max())   or 1.0

        # Sample with weight = events' total absolute impact (so high-impact
        # rows are over-represented but everywhere with disasters gets a chance).
        weights = (
            (grp[COL_DEATHS].fillna(0)   / deaths_p99) +
            (grp[COL_AFFECTED].fillna(0) / affected_p99) +
            (grp[COL_DAMAGE].fillna(0)   / damage_p99) +
            0.01  # floor so zero-impact rows still have a tiny chance
        ).clip(lower=0).to_numpy()
        if weights.sum() == 0:
            weights = np.ones(len(grp))
        weights = weights / weights.sum()

        n_take = min(points_per_type, len(grp))
        idx = rng.choice(len(grp), size=n_take, replace=False, p=weights)

        def _safe(v: object) -> float:
            try:
                f = float(v)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return 0.0
            return 0.0 if math.isnan(f) else f

        for i in idx:
            row = grp.iloc[int(i)]
            d = _safe(row[COL_DEATHS])   / deaths_p99
            a = _safe(row[COL_AFFECTED]) / affected_p99
            m = _safe(row[COL_DAMAGE])   / damage_p99
            risk = (min(d, 1.0) * 0.35 + min(a, 1.0) * 0.30 +
                    min(m, 1.0) * 0.20 + 1.0 * 0.15) * 100.0
            points.append({
                "lat":           round(float(row[COL_LAT]), 4),
                "lon":           round(float(row[COL_LON]), 4),
                "risk_score":    round(risk, 1),
                "disaster_type": str(dtype),
            })

    rng.shuffle(points)  # mix types so the front-end renders a varied heat blob
    log.info("  risk_map: %d points across %d disaster types",
             len(points), len({p["disaster_type"] for p in points}))
    return points


def build_timeseries(df: pd.DataFrame) -> dict:
    """
    by_year:   years 1960–2021 (62 entries per type)
    by_decade: decades 1900–2020 (13 entries per type: 1900, 1910, ..., 2020)
    events = raw count.
    deaths / affected / damage_000usd = median (NEVER mean). None when no data.
    Zero-event years/decades → {year/decade: X, events: 0, deaths: null, ...}
    """
    log.info("Building timeseries.json ...")

    YEARS   = list(range(1960, 2022))       # 62 values: 1960–2021
    DECADES = list(range(1900, 2021, 10))   # 13 values: 1900–2020

    def _ni(v: float | None) -> int | None:
        return _to_int(v) if v is not None else None

    by_year:   dict = {}
    by_decade: dict = {}

    df2 = df.copy()
    df2["decade"] = (df2[COL_YEAR] // 10 * 10).astype(int)

    for dtype, grp in df.groupby(COL_TYPE, sort=True):
        dtype_str = str(dtype)
        grp2 = df2[df2[COL_TYPE] == dtype]

        # — by_year —
        year_map = {
            int(yr): g
            for yr, g in grp[grp[COL_YEAR].between(1960, 2021)].groupby(COL_YEAR)
        }
        rows_year = []
        for yr in YEARS:
            if yr in year_map:
                g = year_map[yr]
                rows_year.append({
                    "year":          yr,
                    "events":        int(len(g)),
                    "deaths":        _ni(safe_median(g[COL_DEATHS])),
                    "affected":      _ni(safe_median(g[COL_AFFECTED])),
                    "damage_000usd": _ni(safe_median(g[COL_DAMAGE])),
                })
            else:
                rows_year.append({"year": yr, "events": 0, "deaths": None, "affected": None, "damage_000usd": None})
        by_year[dtype_str] = rows_year

        # — by_decade —
        decade_map = {int(dec): g for dec, g in grp2.groupby("decade")}
        rows_dec = []
        for dec in DECADES:
            if dec in decade_map:
                g = decade_map[dec]
                rows_dec.append({
                    "decade":        dec,
                    "events":        int(len(g)),
                    "deaths":        _ni(safe_median(g[COL_DEATHS])),
                    "affected":      _ni(safe_median(g[COL_AFFECTED])),
                    "damage_000usd": _ni(safe_median(g[COL_DAMAGE])),
                })
            else:
                rows_dec.append({"decade": dec, "events": 0, "deaths": None, "affected": None, "damage_000usd": None})
        by_decade[dtype_str] = rows_dec

    # — by_continent_decade —
    # Continent × disaster-type × decade matrix, same shape as by_decade per cell.
    by_continent_decade: dict = {}
    for (continent, dtype), cgrp in df2.groupby([COL_CONTINENT, COL_TYPE], sort=True):
        cont_str, dtype_str = str(continent), str(dtype)
        decade_map = {int(dec): g for dec, g in cgrp.groupby("decade")}
        cont_rows = []
        for dec in DECADES:
            if dec in decade_map:
                g = decade_map[dec]
                cont_rows.append({
                    "decade":        dec,
                    "events":        int(len(g)),
                    "deaths":        _ni(safe_median(g[COL_DEATHS])),
                    "affected":      _ni(safe_median(g[COL_AFFECTED])),
                    "damage_000usd": _ni(safe_median(g[COL_DAMAGE])),
                })
            else:
                cont_rows.append({
                    "decade": dec, "events": 0,
                    "deaths": None, "affected": None, "damage_000usd": None,
                })
        by_continent_decade.setdefault(cont_str, {})[dtype_str] = cont_rows

    log.info("  by_year:              %d types x %d years each", len(by_year), len(YEARS))
    log.info("  by_decade:            %d types x %d decades each", len(by_decade), len(DECADES))
    log.info("  by_continent_decade:  %d continents", len(by_continent_decade))
    return {"by_year": by_year, "by_decade": by_decade,
            "by_continent_decade": by_continent_decade}

# ---------------------------------------------------------------------------
# Builder 9 — countries.json  (continent -> country list with fixed centroids)
# ---------------------------------------------------------------------------

def build_countries(df: pd.DataFrame) -> dict:
    """Continent → list of selectable countries, each with a fixed centroid.

    Powers the frontend cascading continent→country picker. `name` is the EXACT
    EM-DAT country string (so the backend country-tier impact lookup hits) and
    matches the by_country keys in emdat_stats.json (same df, same read). `label`
    is a cleaned display string. Countries without an ISO3 centroid are omitted.

    Output:
      {
        "default": {continent, name, label, lat, lon},   # most-data-rich country
        "continents": { <continent>: [ {name, label, iso, lat, lon, n_events} ] }
      }
    Each continent list is sorted by n_events desc, then label asc.
    """
    log.info("Building countries.json ...")

    agg = (
        df.dropna(subset=[COL_COUNTRY])
        .groupby(COL_COUNTRY)
        .agg(
            iso=(COL_ISO,       lambda x: x.dropna().mode().iloc[0] if x.dropna().size else None),
            cont=(COL_CONTINENT, lambda x: x.dropna().mode().iloc[0] if x.dropna().size else None),
            n=(COL_COUNTRY, "size"),
        )
        .reset_index()
    )

    continents: dict[str, list] = {}
    for _, r in agg.iterrows():
        iso = str(r["iso"]).strip().upper() if r["iso"] is not None else ""
        centroid = _ISO3_CENTROIDS.get(iso)
        if centroid is None or r["cont"] is None:
            continue  # drop countries with no stable centroid (historical/aggregate codes)
        lat, lon = centroid
        cont = str(r["cont"])
        entry = {
            "name":     str(r[COL_COUNTRY]),
            "label":    _clean_country_label(r[COL_COUNTRY]),
            "iso":      iso,
            "lat":      round(float(lat), 4),
            "lon":      round(float(lon), 4),
            "n_events": int(r["n"]),
        }
        continents.setdefault(cont, []).append(entry)

    for cont in continents:
        continents[cont].sort(key=lambda e: (-e["n_events"], e["label"]))

    # Default = the single most data-rich country across all continents.
    default_entry = max(
        (e for lst in continents.values() for e in lst),
        key=lambda e: e["n_events"],
    )
    default = {
        "continent": next(c for c, lst in continents.items() if default_entry in lst),
        "name":      default_entry["name"],
        "label":     default_entry["label"],
        "lat":       default_entry["lat"],
        "lon":       default_entry["lon"],
    }

    total = sum(len(v) for v in continents.values())
    log.info("  countries: %d across %d continents (default: %s)",
             total, len(continents), default["label"])
    return {"default": default, "continents": continents}


# ---------------------------------------------------------------------------
# I/O helper
# ---------------------------------------------------------------------------

def write_json(data: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2, ensure_ascii=False)
    log.info("  Wrote %-40s  %.1f KB", path.name, path.stat().st_size / 1024)

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    # Actual filename on disk confirmed by scripts/inspect_data.py.
    # CLAUDE.md lists an incorrect name ('1900_2021_DISASTERS_xlsx_-_train_data.csv') —
    # the real file is '1900_2021_DISASTERS.xlsx - train data.csv'.
    default_csv = Path("data/train/1900_2021_DISASTERS.xlsx - train data.csv")
    p = argparse.ArgumentParser(
        description="Generate 7 precomputed JSON files from the EM-DAT train CSV."
    )
    p.add_argument(
        "--train-csv", type=Path, default=default_csv,
        help="Path to EM-DAT train CSV  (default: %(default)s)",
    )
    p.add_argument(
        "--out-dir", type=Path, default=Path("data/generated"),
        help="Output directory for JSON files  (default: %(default)s)",
    )
    return p.parse_args()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    if not args.train_csv.exists():
        log.error("CSV not found: %s", args.train_csv)
        sys.exit(1)

    args.out_dir.mkdir(parents=True, exist_ok=True)

    df = load_and_clean(args.train_csv)
    df = apply_p99_caps(df)
    log.info(
        "Dataset ready: %d rows | %d disaster types",
        len(df), df[COL_TYPE].nunique(),
    )

    log.info("=" * 55)

    # ── File 1 — emdat_stats.json ─────────────────────────────────────────
    emdat_stats = build_emdat_stats(df)
    out_path = args.out_dir / "emdat_stats.json"
    write_json(emdat_stats, out_path)
    log.info(
        "  SUMMARY | types: %d | countries: %d | regions: %d | rows: %d | %.1f KB",
        len(emdat_stats["global"]),
        len(emdat_stats["by_country"]),
        len(emdat_stats["by_region"]),
        len(df),
        out_path.stat().st_size / 1024,
    )

    # ── Files 2–8 — Steps 3b–3g + risk_map ───────────────────────────────
    for name, fn in [
        ("secondary_disasters.json", build_secondary_disasters),
        ("seasonal_peaks.json",      build_seasonal_peaks),
        ("insurance_ratios.json",    build_insurance_ratios),
        ("trends.json",              build_trends),
        ("continent_stats.json",     build_continent_stats),
        ("timeseries.json",          build_timeseries),
        ("risk_map.json",            build_risk_map),
        ("countries.json",           build_countries),
    ]:
        data = fn(df)
        write_json(data, args.out_dir / name)

    log.info("=" * 55)
    log.info("Phase 2 Steps 3a–3g + risk_map + countries done. All 9 JSON files written to %s", args.out_dir)


if __name__ == "__main__":
    main()
