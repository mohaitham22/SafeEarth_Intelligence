"""
v4.2 model constants — single source of truth for ML metrics exposed via GET /admin/model-stats.
The frontend admin page reads this via the API instead of hardcoding.
"""
from __future__ import annotations

MODEL_VERSION = "v4.2"

# Ensemble weights
ENSEMBLE = {"XGBoost": 0.60, "CatBoost": 0.40}

# Holdout evaluation (test set 1970–2021, n=13,070)
MACRO_F1    = 0.7052
WEIGHTED_F1 = 0.7587
ACCURACY    = 0.7467

FEATURE_COUNT = 16
FEATURE_NAMES = [
    "latitude", "longitude", "abs_latitude",
    "continent_enc", "region_enc", "country_enc",
    "month_sin", "month_cos",
    "dis_mag_value", "has_magnitude",
    "historical_freq", "log_hist_freq",
    "decade", "day_offset",
    # Two additional encoded features resolved at inference:
    # (country-derived region_enc / country_enc are set by _resolve_location_features)
]

# Per-class F1 on holdout
PER_CLASS_F1 = [
    {"type": "Earthquake",         "f1": 0.976, "support": 1137},
    {"type": "Flood",              "f1": 0.778, "support": 5272},
    {"type": "Storm",              "f1": 0.771, "support": 4005},
    {"type": "Extreme temperature","f1": 0.749, "support":  584},
    {"type": "Volcanic activity",  "f1": 0.668, "support":  222},
    {"type": "Wildfire",           "f1": 0.628, "support":  452},
    {"type": "Drought",            "f1": 0.589, "support":  685},
    {"type": "Landslide",          "f1": 0.482, "support":  713},
]
