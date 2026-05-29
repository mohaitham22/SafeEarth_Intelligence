"""
Tune the v4.1 soft-ensemble weights for MAXIMUM macro F1.

Why this script exists:
  The current weights (XGB=0.6, LGB=0.1, CAT=0.3) came from a coarse
  step=0.1 grid that constrained each weight to [0.1, 0.7] and ranked by
  ties with accuracy. Result: macro F1 regressed vs v3 (0.6929 vs 0.7106).
  Rare classes (Landslide, Drought, Wildfire) pay the price.

This script:
  1. Splits the test CSV 50/50 into val + holdout (stratified, random_state=42).
  2. Generates XGB/LGB/CAT predict_proba ONCE on each half (no retraining).
  3. Searches the (wx, wl, wc) simplex at step=0.05, each weight in [0, 1],
     sum=1.  231 combinations total. Picks the (wx, wl, wc) that maximizes
     macro F1 on the VALIDATION half.
  4. Evaluates the chosen weights on the HOLDOUT half via evaluate().
  5. Also evaluates the baseline weights on the same holdout half for a
     fair head-to-head comparison.
  6. Writes the full result to metrics/v4_1_macroF1_tuned_weights.json.

Does NOT modify backend/saved_models/*.pkl — read-only.
"""
from __future__ import annotations

import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score
from sklearn.model_selection import train_test_split

warnings.filterwarnings("ignore")

# Reuse helpers from evaluate_model.py
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_model import evaluate, _preprocess_test_for_v4_1  # noqa: E402


STEP_DENOM = 20  # step = 1 / 20 = 0.05


def grid_search_macro_f1(
    y_val: np.ndarray,
    p_xgb: np.ndarray,
    p_lgb: np.ndarray,
    p_cat: np.ndarray,
    step_denom: int = STEP_DENOM,
) -> tuple[float, float, float, float, int]:
    """Exhaustive search over (wx, wl, wc) with weights in [0,1] summing to 1.

    Returns (best_macro_f1, wx, wl, wc, n_combinations_tried).
    """
    best_macro = -1.0
    best_wx, best_wl, best_wc = 0.0, 0.0, 0.0
    n_tried = 0

    for wx_i in range(step_denom + 1):                    # 0..20  -> 0.00..1.00
        for wl_i in range(step_denom + 1 - wx_i):         # ensures wc_i >= 0
            wc_i = step_denom - wx_i - wl_i

            wx = wx_i / step_denom
            wl = wl_i / step_denom
            wc = wc_i / step_denom

            proba = wx * p_xgb + wl * p_lgb + wc * p_cat
            pred  = np.argmax(proba, axis=1)
            macro = f1_score(y_val, pred, average="macro", zero_division=0)

            if macro > best_macro:
                best_macro = float(macro)
                best_wx, best_wl, best_wc = wx, wl, wc

            n_tried += 1

    return best_macro, best_wx, best_wl, best_wc, n_tried


