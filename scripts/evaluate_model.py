"""
Reusable model evaluation utility for the SafeEarth disaster classifier.

Public API:
    evaluate(y_true, y_proba, class_names, model_name="model") -> dict
        Takes ground-truth integer labels and predicted probabilities.
        Prints full classification report, macro F1, weighted F1, and a
        per-class F1 table sorted worst-to-best.
        Returns a JSON-serialisable metrics dict.

Macro F1 is the PRIMARY metric for this project — rare disaster types
(Landslide, Drought, Volcanic activity) matter as much as common ones.

Standalone run (no flags):
    py -3.12 scripts/evaluate_model.py
    -> Loads v4.1 saved models, predicts on the 1970-2021 holdout test set,
       writes metrics/baseline_v4_1_metrics.json.
"""
from __future__ import annotations

import json
import re
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, f1_score
from sklearn.preprocessing import LabelEncoder

warnings.filterwarnings("ignore")


# ── PUBLIC: reusable evaluation function ─────────────────────────────────────

def evaluate(
    y_true: np.ndarray | Sequence[int],
    y_proba: np.ndarray,
    class_names: Sequence[str],
    model_name: str = "model",
) -> dict:
    """Evaluate a multiclass classifier against ground truth.

    Args:
        y_true:      shape (n,) — integer class indices (0..n_classes-1).
        y_proba:     shape (n, n_classes) — predicted probabilities.
        class_names: list of class names in column order of y_proba.
        model_name:  identifier printed in the report header and stored in
                     the returned dict.

    Returns:
        JSON-serialisable dict with macro_f1 (PRIMARY), weighted_f1, accuracy,
        per-class F1 sorted worst-to-best, and the full sklearn report as dict.
    """
    y_true  = np.asarray(y_true)
    y_proba = np.asarray(y_proba)
    y_pred  = np.argmax(y_proba, axis=1)

    n_samples = int(len(y_true))
    n_classes = len(class_names)

    # ── Header + full sklearn classification report ─────────────────────────
    print()
    print("=" * 70)
    print(f"Evaluation: {model_name}   |   n={n_samples:,}   classes={n_classes}")
    print("=" * 70)
    report_text = classification_report(
        y_true, y_pred,
        target_names=class_names,
        zero_division=0,
        digits=4,
    )
    print(report_text)

    # ── Aggregate metrics ───────────────────────────────────────────────────
    macro_f1    = float(f1_score(y_true, y_pred, average="macro",    zero_division=0))
    weighted_f1 = float(f1_score(y_true, y_pred, average="weighted", zero_division=0))
    accuracy    = float((y_true == y_pred).mean())

    # ── Per-class F1, sorted worst-to-best ──────────────────────────────────
    per_class_f1 = f1_score(
        y_true, y_pred,
        labels=list(range(n_classes)),
        average=None,
        zero_division=0,
    )
    supports = np.bincount(y_true, minlength=n_classes)

    per_class_sorted = sorted(
        [
            {
                "class":   name,
                "f1":      round(float(f), 4),
                "support": int(supports[i]),
            }
            for i, (name, f) in enumerate(zip(class_names, per_class_f1))
        ],
        key=lambda r: r["f1"],
    )

    print("Per-class F1 (worst -> best):")
    print(f"  {'class':<22s}  {'f1':>7s}  {'n':>6s}")
    print(f"  {'-'*22}  {'-'*7}  {'-'*6}")
    for row in per_class_sorted:
        print(f"  {row['class']:<22s}  {row['f1']:>7.4f}  {row['support']:>6,d}")

    print()
    print(f"  PRIMARY    Macro F1   : {macro_f1:.4f}")
    print(f"  SECONDARY  Weighted F1: {weighted_f1:.4f}")
    print(f"             Accuracy   : {accuracy:.4f}")
    print()

    # ── Build full report dict for JSON storage ─────────────────────────────
    report_dict = classification_report(
        y_true, y_pred,
        target_names=class_names,
        zero_division=0,
        output_dict=True,
    )

    return {
        "model_name":            model_name,
        "primary_metric":        "macro_f1",
        "macro_f1":              round(macro_f1, 4),
        "weighted_f1":           round(weighted_f1, 4),
        "accuracy":              round(accuracy, 4),
        "n_samples":             n_samples,
        "n_classes":             n_classes,
        "class_names":           list(class_names),
        "per_class_f1_sorted":   per_class_sorted,
        "classification_report": report_dict,
    }


