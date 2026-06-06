"""
scripts/tests/test_generation.py

Regression tests for the 7 precomputed JSON files in data/generated/.
Run AFTER scripts/generate_emdat_stats.py has been executed.
These tests do NOT re-run the script — they read from disk only.

Usage:
    pytest scripts/tests/ -v
    pytest scripts/tests/ -v -m data_generation
    pytest scripts/tests/ -v -m "not data_generation"   # skip in CI
"""
import json
import pytest
from pathlib import Path

GENERATED_DIR = Path(__file__).parent.parent.parent / "data" / "generated"

pytestmark = pytest.mark.data_generation

SEVEN_FILES = [
    "emdat_stats.json",
    "secondary_disasters.json",
    "seasonal_peaks.json",
    "insurance_ratios.json",
    "trends.json",
    "continent_stats.json",
    "timeseries.json",
]

STATS_KEYS = [
    "median_deaths",
    "median_injuries",
    "median_affected",
    "median_damage_000usd",
    "n_events",
    "deaths_coverage",
    "injuries_coverage",
    "affected_coverage",
    "damage_coverage",
]

COVERAGE_KEYS = [
    "deaths_coverage",
    "injuries_coverage",
    "affected_coverage",
    "damage_coverage",
]


def _load(name: str) -> dict:
    return json.loads((GENERATED_DIR / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Module-scoped fixtures — each JSON is loaded once per test session
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def emdat_stats():
    return _load("emdat_stats.json")


@pytest.fixture(scope="module")
def secondary_disasters():
    return _load("secondary_disasters.json")


@pytest.fixture(scope="module")
def seasonal_peaks():
    return _load("seasonal_peaks.json")


@pytest.fixture(scope="module")
def insurance_ratios():
    return _load("insurance_ratios.json")


@pytest.fixture(scope="module")
def trends():
    return _load("trends.json")


@pytest.fixture(scope="module")
def continent_stats():
    return _load("continent_stats.json")


@pytest.fixture(scope="module")
def timeseries():
    return _load("timeseries.json")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_all_seven_files_exist():
    for name in SEVEN_FILES:
        assert (GENERATED_DIR / name).exists(), f"Missing generated file: {name}"


def test_emdat_stats_structure(emdat_stats):
    assert set(emdat_stats.keys()) == {"global", "by_country", "by_region"}, (
        f"Top-level keys mismatch: {set(emdat_stats.keys())}"
    )
    flood = emdat_stats["global"]["Flood"]
    for key in STATS_KEYS:
        assert key in flood, f"global['Flood'] missing key: '{key}'"


def test_medians_are_not_means(emdat_stats):
    flood_deaths = emdat_stats["global"]["Flood"]["median_deaths"]
    assert flood_deaths > 0, (
        f"median_deaths={flood_deaths} — should be > 0"
    )
    assert flood_deaths < 200, (
        f"median_deaths={flood_deaths} looks like a mean (~1735). "
        "CLAUDE.md rule: NEVER use mean — always median."
    )


def test_coverage_values_in_range(emdat_stats):
    # global tier: {disaster_type: stats_dict}
    for dtype, stats in emdat_stats["global"].items():
        for key in COVERAGE_KEYS:
            val = stats[key]
            assert 0.0 <= val <= 1.0, (
                f"global[{dtype!r}][{key!r}] = {val} — out of [0.0, 1.0]"
            )
    # by_country and by_region: {geo: {disaster_type: stats_dict}}
    for tier in ("by_country", "by_region"):
        for geo, types in emdat_stats[tier].items():
            for dtype, stats in types.items():
                for key in COVERAGE_KEYS:
                    val = stats[key]
                    assert 0.0 <= val <= 1.0, (
                        f"{tier}[{geo!r}][{dtype!r}][{key!r}] = {val} — "
                        "out of [0.0, 1.0]"
                    )


def test_secondary_disasters_threshold(secondary_disasters):
    for dtype, associations in secondary_disasters.items():
        for entry in associations:
            assert entry["count"] >= 50, (
                f"{dtype}: association '{entry['type']}' has count={entry['count']} "
                "— below the >= 50 threshold"
            )


def test_seasonal_peaks_valid_months(seasonal_peaks):
    for dtype, months in seasonal_peaks.items():
        for m in months:
            assert 1 <= m <= 12, (
                f"{dtype}: month value {m} is outside valid range [1, 12]"
            )


def test_insurance_ratios_in_range(insurance_ratios):
    for dtype, ratio in insurance_ratios.items():
        assert isinstance(ratio, float), (
            f"{dtype}: ratio is {type(ratio).__name__}, expected float"
        )
        assert 0.0 <= ratio <= 1.0, (
            f"{dtype}: ratio={ratio} — out of [0.0, 1.0]"
        )


def test_trends_decade_alignment(trends):
    expected_decades = list(range(1950, 2030, 10))  # [1950, 1960, ..., 2020]
    assert trends["decades"] == expected_decades, (
        f"trends['decades'] mismatch.\n"
        f"  expected: {expected_decades}\n"
        f"  got:      {trends['decades']}"
    )
    n = len(trends["decades"])
    for dtype, counts in trends.items():
        if dtype == "decades":
            continue
        assert len(counts) == n, (
            f"trends[{dtype!r}] has {len(counts)} entries, "
            f"expected {n} (one per decade)"
        )


def test_continent_stats_has_top_disaster(continent_stats):
    for continent, stats in continent_stats.items():
        assert "top_disaster" in stats, (
            f"{continent}: missing 'top_disaster' key"
        )
        assert isinstance(stats["top_disaster"], str), (
            f"{continent}: top_disaster is {type(stats['top_disaster']).__name__}, "
            "expected str"
        )
        assert stats["top_disaster"] != "", (
            f"{continent}: top_disaster is an empty string"
        )


def test_continent_stats_has_events_by_type(continent_stats):
    for continent, stats in continent_stats.items():
        assert "events_by_type" in stats, (
            f"{continent}: missing 'events_by_type' key — re-run generate_emdat_stats.py"
        )
        ebt = stats["events_by_type"]
        assert isinstance(ebt, dict), (
            f"{continent}: events_by_type is {type(ebt).__name__}, expected dict"
        )
        assert len(ebt) > 0, (
            f"{continent}: events_by_type is empty"
        )
        for dtype, count in ebt.items():
            assert isinstance(count, int) and count > 0, (
                f"{continent}: events_by_type[{dtype!r}] = {count!r} — expected positive int"
            )
        # The top disaster must appear in events_by_type.
        top = stats["top_disaster"]
        assert top in ebt, (
            f"{continent}: top_disaster={top!r} not in events_by_type keys {list(ebt)}"
        )


def test_timeseries_has_continent_decade(timeseries):
    assert "by_continent_decade" in timeseries, (
        "timeseries.json missing 'by_continent_decade' — re-run generate_emdat_stats.py"
    )
    bcd = timeseries["by_continent_decade"]
    assert len(bcd) >= 5, f"Expected at least 5 continents, got {len(bcd)}"
    # Each continent must have Flood and Earthquake (two highest-event types globally).
    for continent, types_map in bcd.items():
        for dtype in ("Flood", "Earthquake"):
            assert dtype in types_map, (
                f"by_continent_decade[{continent!r}] missing {dtype!r}"
            )
            arr = types_map[dtype]
            assert len(arr) == 13, (
                f"by_continent_decade[{continent!r}][{dtype!r}] has {len(arr)} decades, expected 13"
            )
            assert arr[0]["decade"] == 1900 and arr[-1]["decade"] == 2020, (
                f"Decade range mismatch for {continent!r}/{dtype!r}"
            )


def test_timeseries_year_range(timeseries):
    flood_years = timeseries["by_year"]["Flood"]
    assert len(flood_years) == 62, (
        f"by_year['Flood'] has {len(flood_years)} entries, expected 62 (1960–2021)"
    )
    assert flood_years[0]["year"] == 1960, (
        f"First year is {flood_years[0]['year']}, expected 1960"
    )
    assert flood_years[-1]["year"] == 2021, (
        f"Last year is {flood_years[-1]['year']}, expected 2021"
    )

    flood_decades = timeseries["by_decade"]["Flood"]
    assert len(flood_decades) == 13, (
        f"by_decade['Flood'] has {len(flood_decades)} entries, expected 13 (1900–2020)"
    )
    assert flood_decades[0]["decade"] == 1900, (
        f"First decade is {flood_decades[0]['decade']}, expected 1900"
    )
    assert flood_decades[-1]["decade"] == 2020, (
        f"Last decade is {flood_decades[-1]['decade']}, expected 2020"
    )


# ---------------------------------------------------------------------------
# countries.json — continent→country picker with fixed centroids (this phase)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def countries():
    return _load("countries.json")


def test_countries_structure_and_default(countries):
    assert set(countries.keys()) == {"default", "continents"}

    default = countries["default"]
    for k in ("continent", "name", "label", "lat", "lon"):
        assert k in default, f"default missing {k}"
    # Default is the most data-rich country in the dataset (United States).
    assert "United States" in default["label"], default["label"]

    continents = countries["continents"]
    assert len(continents) == 5, f"expected 5 continents, got {list(continents)}"


def test_countries_entries_valid_and_sorted(countries):
    emdat = _load("emdat_stats.json")
    by_country = set(emdat["by_country"].keys())

    for cont, entries in countries["continents"].items():
        assert len(entries) > 0, f"{cont} empty"
        counts = [e["n_events"] for e in entries]
        assert counts == sorted(counts, reverse=True), f"{cont} not sorted by n_events desc"
        for e in entries:
            for k in ("name", "label", "iso", "lat", "lon", "n_events"):
                assert k in e, f"{cont} entry missing {k}: {e}"
            assert -90 <= e["lat"] <= 90, f"bad lat: {e}"
            assert -180 <= e["lon"] <= 180, f"bad lon: {e}"
            assert len(e["iso"]) == 3, f"ISO not 3 chars: {e}"
            # name must align with an EM-DAT by_country key (country-tier hit)
            assert e["name"] in by_country, f"name not an EM-DAT country: {e['name']!r}"