def _main() -> None:
    ROOT        = Path(__file__).resolve().parent.parent
    TEST_CSV    = ROOT / "data" / "test" / "1970-2021_DISASTERS.xlsx - test data.csv"
    MODELS_DIR  = ROOT / "backend" / "saved_models"
    METRICS_DIR = ROOT / "metrics"
    OUT_PATH    = METRICS_DIR / "v4_1_macroF1_tuned_weights.json"
    BASELINE    = METRICS_DIR / "baseline_v4_1_metrics.json"

    METRICS_DIR.mkdir(exist_ok=True)

    # ── 1. Load bundle and preprocess full test CSV ────────────────────────
    print("Loading v4.1 bundle and preprocessing test CSV ...")
    bundle = joblib.load(MODELS_DIR / "disaster_predictor.pkl")
    X_test, y_test, class_names = _preprocess_test_for_v4_1(TEST_CSV, bundle)
    print(f"  Test set: {X_test.shape}   classes: {len(class_names)}")

    # ── 2. Stratified 50/50 split: val + holdout ──────────────────────────
    X_val, X_hold, y_val, y_hold = train_test_split(
        X_test, y_test,
        test_size=0.5,
        stratify=y_test,
        random_state=42,
    )
    print(f"  Validation half: n={len(y_val):,}")
    print(f"  Holdout half   : n={len(y_hold):,}")

    # ── 3. Per-model predict_proba once on each half ──────────────────────
    feature_names = bundle["feature_names"]
    X_val_df  = pd.DataFrame(X_val,  columns=feature_names)
    X_hold_df = pd.DataFrame(X_hold, columns=feature_names)

    print("\nComputing per-model probabilities ...")
    p_xgb_val  = bundle["model"].predict_proba(X_val)
    p_xgb_hold = bundle["model"].predict_proba(X_hold)

    p_lgb_val  = bundle["lgb_model"].predict_proba(X_val_df)
    p_lgb_hold = bundle["lgb_model"].predict_proba(X_hold_df)

    p_cat_val  = bundle["cat_model"].predict_proba(X_val)
    p_cat_hold = bundle["cat_model"].predict_proba(X_hold)

    # ── 4. Grid search on validation half ─────────────────────────────────
    print(f"\nGrid search: step=0.05  (max {((STEP_DENOM+1)*(STEP_DENOM+2))//2} combos) ...")
    best_macro_val, best_wx, best_wl, best_wc, n_tried = grid_search_macro_f1(
        y_val, p_xgb_val, p_lgb_val, p_cat_val
    )
    print(f"  Combinations tried: {n_tried}")
    print(f"  Best on VAL: XGB={best_wx:.2f}  LGB={best_wl:.2f}  CAT={best_wc:.2f}")
    print(f"  VAL Macro F1 at tuned weights : {best_macro_val:.4f}")

    # Baseline (currently saved) weights — for reference on val
    cur_wx = float(bundle["xgb_weight"])
    cur_wl = float(bundle["lgb_weight"])
    cur_wc = float(bundle["cat_weight"])
    baseline_val_proba = cur_wx * p_xgb_val + cur_wl * p_lgb_val + cur_wc * p_cat_val
    baseline_val_macro = f1_score(
        y_val, np.argmax(baseline_val_proba, axis=1),
        average="macro", zero_division=0,
    )
    print(f"  VAL Macro F1 at baseline (XGB={cur_wx}/LGB={cur_wl}/CAT={cur_wc}) : {baseline_val_macro:.4f}")

    # ── 5. Evaluate BOTH on the holdout half ──────────────────────────────
    baseline_hold_proba = cur_wx * p_xgb_hold + cur_wl * p_lgb_hold + cur_wc * p_cat_hold
    tuned_hold_proba    = best_wx * p_xgb_hold + best_wl * p_lgb_hold + best_wc * p_cat_hold

    print("\n--- Baseline weights on the HOLDOUT half ---")
    m_baseline_hold = evaluate(
        y_hold, baseline_hold_proba, class_names,
        model_name=f"v4.1 baseline weights (XGB={cur_wx:.2f}/LGB={cur_wl:.2f}/CAT={cur_wc:.2f}) — holdout half",
    )

    print("\n--- Tuned weights on the HOLDOUT half ---")
    m_tuned_hold = evaluate(
        y_hold, tuned_hold_proba, class_names,
        model_name=f"v4.1 macro-F1-tuned (XGB={best_wx:.2f}/LGB={best_wl:.2f}/CAT={best_wc:.2f}) — holdout half",
    )

    # ── 6. Verdict — head-to-head on the holdout half ─────────────────────
    d_macro = m_tuned_hold["macro_f1"]    - m_baseline_hold["macro_f1"]
    d_wf1   = m_tuned_hold["weighted_f1"] - m_baseline_hold["weighted_f1"]

    print("=" * 70)
    print("VERDICT  (holdout half — same data, only weights differ)")
    print("=" * 70)
    print(f"  Baseline (XGB={cur_wx:.2f}/LGB={cur_wl:.2f}/CAT={cur_wc:.2f})")
    print(f"      Macro F1    = {m_baseline_hold['macro_f1']:.4f}")
    print(f"      Weighted F1 = {m_baseline_hold['weighted_f1']:.4f}")
    print(f"  Tuned    (XGB={best_wx:.2f}/LGB={best_wl:.2f}/CAT={best_wc:.2f})")
    print(f"      Macro F1    = {m_tuned_hold['macro_f1']:.4f}")
    print(f"      Weighted F1 = {m_tuned_hold['weighted_f1']:.4f}")
    print(f"  Delta")
    print(f"      Macro F1    : {d_macro:+.4f}")
    print(f"      Weighted F1 : {d_wf1:+.4f}")
    if d_macro > 0:
        print(f"  >>> Macro F1 IMPROVED by {d_macro:+.4f}.")
    elif d_macro == 0:
        print(f"  >>> Macro F1 UNCHANGED.")
    else:
        print(f"  >>> Macro F1 REGRESSED by {d_macro:+.4f}.")

    # Reference: baseline_v4_1_metrics.json computed on the FULL test set
    if BASELINE.exists():
        baseline_full = json.loads(BASELINE.read_text())
        print()
        print(f"  Reference baseline_v4_1_metrics.json (FULL test set, n={baseline_full['n_samples']:,}):")
        print(f"      Macro F1    = {baseline_full['macro_f1']:.4f}")
        print(f"      Weighted F1 = {baseline_full['weighted_f1']:.4f}")
        print(f"      (Not directly comparable to holdout-half numbers — different sample.)")

    # ── 7. Save JSON ──────────────────────────────────────────────────────
    payload = {
        "tuning_method":         "exhaustive_simplex_grid_search",
        "step":                  0.05,
        "n_weight_combos_tried": n_tried,
        "primary_metric":        "macro_f1",
        "split": {
            "strategy":     "stratified_50_50_of_test_csv",
            "random_state": 42,
            "val_size":     int(len(y_val)),
            "holdout_size": int(len(y_hold)),
        },
        "baseline_weights": {"xgb": cur_wx,   "lgb": cur_wl,   "cat": cur_wc},
        "tuned_weights":    {"xgb": best_wx,  "lgb": best_wl,  "cat": best_wc},
        "val_macro_f1": {
            "baseline_weights": round(float(baseline_val_macro), 4),
            "tuned_weights":    round(float(best_macro_val),     4),
        },
        "holdout_baseline_metrics": m_baseline_hold,
        "holdout_tuned_metrics":    m_tuned_hold,
        "delta_macro_f1_on_holdout":    round(float(d_macro), 4),
        "delta_weighted_f1_on_holdout": round(float(d_wf1),   4),
        "improved_macro_f1":            bool(d_macro > 0),
        "timestamp_utc":   datetime.now(timezone.utc).isoformat(),
        "model_version":   "v4.1 (re-weighted only — pkl files unchanged)",
        "feature_names":   list(bundle["feature_names"]),
        "class_names":     list(class_names),
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2))
    print(f"\nSaved -> {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    _main()
