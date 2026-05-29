"""
Persist v4.2 to backend/saved_models/.

v4.2 = v4.1 classifier ensemble with two changes:
  - LightGBM dropped entirely  (lgb_model = None, lgb_weight = 0.0)
  - Ensemble weights now XGB=0.60, CAT=0.40  (from prior macro-F1 weight tuning)

XGBoost and CatBoost are retrained from scratch on the full train set with the
v4.1 hand-tuned per-class sample weights (Drought=4, Landslide=3, Wildfire=2.5,
Volcanic=3.0, Extreme=1.5, Flood=1, Storm=1, Earthquake=1) and the v4.1
hyperparameters. random_state=42 for reproducibility — same model that
metrics/minority_strategies_v4_2.json reported with macro F1 = 0.7052.

SHAP TreeExplainer is rebuilt for the new XGB.
impact_regressor.pkl is NOT touched (impact regressors are independent of the
classifier ensemble composition).

The v4.1 pkl files are renamed to *_v4_1_backup.pkl before being overwritten,
so the previous bundle can be restored if anything goes wrong.

Usage:
  py -3.12 scripts/persist_v4_2.py
"""
from __future__ import annotations

import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import shap

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_model import _preprocess_test_for_v4_1  # noqa: E402
from train_minority_strategies import (  # noqa: E402
    HAND_WEIGHTS, W_CAT, W_XGB, make_cat, make_xgb,
)


def main() -> None:
    ROOT       = Path(__file__).resolve().parent.parent
    TRAIN_CSV  = ROOT / "data" / "train" / "1900_2021_DISASTERS.xlsx - train data.csv"
    MODELS_DIR = ROOT / "backend" / "saved_models"

    BUNDLE_PATH   = MODELS_DIR / "disaster_predictor.pkl"
    SHAP_PATH     = MODELS_DIR / "shap_explainer.pkl"
    BUNDLE_BACKUP = MODELS_DIR / "disaster_predictor_v4_1_backup.pkl"
    SHAP_BACKUP   = MODELS_DIR / "shap_explainer_v4_1_backup.pkl"

    # ── 1. Load existing v4.1 bundle (for encoders + region_freq_map) ────
    print("Loading v4.1 bundle (encoders + region_freq_map) ...")
    old = joblib.load(BUNDLE_PATH)
    le_target   = old["le_target"]
    class_names = list(le_target.classes_)
    print(f"  classes: {class_names}")
    print(f"  v4.1 weights: XGB={old['xgb_weight']}  LGB={old['lgb_weight']}  CAT={old['cat_weight']}")

    # ── 2. Preprocess train CSV using v4.1's fitted encoders ─────────────
    print("\nPreprocessing train CSV ...")
    X_train, y_train, _ = _preprocess_test_for_v4_1(TRAIN_CSV, old)
    print(f"  X_train: {X_train.shape}   y_train: {y_train.shape}")

    # ── 3. Hand-tuned per-class sample weights (v4.1's CUSTOM_CLASS_WEIGHTS) ─
    classes_str = le_target.inverse_transform(y_train)
    sample_weights = np.array(
        [HAND_WEIGHTS[c] for c in classes_str],
        dtype=np.float32,
    )

    # ── 4. Fit XGB and CatBoost ──────────────────────────────────────────
    print("\nFitting XGBoost ...")
    xgb_new = make_xgb()
    xgb_new.fit(X_train, y_train, sample_weight=sample_weights)
    print("  done.")

    print("Fitting CatBoost ...")
    cat_new = make_cat()
    cat_new.fit(X_train, y_train, sample_weight=sample_weights)
    print("  done.")

    # ── 5. Rebuild SHAP TreeExplainer for the new XGB ────────────────────
    print("\nBuilding SHAP TreeExplainer for new XGB ...")
    explainer = shap.TreeExplainer(xgb_new)
    print("  done.")

    # ── 6. Backup v4.1 pkl files (only if backups don't already exist) ───
    print("\nBacking up v4.1 pkl files ...")
    if not BUNDLE_BACKUP.exists():
        joblib.dump(old, BUNDLE_BACKUP)
        print(f"  saved {BUNDLE_BACKUP.name} ({BUNDLE_BACKUP.stat().st_size // 1024:,} KB)")
    else:
        print(f"  {BUNDLE_BACKUP.name} already exists — keeping existing backup")

    if not SHAP_BACKUP.exists():
        old_shap = joblib.load(SHAP_PATH)
        joblib.dump(old_shap, SHAP_BACKUP)
        print(f"  saved {SHAP_BACKUP.name} ({SHAP_BACKUP.stat().st_size // 1024:,} KB)")
    else:
        print(f"  {SHAP_BACKUP.name} already exists — keeping existing backup")

    # ── 7. Save new v4.2 bundle ──────────────────────────────────────────
    print("\nSaving v4.2 bundle ...")
    new_bundle = {
        "model":             xgb_new,
        "lgb_model":         None,            # explicitly dropped in v4.2
        "cat_model":         cat_new,
        "xgb_weight":        float(W_XGB),    # 0.60
        "lgb_weight":        0.0,
        "cat_weight":        float(W_CAT),    # 0.40
        "le_continent":      old["le_continent"],
        "le_region":         old["le_region"],
        "le_country":        old["le_country"],
        "le_target":         old["le_target"],
        "region_freq_map":   old["region_freq_map"],
        "feature_names":     old["feature_names"],
        "targets_are_log1p": old.get("targets_are_log1p", True),
        "version":           "v4.2",
        "trained_at":        datetime.now(timezone.utc).isoformat(),
    }
    joblib.dump(new_bundle, BUNDLE_PATH)
    joblib.dump(explainer, SHAP_PATH)

    # ── 8. Report final file sizes ───────────────────────────────────────
    print("\nFinal contents of backend/saved_models/:")
    for f in sorted(MODELS_DIR.glob("*.pkl")):
        print(f"  {f.name:<42s}  {f.stat().st_size // 1024:>8,} KB")

    print("\nDone. Remember to:")
    print("  1. Update backend/ml/predictor.py: MODEL_VERSION = 'v4.2'")
    print("  2. Run: py -3.12 -m pytest backend/tests/test_predictions.py")


if __name__ == "__main__":
    main()
