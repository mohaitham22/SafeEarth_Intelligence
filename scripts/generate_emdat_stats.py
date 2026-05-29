"""
scripts/generate_emdat_stats.py

Run ONCE before first deployment. Reads the EM-DAT train CSV.
Writes all 7 precomputed JSON files to data/generated/.

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
        out[str(continent)] = {
            "total_events":        int(len(grp)),
            "top_disaster":        top_disaster,
            "median_deaths":       _to_int(safe_median(grp[COL_DEATHS])),
            "median_damage_000usd": _to_int(safe_median(grp[COL_DAMAGE])),
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

    log.info("  by_year:   %d types x %d years each", len(by_year), len(YEARS))
    log.info("  by_decade: %d types x %d decades each", len(by_decade), len(DECADES))
    return {"by_year": by_year, "by_decade": by_decade}

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
    ]:
        data = fn(df)
        write_json(data, args.out_dir / name)

    log.info("=" * 55)
    log.info("Phase 2 Steps 3a–3g + risk_map done. All 8 JSON files written to %s", args.out_dir)


if __name__ == "__main__":
    main()
