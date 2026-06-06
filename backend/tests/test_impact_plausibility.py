"""
Unit tests for the type-aware + plausible impact logic in ml.predictor.

These exercise the pure helpers directly — no models, no DB, no pkl files.
They lock in the two guarantees added this phase:
  1. Impact varies by disaster type (EM-DAT type-specific medians drive the blend).
  2. deaths <= injured <= affected always holds (zeros allowed where appropriate).
"""
from __future__ import annotations

import pytest

from ml import predictor


# ── _apply_plausibility — ordering guarantee ─────────────────────────────────

@pytest.mark.parametrize("dtype", [
    "Flood", "Storm", "Earthquake", "Wildfire",
    "Volcanic activity", "Landslide", "Drought", "Extreme temperature",
])
def test_ordering_holds_for_all_types(dtype):
    # Deliberately broken input: deaths > injured, affected tiny.
    d, i, a = predictor._apply_plausibility(dtype, deaths=10, injuries=1, affected=2)
    assert d <= i <= a, f"{dtype}: ordering violated ({d}, {i}, {a})"


def test_egypt_flood_case_is_repaired():
    # The reported regression: deaths=2, injured=1 (deaths > injured).
    d, i, a = predictor._apply_plausibility("Flood", deaths=2, injuries=1, affected=453)
    assert d <= i <= a
    assert i >= d  # injured can no longer be below deaths


def test_zeros_preserved_when_no_deaths():
    # Drought with 0 deaths: floors keyed off deaths stay 0; affected from EM-DAT.
    d, i, a = predictor._apply_plausibility("Drought", deaths=0, injuries=0, affected=500_000)
    assert d == 0 and i == 0
    assert a == 500_000


def test_drought_affected_dwarfs_deaths_when_deaths_present():
    # Droughts cause few direct injuries but huge affected populations.
    d, i, a = predictor._apply_plausibility("Drought", deaths=30, injuries=0, affected=0)
    assert d <= i <= a
    assert a >= d * 100, "drought affected should dwarf deaths once deaths > 0"


def test_floors_only_raise_never_lower():
    # If the model already exceeds the floors, they are left untouched.
    d, i, a = predictor._apply_plausibility("Earthquake", deaths=5, injuries=9999, affected=10**6)
    assert (d, i, a) == (5, 9999, 10**6)


# ── _blend_and_constrain_impact — type sensitivity ───────────────────────────

def test_blend_differs_by_disaster_type():
    """Same ML signal + different EM-DAT medians → different outputs.

    This is the core fix: predict() was type-blind because it used raw
    regressors. The blend now mixes in disaster-type-specific EM-DAT medians.
    """
    ml_vals = {"deaths": 4, "injuries": 4, "affected": 100, "damage_k": 1_000}

    flood_emdat = {
        "median_deaths": 16, "median_injuries": 5,
        "median_affected": 30_000, "median_damage_000usd": 200_000,
    }
    quake_emdat = {
        "median_deaths": 60, "median_injuries": 200,
        "median_affected": 2_000, "median_damage_000usd": 500_000,
    }

    flood = predictor._blend_and_constrain_impact("Flood", ml_vals, flood_emdat)
    quake = predictor._blend_and_constrain_impact("Earthquake", ml_vals, quake_emdat)

    assert flood != quake, "blend must differ by disaster type"
    # Both still satisfy ordering on (deaths, injured, affected).
    for deaths, injuries, affected, _damage in (flood, quake):
        assert deaths <= injuries <= affected


def test_blend_handles_empty_emdat_stats():
    # Missing/None medians must not crash and must still be ordered.
    ml_vals = {"deaths": 3, "injuries": 2, "affected": 50, "damage_k": 10}
    d, i, a, dmg = predictor._blend_and_constrain_impact("Storm", ml_vals, {})
    assert d <= i <= a
    assert dmg >= 0
