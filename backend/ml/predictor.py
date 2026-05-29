"""
backend/ml/predictor.py

ML model loader and single-function inference entry point.
All business logic (EM-DAT lookup, risk score, uninsured loss) lives here.

Cardinal rules — any violation breaks the 2-5 second latency budget:
  - joblib.load()          NEVER inside a route or service function
  - shap.TreeExplainer()   NEVER instantiated per-request (cached at startup)
  - predict()              NEVER called from a router (service layer only)
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import joblib
import numpy as np

# ── Module-level variables — None until load_models() runs at startup ─────────
_classifier               = None   # XGBClassifier (tuned, Optuna v4.1)
_lgb_classifier           = None   # LGBMClassifier (tuned, Optuna v4.1) — None for older bundles
_cat_classifier           = None   # CatBoostClassifier (tuned, Optuna v4.1) — None for older bundles
_regressors: dict | None  = None   # {"deaths", "injuries", "affected", "damage"}
_shap_explainer           = None   # shap.TreeExplainer — cached, NEVER re-instantiated per request
_bundle: dict | None      = None   # full disaster_predictor.pkl dict (encoders + metadata)
_avg_historical_freq: int = 100    # precomputed mean of region_freq_map at startup
_xgb_weight: float        = 1.0   # soft ensemble weight for XGBoost
_lgb_weight: float        = 0.0   # soft ensemble weight for LightGBM
_cat_weight: float        = 0.0   # soft ensemble weight for CatBoost

MODEL_VERSION = "v4.2"

# Feature names — must match FEATURE_NAMES in scripts/run_training.py exactly (16 features, v4.1)
# frac_* features were dropped (v4 experiment showed they hurt XGBoost generalization)
_FEATURE_NAMES = [
    "latitude", "longitude",
    "abs_latitude",           # v3: distance from equator (climate zone proxy)
    "lon_sin", "lon_cos",    # v3: cyclical longitude
    "continent_enc", "region_enc", "country_enc",
    "month_sin", "month_cos",
    "dis_mag_value", "has_magnitude",
    "historical_freq", "log_hist_freq",  # v3: log1p(historical_freq)
    "decade", "day_offset",
]

# Season -> representative month number (mid-season).
# Accepts season names (case-insensitive) or integer months 1-12.
_SEASON_TO_MONTH: dict[str, int] = {
    "spring": 4,
    "summer": 7,
    "autumn": 10,
    "fall":   10,
    "winter":  1,
}

# Per-disaster-type approximate 99th-percentile impact values from EM-DAT 1900-2021.
# Used ONLY for normalising the 0-100 composite risk score — never shown to users.
# damage_usd values are in full USD (regressor output in thousands USD x 1000).
_EMDAT_P99: dict[str, dict] = {
    "Flood":               {"deaths": 10_000, "affected": 15_000_000, "damage_usd": 4_000_000_000},
    "Storm":               {"deaths":  4_000, "affected":  2_000_000, "damage_usd": 6_000_000_000},
    "Earthquake":          {"deaths": 15_000, "affected":  1_000_000, "damage_usd": 3_000_000_000},
    "Drought":             {"deaths":  2_000, "affected": 50_000_000, "damage_usd": 1_000_000_000},
    "Wildfire":            {"deaths":     50, "affected":     50_000, "damage_usd":   500_000_000},
    "Landslide":           {"deaths":    500, "affected":    100_000, "damage_usd":    50_000_000},
    "Volcanic activity":   {"deaths":    500, "affected":    200_000, "damage_usd":   100_000_000},
    "Extreme temperature": {"deaths":  2_000, "affected":    500_000, "damage_usd":   200_000_000},
}

_P99_FALLBACK = {"deaths": 10_000, "affected": 10_000_000, "damage_usd": 2_000_000_000}


# ── Startup loader ─────────────────────────────────────────────────────────────

_PKL_FILES = ["disaster_predictor.pkl", "impact_regressor.pkl", "shap_explainer.pkl"]


def _ensure_models_downloaded(
    saved_models_dir: Path,
    repo_id: str,
    token: str,
) -> None:
    """Download any missing .pkl files from Hugging Face Hub.

    Silently skips when:
      - All three files already exist locally (local dev / warm Render instance).
      - repo_id is empty (creds not configured — local dev without HF).

    Raises:
        RuntimeError: if repo_id is set but the download fails (fatal on Render).
    """
    missing = [f for f in _PKL_FILES if not (saved_models_dir / f).exists()]
    if not missing:
        return  # nothing to do

    if not repo_id:
        # No HF credentials configured — the FileNotFoundError below will surface a
        # clear message asking the developer to run the training script.
        return

    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise RuntimeError(
            "huggingface_hub is not installed. Add it to requirements.txt."
        ) from exc

    saved_models_dir.mkdir(parents=True, exist_ok=True)
    for filename in missing:
        print(f"  Downloading {filename} from HuggingFace ({repo_id})…")
        hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            local_dir=str(saved_models_dir),
            token=token or None,  # None = public repo (no auth header sent)
        )
        print(f"  ✓ {filename} downloaded")


def load_models(
    saved_models_dir: Path,
    huggingface_repo_id: str = "",
    huggingface_token: str = "",
) -> None:
    """Load all 3 pkl files into module-level variables.

    Called ONCE in the FastAPI lifespan context manager in main.py.
    Never call from a route function or service function.

    Downloads missing files from HuggingFace Hub before loading when
    huggingface_repo_id is set (required for Render deployments).

    Raises:
        FileNotFoundError: if any pkl file is still missing after the download
                           attempt, with instructions to run training.
    """
    global _classifier, _lgb_classifier, _cat_classifier, _regressors, _shap_explainer
    global _bundle, _avg_historical_freq, _xgb_weight, _lgb_weight, _cat_weight

    _ensure_models_downloaded(saved_models_dir, huggingface_repo_id, huggingface_token)

    for filename in _PKL_FILES:
        path = saved_models_dir / filename
        if not path.exists():
            raise FileNotFoundError(
                f"Missing model file: {path}\n"
                f"Run: py -3.12 scripts/run_training.py from the project root.\n"
                f"Or set HUGGINGFACE_REPO_ID + HUGGINGFACE_TOKEN for automatic download."
            )

    _bundle         = joblib.load(saved_models_dir / "disaster_predictor.pkl")
    _classifier     = _bundle["model"]
    _lgb_classifier = _bundle.get("lgb_model")           # None for v1/v2/v3 bundles
    _cat_classifier = _bundle.get("cat_model")           # None for v1/v2/v3 bundles
    _xgb_weight     = float(_bundle.get("xgb_weight", 1.0))
    _lgb_weight     = float(_bundle.get("lgb_weight", 0.0))
    _cat_weight     = float(_bundle.get("cat_weight", 0.0))
    _regressors     = joblib.load(saved_models_dir / "impact_regressor.pkl")
    _shap_explainer = joblib.load(saved_models_dir / "shap_explainer.pkl")

    freq_map = _bundle.get("region_freq_map", {})
    _avg_historical_freq = int(sum(freq_map.values()) / len(freq_map)) if freq_map else 100

    n_features = len(_bundle.get("feature_names", _FEATURE_NAMES))
    models_desc = []
    if _xgb_weight > 0:
        models_desc.append(f"XGB*{_xgb_weight:.2f}")
    if _lgb_classifier is not None and _lgb_weight > 0:
        models_desc.append(f"LGB*{_lgb_weight:.2f}")
    if _cat_classifier is not None and _cat_weight > 0:
        models_desc.append(f"CAT*{_cat_weight:.2f}")
    ensemble_desc = " + ".join(models_desc) if len(models_desc) > 1 else (models_desc[0] if models_desc else "XGBoost only")

    print(f"  Classifier   : {type(_classifier).__name__} [{ensemble_desc}]")
    print(f"  Regressors   : {list(_regressors.keys())}")
    print(f"  Features     : {n_features}")
    print(f"  Avg hist freq: {_avg_historical_freq}")


# ── Public helpers ─────────────────────────────────────────────────────────────

def get_historical_freq(region: str) -> int:
    """Return historical event count for a region from the training bundle.

    Returns 1 (not 0) for unknown regions so the feature is never zero.
    """
    if _bundle is None:
        return 1
    return _bundle.get("region_freq_map", {}).get(region, 1)


# ── Public inference function ──────────────────────────────────────────────────

def predict(
    lat: float,
    lon: float,
    disaster_type: str,
    magnitude: Optional[float],
    season: str | int,
    continent: str,
    day_offset: int = 0,
    *,
    country: Optional[str] = None,
    region: Optional[str] = None,
) -> dict:
    """Run full prediction pipeline for a specified disaster type.

    Returns a complete dict with all CLAUDE.md Feature 1 fields — ready
    for predictor_service.py to persist to DB and return to the router.
    Never call this from a router.

    Args:
        lat, lon:       WGS-84 coordinates.
        disaster_type:  One of the 8 valid EM-DAT types (stripped automatically).
        magnitude:      Disaster magnitude (Richter / Kph / Km² / °C) or None.
        season:         Season name ("spring"/"summer"/"autumn"/"fall"/"winter")
                        or integer month 1-12, or a string digit e.g. "7".
        continent:      Continent name as it appears in the EM-DAT training data.
        day_offset:     0 for a single prediction; 0-29 for 30-day forecast rows.
        country:        Optional country name for 3-tier EM-DAT lookup.
        region:         Optional EM-DAT region name for type-fraction lookup (v4).

    Raises:
        RuntimeError: if load_models() was not called at startup.
        ValueError:   if disaster_type is not one of the 8 valid EM-DAT types.
    """
    if _classifier is None:
        raise RuntimeError(
            "Models not loaded — load_models() must run in the FastAPI lifespan at startup."
        )

    # Disaster type string must be stripped (CSV has 'Extreme temperature ' with trailing space)
    disaster_type = disaster_type.strip()

    classes: list[str] = list(_bundle["le_target"].classes_)
    if disaster_type not in classes:
        raise ValueError(
            f"Unknown disaster type: {disaster_type!r}. "
            f"Valid types: {classes}"
        )

    # ── Build feature vector ──────────────────────────────────────────────────
    month = _parse_season(season)
    month_sin = float(np.sin(2 * np.pi * month / 12))
    month_cos = float(np.cos(2 * np.pi * month / 12))

    has_magnitude = 1 if magnitude is not None else 0
    mag_value     = float(magnitude) if magnitude is not None else 0.0
    decade        = (datetime.now(timezone.utc).year // 10) * 10

    hf     = float(_avg_historical_freq)
    log_hf = float(np.log1p(hf))

    features = np.array([[
        lat, lon,
        abs(lat),                              # abs_latitude
        float(np.sin(2 * np.pi * lon / 360)), # lon_sin
        float(np.cos(2 * np.pi * lon / 360)), # lon_cos
        _safe_encode(_bundle["le_continent"], continent),
        0,                                     # region_enc — not provided; 0 = first-class fallback
        0,                                     # country_enc — not provided; same fallback
        month_sin, month_cos,
        mag_value, has_magnitude,
        hf, log_hf,                            # historical_freq, log_hist_freq
        decade,
        day_offset,
    ]], dtype=np.float32)

    # ── Classification — soft ensemble (XGBoost + optional LGB + optional CAT) ─
    proba = _xgb_weight * _classifier.predict_proba(features)[0]

    if _lgb_classifier is not None and _lgb_weight > 0:
        import pandas as _pd  # noqa: PLC0415
        features_df = _pd.DataFrame(features, columns=_FEATURE_NAMES)
        proba += _lgb_weight * _lgb_classifier.predict_proba(features_df)[0]

    if _cat_classifier is not None and _cat_weight > 0:
        import pandas as _pd  # noqa: PLC0415
        features_df = _pd.DataFrame(features, columns=_FEATURE_NAMES)
        proba += _cat_weight * _cat_classifier.predict_proba(features_df)[0]

    class_idx   = classes.index(disaster_type)
    probability = float(proba[class_idx])

    severity = _probability_to_severity(probability)

    # ── Impact regression ──────────────────────────────────────────────────────
    # Targets were log1p-transformed at training time -> must expm1 + clip(min=0).
    estimated_deaths   = max(0, int(np.expm1(_regressors["deaths"].predict(features)[0])))
    estimated_injuries = max(0, int(np.expm1(_regressors["injuries"].predict(features)[0])))
    estimated_affected = max(0, int(np.expm1(_regressors["affected"].predict(features)[0])))
    estimated_damage_k = max(0, int(np.expm1(_regressors["damage"].predict(features)[0])))
    # estimated_damage_k is in thousands USD (matches training target units and DB column)

    # ── SHAP — cached XGBoost explainer, NEVER re-instantiated per request ────
    shap_values      = _shap_explainer.shap_values(features)
    shap_explanation = _extract_top_shap(shap_values, class_idx)

    # ── EM-DAT 3-tier impact lookup ────────────────────────────────────────────
    from ml import emdat_lookup  # noqa: PLC0415
    try:
        impact_stats = emdat_lookup.resolve_impact_stats(disaster_type, country=country)
    except KeyError:
        impact_stats = {"data_source": "global", "country_used": country, "n_events": 0}

    # ── Uninsured loss ─────────────────────────────────────────────────────────
    insurance_ratio = emdat_lookup.get_insurance_ratio(disaster_type)
    uninsured_loss  = int(estimated_damage_k * (1 - insurance_ratio))

    # ── Risk score (0-100 composite, CLAUDE.md formula) ───────────────────────
    risk_score = _compute_risk_score(
        disaster_type = disaster_type,
        deaths        = estimated_deaths,
        affected      = estimated_affected,
        damage_k      = estimated_damage_k,
        probability   = probability,
    )

    # ── Contextual enrichment ──────────────────────────────────────────────────
    secondary_warning = emdat_lookup.get_secondary_warning(disaster_type)
    seasonal_peaks    = emdat_lookup.get_seasonal_peaks(disaster_type)

    return {
        "disaster_type":               disaster_type,
        "probability_score":           probability,
        "severity_level":              severity,
        "risk_score":                  risk_score,
        "estimated_deaths":            estimated_deaths,
        "estimated_injuries":          estimated_injuries,
        "estimated_affected":          estimated_affected,
        "estimated_damage_usd":        estimated_damage_k,   # thousands USD
        "uninsured_loss_usd":          uninsured_loss,        # thousands USD
        "shap_explanation":            shap_explanation,
        "secondary_disaster_warning":  secondary_warning,
        "seasonal_peak_months":        seasonal_peaks,
        "data_quality":                "full",
        "data_source":                 impact_stats.get("data_source", "global"),
        "country_used":                impact_stats.get("country_used"),
        "n_events":                    impact_stats.get("n_events", 0),
    }


# ── Additional public inference functions (no DB write) ────────────────────────

def classify_all_types(
    lat: float,
    lon: float,
    magnitude: Optional[float],
    season: "str | int",
    continent: str,
    year: int,
    day_offset: int = 0,
    *,
    country: Optional[str] = None,
    region: Optional[str] = None,
) -> dict:
    """Return ranked probabilities for all 8 disaster types.

    Unlike predict(), this does NOT save to DB and does NOT take disaster_type
    as input — it scores every type and returns them ranked.
    """
    if _classifier is None:
        raise RuntimeError(
            "Models not loaded — load_models() must run in the FastAPI lifespan at startup."
        )
    features = _build_feature_vector(lat, lon, magnitude, season, continent, year, day_offset)
    proba = _run_ensemble(features)
    classes: list[str] = list(_bundle["le_target"].classes_)
    ranked = sorted(
        [{"disaster_type": c, "probability": float(p)} for c, p in zip(classes, proba)],
        key=lambda x: x["probability"],
        reverse=True,
    )
    return {
        "ranked": ranked,
        "top_type": ranked[0]["disaster_type"],
        "top_probability": ranked[0]["probability"],
        "model_version": MODEL_VERSION,
    }


def predict_impact(
    lat: float,
    lon: float,
    season: "str | int",
    continent: str,
    year: int,
    day_offset: int = 0,
    *,
    country: Optional[str] = None,
    region: Optional[str] = None,
) -> dict:
    """Auto-select top disaster type and return impact estimates.

    Does NOT save to DB and does NOT require disaster_type as input.
    The top type is determined by argmax of the ensemble probability.

    Impact estimates blend two signals:
      - ML regressors: location-aware (lat/lon/continent/season/decade) but
        NOT disaster-type-aware — same 16 features as the classifier.
      - EM-DAT 3-tier medians: disaster-type-specific historical ground truth,
        looked up at country → region → global tier.
    Blend weights match per-field EM-DAT data coverage:
      deaths/affected ~73% coverage → 70% EM-DAT + 30% ML
      injuries        ~26% coverage → 30% EM-DAT + 70% ML
      damage          ~33% coverage → 35% EM-DAT + 65% ML
    """
    if _classifier is None:
        raise RuntimeError(
            "Models not loaded — load_models() must run in the FastAPI lifespan at startup."
        )
    features = _build_feature_vector(lat, lon, None, season, continent, year, day_offset)
    proba = _run_ensemble(features)
    classes: list[str] = list(_bundle["le_target"].classes_)
    top_idx = int(np.argmax(proba))
    top_type = classes[top_idx]
    top_prob = float(proba[top_idx])

    # ML regressor raw outputs — location-aware, NOT disaster-type-aware.
    ml_deaths   = max(0, int(np.expm1(_regressors["deaths"].predict(features)[0])))
    ml_injuries = max(0, int(np.expm1(_regressors["injuries"].predict(features)[0])))
    ml_affected = max(0, int(np.expm1(_regressors["affected"].predict(features)[0])))
    ml_damage_k = max(0, int(np.expm1(_regressors["damage"].predict(features)[0])))

    # EM-DAT 3-tier medians — disaster-type-specific, historically grounded.
    from ml import emdat_lookup  # noqa: PLC0415
    try:
        impact_stats = emdat_lookup.resolve_impact_stats(top_type, country=country)
    except KeyError:
        impact_stats = {"data_source": "global", "country_used": country, "n_events": 0}

    emdat_deaths   = int(impact_stats.get("median_deaths",        0) or 0)
    emdat_injuries = int(impact_stats.get("median_injuries",      0) or 0)
    emdat_affected = int(impact_stats.get("median_affected",      0) or 0)
    emdat_damage_k = int(impact_stats.get("median_damage_000usd", 0) or 0)

    # Blend: coverage-weighted combination of both signals.
    estimated_deaths   = int(0.70 * emdat_deaths   + 0.30 * ml_deaths)
    estimated_injuries = int(0.30 * emdat_injuries + 0.70 * ml_injuries)
    estimated_affected = int(0.70 * emdat_affected + 0.30 * ml_affected)
    estimated_damage_k = int(0.35 * emdat_damage_k + 0.65 * ml_damage_k)

    hist_freq = get_historical_freq(region or "")
    expected_events = max(0, round(top_prob * hist_freq))

    insurance_ratio = emdat_lookup.get_insurance_ratio(top_type)
    uninsured_loss  = int(estimated_damage_k * (1 - insurance_ratio))

    return {
        "predicted_disaster_type": top_type,
        "probability":             top_prob,
        "expected_events":         expected_events,
        "estimated_deaths":        estimated_deaths,
        "estimated_injuries":      estimated_injuries,
        "estimated_affected":      estimated_affected,
        "estimated_damage_usd":    estimated_damage_k,
        "uninsured_loss_usd":      uninsured_loss,
        "data_source":             impact_stats.get("data_source", "global"),
        "model_version":           MODEL_VERSION,
    }


# ── Private helpers ────────────────────────────────────────────────────────────

def _build_feature_vector(
    lat: float,
    lon: float,
    magnitude: Optional[float],
    season: "str | int",
    continent: str,
    year: int,
    day_offset: int = 0,
) -> np.ndarray:
    """Build the 16-element feature array used by classify_all_types and predict_impact."""
    month     = _parse_season(season)
    month_sin = float(np.sin(2 * np.pi * month / 12))
    month_cos = float(np.cos(2 * np.pi * month / 12))
    has_magnitude = 1 if magnitude is not None else 0
    mag_value     = float(magnitude) if magnitude is not None else 0.0
    decade        = (year // 10) * 10
    hf            = float(_avg_historical_freq)
    log_hf        = float(np.log1p(hf))
    return np.array([[
        lat, lon,
        abs(lat),
        float(np.sin(2 * np.pi * lon / 360)),
        float(np.cos(2 * np.pi * lon / 360)),
        _safe_encode(_bundle["le_continent"], continent),
        0, 0,          # region_enc, country_enc — fallback to 0 (unknown)
        month_sin, month_cos,
        mag_value, has_magnitude,
        hf, log_hf,
        decade,
        day_offset,
    ]], dtype=np.float32)


def _run_ensemble(features: np.ndarray) -> np.ndarray:
    """Soft-vote across XGB + optional LGB + optional CAT. Returns class probability array."""
    proba = _xgb_weight * _classifier.predict_proba(features)[0]
    if _lgb_classifier is not None and _lgb_weight > 0:
        import pandas as _pd  # noqa: PLC0415
        features_df = _pd.DataFrame(features, columns=_FEATURE_NAMES)
        proba += _lgb_weight * _lgb_classifier.predict_proba(features_df)[0]
    if _cat_classifier is not None and _cat_weight > 0:
        import pandas as _pd  # noqa: PLC0415
        features_df = _pd.DataFrame(features, columns=_FEATURE_NAMES)
        proba += _cat_weight * _cat_classifier.predict_proba(features_df)[0]
    return proba


def _parse_season(season: str | int) -> int:
    """Convert a season name or month number to a month integer 1-12."""
    if isinstance(season, int):
        return max(1, min(12, season))
    s = str(season).strip().lower()
    if s in _SEASON_TO_MONTH:
        return _SEASON_TO_MONTH[s]
    try:
        return max(1, min(12, int(s)))
    except (ValueError, TypeError):
        raise ValueError(
            f"Unrecognised season: {season!r}. "
            f"Valid values: {list(_SEASON_TO_MONTH)} or integer month 1-12."
        )


def _probability_to_severity(p: float) -> str:
    """Map probability to severity label using CLAUDE.md thresholds (fixed — do not change)."""
    if p <= 0.30:
        return "Low"
    if p <= 0.55:
        return "Medium"
    if p <= 0.75:
        return "High"
    return "Critical"


def _compute_risk_score(
    disaster_type: str,
    deaths: int,
    affected: int,
    damage_k: int,       # thousands USD
    probability: float,
) -> float:
    """Composite 0-100 risk score (CLAUDE.md formula)."""
    p99 = _EMDAT_P99.get(disaster_type, _P99_FALLBACK)

    damage_usd = damage_k * 1000

    norm_deaths   = min(deaths     / p99["deaths"],     1.0)
    norm_affected = min(affected   / p99["affected"],   1.0)
    norm_damage   = min(damage_usd / p99["damage_usd"], 1.0)

    raw = (
        norm_deaths   * 0.35
        + norm_affected * 0.30
        + norm_damage   * 0.20
        + probability   * 0.15
    )
    return round(raw * 100, 1)


def _safe_encode(le, value: str) -> int:
    """Encode a categorical value; map unseen categories to 0 instead of raising."""
    try:
        return int(le.transform([value])[0])
    except (ValueError, AttributeError):
        return 0


def _extract_top_shap(shap_values, class_idx: int) -> list[dict]:
    """Extract top-3 SHAP features as % of total absolute SHAP sum.

    Multi-class XGBoost TreeExplainer returns shape (n_samples, n_features, n_classes).
    We slice for the requested class_idx to explain why THIS type was predicted.
    """
    if hasattr(shap_values, "ndim") and shap_values.ndim == 3:
        vals = np.abs(shap_values[0, :, class_idx])
    else:
        vals = np.abs(shap_values[0])

    total = vals.sum()
    if total == 0:
        return []

    # Use the feature names from the bundle if available (handles both v3 and v4 shapes)
    feature_names = _FEATURE_NAMES
    if _bundle is not None and "feature_names" in _bundle:
        feature_names = _bundle["feature_names"]

    # Pad or trim shap vals to match feature_names length
    n = len(feature_names)
    if len(vals) < n:
        vals = np.pad(vals, (0, n - len(vals)))
    else:
        vals = vals[:n]

    ranked = sorted(zip(feature_names, vals), key=lambda x: x[1], reverse=True)[:3]
    return [
        {"feature": name, "contribution_pct": round(float(v / total * 100), 1)}
        for name, v in ranked
    ]