# ── Private helpers for the standalone v4.1 baseline run ─────────────────────

VALID_DISASTER_TYPES = [
    "Flood", "Storm", "Earthquake", "Wildfire",
    "Volcanic activity", "Landslide", "Drought", "Extreme temperature",
]


def _parse_coord(val) -> float:
    """Match scripts/run_training.py:parse_coord — handles directional notation."""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return np.nan
    s = str(val).strip().rstrip(".")
    try:
        return float(s)
    except ValueError:
        pass
    m = re.match(r"^([0-9.]+)\s*([NSEWnsew])\s*$", s)
    if m:
        num_str, direction = m.group(1).rstrip("."), m.group(2).upper()
        try:
            num = float(num_str)
            return -num if direction in ("S", "W") else num
        except ValueError:
            pass
    return np.nan


def _safe_encode(le: LabelEncoder, values) -> np.ndarray:
    known = set(le.classes_)
    return np.array(
        [le.transform([v])[0] if v in known else 0 for v in values],
        dtype=np.int32,
    )


def _preprocess_test_for_v4_1(test_csv: Path, bundle: dict):
    """Recreate the 16-feature matrix used in scripts/run_training.py.

    Returns (X_test, y_test, class_names) where the column order of X_test
    matches bundle["feature_names"] exactly.
    """
    feature_names: list[str] = bundle["feature_names"]
    le_continent: LabelEncoder = bundle["le_continent"]
    le_region:    LabelEncoder = bundle["le_region"]
    le_country:   LabelEncoder = bundle["le_country"]
    le_target:    LabelEncoder = bundle["le_target"]
    region_freq_map: dict = bundle["region_freq_map"]

    df_t = pd.read_csv(test_csv, encoding="latin-1")
    df_t["Disaster Type"] = df_t["Disaster Type"].str.strip()
    df_t = df_t[df_t["Disaster Type"].isin(VALID_DISASTER_TYPES)].reset_index(drop=True)

    # lat / lon: parse + impute by Country -> Continent -> global median
    for col, (lo, hi) in [("Latitude", (-90.0, 90.0)), ("Longitude", (-180.0, 180.0))]:
        df_t[col] = df_t[col].apply(_parse_coord)
        df_t.loc[(df_t[col] < lo) | (df_t[col] > hi), col] = np.nan
        df_t[col] = df_t[col].fillna(df_t.groupby("Country")[col].transform("median"))
        df_t[col] = df_t[col].fillna(df_t.groupby("Continent")[col].transform("median"))
        df_t[col] = df_t[col].fillna(df_t[col].median())

    df_t["latitude"]     = df_t["Latitude"]
    df_t["longitude"]    = df_t["Longitude"]
    df_t["abs_latitude"] = df_t["latitude"].abs()
    df_t["lon_sin"]      = np.sin(2 * np.pi * df_t["longitude"] / 360)
    df_t["lon_cos"]      = np.cos(2 * np.pi * df_t["longitude"] / 360)

    raw_month = df_t["Start Month"].fillna(6).astype(int)
    df_t["month_sin"] = np.sin(2 * np.pi * raw_month / 12)
    df_t["month_cos"] = np.cos(2 * np.pi * raw_month / 12)

    df_t["decade"]          = (df_t["Year"] // 10) * 10
    df_t["historical_freq"] = df_t["Region"].map(region_freq_map).fillna(1).astype(int)
    df_t["log_hist_freq"]   = np.log1p(df_t["historical_freq"])
    df_t["has_magnitude"]   = df_t["Dis Mag Value"].notna().astype(int)
    df_t["dis_mag_value"]   = pd.to_numeric(df_t["Dis Mag Value"], errors="coerce").fillna(0.0)
    df_t["day_offset"]      = 0

    df_t["continent_enc"] = _safe_encode(le_continent, df_t["Continent"])
    df_t["region_enc"]    = _safe_encode(le_region,    df_t["Region"])
    df_t["country_enc"]   = _safe_encode(le_country,   df_t["Country"])

    # Restrict to rows whose disaster_type is one of the trained classes
    known = set(le_target.classes_)
    mask  = df_t["Disaster Type"].isin(known)
    df_t  = df_t[mask].reset_index(drop=True)

    X_test = df_t[feature_names].values.astype(np.float32)
    assert np.isnan(X_test).sum() == 0, "NaNs in test feature matrix"

    y_test = le_target.transform(df_t["Disaster Type"])
    return X_test, y_test, list(le_target.classes_)


def _v4_1_ensemble_proba(X_test: np.ndarray, bundle: dict) -> np.ndarray:
    """Reproduce the v4.1 soft ensemble: w_xgb*XGB + w_lgb*LGB + w_cat*CAT."""
    feature_names = bundle["feature_names"]
    xgb_p = bundle["model"].predict_proba(X_test)

    proba = float(bundle["xgb_weight"]) * xgb_p

    if bundle.get("lgb_model") is not None and float(bundle.get("lgb_weight", 0.0)) > 0:
        X_df  = pd.DataFrame(X_test, columns=feature_names)
        lgb_p = bundle["lgb_model"].predict_proba(X_df)
        proba = proba + float(bundle["lgb_weight"]) * lgb_p

    if bundle.get("cat_model") is not None and float(bundle.get("cat_weight", 0.0)) > 0:
        cat_p = bundle["cat_model"].predict_proba(X_test)
        proba = proba + float(bundle["cat_weight"]) * cat_p

    return proba


def _main() -> None:
    ROOT        = Path(__file__).resolve().parent.parent
    TEST_CSV    = ROOT / "data" / "test" / "1970-2021_DISASTERS.xlsx - test data.csv"
    MODELS_DIR  = ROOT / "backend" / "saved_models"
    METRICS_DIR = ROOT / "metrics"
    OUT_PATH    = METRICS_DIR / "baseline_v4_1_metrics.json"

    METRICS_DIR.mkdir(exist_ok=True)

    print(f"Loading v4.1 bundle from {MODELS_DIR.relative_to(ROOT)} ...")
    bundle = joblib.load(MODELS_DIR / "disaster_predictor.pkl")
    print(f"  feature_names: {len(bundle['feature_names'])} features")
    print(f"  ensemble    : XGB={bundle.get('xgb_weight', 1.0):.2f} "
          f"+ LGB={bundle.get('lgb_weight', 0.0):.2f} "
          f"+ CAT={bundle.get('cat_weight', 0.0):.2f}")

    print(f"\nPreprocessing test CSV: {TEST_CSV.relative_to(ROOT)}")
    X_test, y_test, class_names = _preprocess_test_for_v4_1(TEST_CSV, bundle)
    print(f"  X_test: {X_test.shape}   classes: {class_names}")

    print("\nRunning ensemble prediction ...")
    y_proba = _v4_1_ensemble_proba(X_test, bundle)

    metrics = evaluate(y_test, y_proba, class_names, model_name="v4.1")

    # Augment with deployment metadata for future-you reading the JSON
    metrics["timestamp_utc"]    = datetime.now(timezone.utc).isoformat()
    metrics["model_version"]    = "v4.1"
    metrics["ensemble_weights"] = {
        "xgb": round(float(bundle.get("xgb_weight", 1.0)), 4),
        "lgb": round(float(bundle.get("lgb_weight", 0.0)), 4),
        "cat": round(float(bundle.get("cat_weight", 0.0)), 4),
    }
    metrics["feature_names"]    = list(bundle["feature_names"])
    metrics["test_csv"]         = str(TEST_CSV.relative_to(ROOT)).replace("\\", "/")
    metrics["pkl_sizes_kb"]     = {
        f.name: round(f.stat().st_size / 1024)
        for f in sorted(MODELS_DIR.glob("*.pkl"))
    }

    OUT_PATH.write_text(json.dumps(metrics, indent=2))
    print(f"Saved baseline -> {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    _main()
