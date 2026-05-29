"""
v4.2 strategy comparison — XGB + CatBoost (LGB dropped) with minority handling.

Carries forward two findings from the macro-F1 weight tuning step:
  (1) LightGBM HURTS macro F1 -> dropped entirely. Ensemble is XGB + CAT only.
  (2) Validation gains shrink on holdout -> we require holdout_macro_gain > CV_std
      before keeping a strategy.

Strategies compared (all XGB+CAT, ensemble weights XGB=0.60 / CAT=0.40):

  A. "hand_weights"
     v4.1's hand-tuned per-class sample weights:
       Flood=1.0, Storm=1.0, Earthquake=1.0, Extreme=1.5, Wildfire=2.5,
       Volcanic=3.0, Drought=4.0, Landslide=3.0
     (Acts as the "drop LGB only" control — isolates the strategy change from
     the LGB-removal effect.)

  B. "balanced_inv_freq"
     sklearn compute_sample_weight("balanced", y_train).
     Weight per sample = n_samples / (n_classes * n_samples_in_that_class).
     More aggressive than v4.1 for Wildfire/Volcanic, less for Drought/Landslide.

  C. "smote_minority_per_fold"
     SMOTENC oversampling applied ONLY inside the training fold.
     Brings every class with < 1500 events up to 1500.  Categorical columns
     [continent_enc, region_enc, country_enc, has_magnitude, decade] handled
     by SMOTENC's per-feature mode (not averaged).  Never touches val/holdout.

Evaluation:
  5-fold StratifiedKFold on the train CSV (random_state=42).
  For each fold: apply strategy on the TRAIN fold only, fit XGB + CAT,
    predict on the VAL fold, compute macro F1.
  Report mean +- std across folds.
  Then fit on the full train set, predict on the holdout (test CSV), and
    compare against baseline_v4_1_metrics.json.

Decision rule:
  KEEP a strategy iff   (holdout_macro_f1 - baseline_macro_f1)  >  CV_std.
  Otherwise DISCARD (the improvement is within fold-to-fold noise).

Hyperparameters for XGB and CatBoost are reused unchanged from the v4.1 bundle
(`disaster_predictor.pkl`) so that the only thing varying across strategies is
the way training data is presented to the model.

Does NOT modify backend/saved_models/*.pkl - pure evaluation.
"""
from __future__ import annotations

import json
import sys
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTENC
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedKFold
from sklearn.utils.class_weight import compute_sample_weight

from catboost import CatBoostClassifier
from xgboost import XGBClassifier

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_model import evaluate, _preprocess_test_for_v4_1  # noqa: E402


# ── Constants ─────────────────────────────────────────────────────────────────

W_XGB = 0.60   # ensemble weights from prior macro-F1 tuning (LGB=0 dropped, others normalized)
W_CAT = 0.40
N_FOLDS = 5

SMOTE_MIN_TARGET = 1500
# columns to treat as categorical for SMOTENC:
# 5 continent_enc, 6 region_enc, 7 country_enc, 11 has_magnitude, 14 decade
CATEGORICAL_FEATURE_IDX = [5, 6, 7, 11, 14]

# v4.1's hand-tuned weights (used by strategy A)
HAND_WEIGHTS = {
    "Flood":               1.0,
    "Storm":               1.0,
    "Earthquake":          1.0,
    "Extreme temperature": 1.5,
    "Wildfire":            2.5,
    "Volcanic activity":   3.0,
    "Drought":             4.0,
    "Landslide":           3.0,
}

WATCHED_IMPROVE   = ["Landslide", "Drought", "Wildfire"]
WATCHED_REGRESS   = ["Earthquake", "Flood", "Storm"]
REGRESS_THRESHOLD = 0.02


# ── Model factories — same hyperparameters as the v4.1 bundle ────────────────

def make_xgb() -> XGBClassifier:
    return XGBClassifier(
        n_estimators=481,
        max_depth=8,
        learning_rate=0.05187463761442706,
        min_child_weight=4,
        gamma=0.5007073736271453,
        subsample=0.8302660565211304,
        colsample_bytree=0.5614578448080267,
        reg_alpha=1.849828250878654,
        reg_lambda=2.3962531922058874,
        eval_metric="mlogloss",
        random_state=42,
        n_jobs=-1,
        verbosity=0,
    )


def make_cat() -> CatBoostClassifier:
    return CatBoostClassifier(
        iterations=426,
        depth=6,
        learning_rate=0.16872443214156704,
        l2_leaf_reg=9.70782790938596,
        border_count=123,
        bagging_temperature=0.5745188822465942,
        random_strength=1.9838089130705425,
        loss_function="MultiClass",
        eval_metric="Accuracy",
        random_seed=42,
        thread_count=-1,
        verbose=0,
        allow_writing_files=False,
    )


# ── Strategy implementations ─────────────────────────────────────────────────

def _hand_sample_weights(y: np.ndarray, le_target) -> np.ndarray:
    classes_str = le_target.inverse_transform(y)
    return np.array([HAND_WEIGHTS[c] for c in classes_str], dtype=np.float32)


def _balanced_sample_weights(y: np.ndarray) -> np.ndarray:
    return compute_sample_weight("balanced", y).astype(np.float32)


def _smote_resample(X: np.ndarray, y: np.ndarray, random_state: int = 42):
    counts = np.bincount(y)
    sampling_target = {
        int(cls): SMOTE_MIN_TARGET
        for cls, cnt in enumerate(counts)
        if cnt < SMOTE_MIN_TARGET
    }
    if not sampling_target:
        return X, y
    smote = SMOTENC(
        categorical_features=CATEGORICAL_FEATURE_IDX,
        sampling_strategy=sampling_target,
        k_neighbors=5,
        random_state=random_state,
    )
    X_res, y_res = smote.fit_resample(X, y)
    return X_res, y_res


def train_pair(
    X_tr: np.ndarray,
    y_tr: np.ndarray,
    strategy: str,
    le_target,
) -> tuple[XGBClassifier, CatBoostClassifier]:
    if strategy == "smote_minority_per_fold":
        X_used, y_used = _smote_resample(X_tr, y_tr)
        sw = None
    elif strategy == "hand_weights":
        X_used, y_used = X_tr, y_tr
        sw = _hand_sample_weights(y_tr, le_target)
    elif strategy == "balanced_inv_freq":
        X_used, y_used = X_tr, y_tr
        sw = _balanced_sample_weights(y_tr)
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    xgb = make_xgb()
    cat = make_cat()
    xgb.fit(X_used, y_used, sample_weight=sw)
    cat.fit(X_used, y_used, sample_weight=sw)
    return xgb, cat


def predict_ensemble(xgb, cat, X) -> np.ndarray:
    return W_XGB * xgb.predict_proba(X) + W_CAT * cat.predict_proba(X)


# ── Cross-validation ─────────────────────────────────────────────────────────

def run_cv(
    strategy: str,
    X_full: np.ndarray,
    y_full: np.ndarray,
    le_target,
    n_classes: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Returns (fold_macros: shape (N_FOLDS,), fold_per_class_f1: (N_FOLDS, n_classes))."""
    skf = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=42)
    fold_macros = np.zeros(N_FOLDS, dtype=np.float64)
    fold_per_class = np.zeros((N_FOLDS, n_classes), dtype=np.float64)

    for i, (tr_idx, va_idx) in enumerate(skf.split(X_full, y_full)):
        t0 = time.time()
        X_tr, y_tr = X_full[tr_idx], y_full[tr_idx]
        X_va, y_va = X_full[va_idx], y_full[va_idx]

        xgb, cat = train_pair(X_tr, y_tr, strategy, le_target)

        proba = predict_ensemble(xgb, cat, X_va)
        pred  = np.argmax(proba, axis=1)
        macro = f1_score(y_va, pred, average="macro", zero_division=0)
        per   = f1_score(y_va, pred, labels=list(range(n_classes)), average=None, zero_division=0)

        fold_macros[i]    = float(macro)
        fold_per_class[i] = per
        print(f"    Fold {i+1}/{N_FOLDS}: macro F1 = {macro:.4f}   ({time.time()-t0:.0f}s)")

    return fold_macros, fold_per_class


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ROOT          = Path(__file__).resolve().parent.parent
    TRAIN_CSV     = ROOT / "data" / "train" / "1900_2021_DISASTERS.xlsx - train data.csv"
    TEST_CSV      = ROOT / "data" / "test"  / "1970-2021_DISASTERS.xlsx - test data.csv"
    MODELS_DIR    = ROOT / "backend" / "saved_models"
    METRICS_DIR   = ROOT / "metrics"
    OUT_PATH      = METRICS_DIR / "minority_strategies_v4_2.json"
    BASELINE_PATH = METRICS_DIR / "baseline_v4_1_metrics.json"

    METRICS_DIR.mkdir(exist_ok=True)

    print("Loading v4.1 bundle + preprocessing train/test ...")
    bundle = joblib.load(MODELS_DIR / "disaster_predictor.pkl")
    le_target = bundle["le_target"]
    class_names = list(le_target.classes_)
    n_classes = len(class_names)

    X_train, y_train, _ = _preprocess_test_for_v4_1(TRAIN_CSV, bundle)
    X_test,  y_test,  _ = _preprocess_test_for_v4_1(TEST_CSV,  bundle)

    print(f"  X_train: {X_train.shape}   X_test: {X_test.shape}")
    train_counts = dict(zip(class_names, np.bincount(y_train, minlength=n_classes)))
    print(f"  Train class counts:")
    for c, n in sorted(train_counts.items(), key=lambda kv: kv[1]):
        print(f"    {c:<22s}  {n:>5,}")

    # Show the SMOTE sampling plan (one-time, before CV)
    smote_target = {c: SMOTE_MIN_TARGET for c, n in train_counts.items() if n < SMOTE_MIN_TARGET}
    print(f"\n  SMOTE oversampling target ({len(smote_target)} classes -> {SMOTE_MIN_TARGET}):")
    for c, t in smote_target.items():
        added = t - train_counts[c]
        print(f"    {c:<22s}  {train_counts[c]:>5,}  ->  {t:>5,}   (+{added:,})")

    # Load baseline for comparison
    baseline = json.loads(BASELINE_PATH.read_text())
    baseline_macro = baseline["macro_f1"]
    baseline_wf1   = baseline["weighted_f1"]
    baseline_per_class = {row["class"]: row["f1"] for row in baseline["per_class_f1_sorted"]}

    print(f"\nBaseline (v4.1 from {BASELINE_PATH.name}):")
    print(f"  macro F1    = {baseline_macro:.4f}")
    print(f"  weighted F1 = {baseline_wf1:.4f}")

    strategies = ["hand_weights", "balanced_inv_freq", "smote_minority_per_fold"]
    results: dict[str, dict] = {}

    for strategy in strategies:
        print(f"\n{'='*70}")
        print(f"Strategy: {strategy}")
        print(f"{'='*70}")
        print(f"  Running {N_FOLDS}-fold CV ...")

        fold_macros, fold_per_class = run_cv(strategy, X_train, y_train, le_target, n_classes)
        cv_mean = float(fold_macros.mean())
        cv_std  = float(fold_macros.std())

        per_class_cv_mean = fold_per_class.mean(axis=0)
        per_class_cv_std  = fold_per_class.std(axis=0)

        print(f"\n  CV macro F1: {cv_mean:.4f}  +/-  {cv_std:.4f}")

        # Train final model on FULL train, evaluate on test (holdout)
        print(f"  Training on full train, predicting on holdout ...")
        t0 = time.time()
        xgb_full, cat_full = train_pair(X_train, y_train, strategy, le_target)
        proba_h = predict_ensemble(xgb_full, cat_full, X_test)
        print(f"  ({time.time()-t0:.0f}s)")

        m = evaluate(y_test, proba_h, class_names, model_name=f"v4.2 strategy: {strategy}")

        # Compare to baseline
        delta_macro = m["macro_f1"]    - baseline_macro
        delta_wf1   = m["weighted_f1"] - baseline_wf1
        keep        = delta_macro > cv_std  # user-specified decision rule

        per_class_h = {row["class"]: row["f1"] for row in m["per_class_f1_sorted"]}

        improve_deltas = {
            c: round(per_class_h[c] - baseline_per_class[c], 4)
            for c in WATCHED_IMPROVE
        }
        regress_deltas = {
            c: round(per_class_h[c] - baseline_per_class[c], 4)
            for c in WATCHED_REGRESS
        }
        big_regression_classes = [
            c for c, d in regress_deltas.items() if d < -REGRESS_THRESHOLD
        ]

        results[strategy] = {
            "cv_fold_macros":   [round(float(x), 4) for x in fold_macros],
            "cv_macro_mean":    round(cv_mean, 4),
            "cv_macro_std":     round(cv_std,  4),
            "cv_per_class_mean": {
                class_names[i]: round(float(per_class_cv_mean[i]), 4)
                for i in range(n_classes)
            },
            "cv_per_class_std": {
                class_names[i]: round(float(per_class_cv_std[i]), 4)
                for i in range(n_classes)
            },
            "holdout_macro":            m["macro_f1"],
            "holdout_weighted_f1":      m["weighted_f1"],
            "holdout_per_class_f1":     per_class_h,
            "delta_macro_vs_baseline":  round(delta_macro, 4),
            "delta_wf1_vs_baseline":    round(delta_wf1,   4),
            "decision":                 "KEEP" if keep else "DISCARD",
            "decision_rule":            f"holdout_gain {delta_macro:+.4f}  {'>' if keep else '<='}  CV_std {cv_std:.4f}",
            "watched_improve_deltas":   improve_deltas,
            "watched_regress_deltas":   regress_deltas,
            "big_regression_classes":   big_regression_classes,
            "any_big_regression":       len(big_regression_classes) > 0,
        }

    # ── Save full report ─────────────────────────────────────────────────────
    report = {
        "primary_metric":       "macro_f1",
        "ensemble":             {"xgb_weight": W_XGB, "cat_weight": W_CAT, "lgb_dropped": True},
        "n_folds":              N_FOLDS,
        "cv_random_state":      42,
        "smote_min_target":     SMOTE_MIN_TARGET,
        "smote_categorical_features_idx": CATEGORICAL_FEATURE_IDX,
        "smote_k_neighbors":    5,
        "decision_rule":        "keep strategy iff holdout_macro_gain > CV_macro_std",
        "regression_threshold": REGRESS_THRESHOLD,
        "baseline_v4_1": {
            "macro_f1":    baseline_macro,
            "weighted_f1": baseline_wf1,
            "per_class_f1": baseline_per_class,
            "source": str(BASELINE_PATH.relative_to(ROOT)).replace("\\", "/"),
        },
        "strategies":         results,
        "watched_improve":    WATCHED_IMPROVE,
        "watched_regress":    WATCHED_REGRESS,
        "timestamp_utc":      datetime.now(timezone.utc).isoformat(),
        "model_version":      "v4.2 (XGB+CAT, LGB dropped) - evaluation only",
        "feature_names":      list(bundle["feature_names"]),
        "class_names":        class_names,
    }
    OUT_PATH.write_text(json.dumps(report, indent=2))

    # ── Final printed summary ───────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    print(f"Baseline v4.1:  macro F1 = {baseline_macro:.4f}   weighted F1 = {baseline_wf1:.4f}")
    print()
    print(f"{'strategy':<28s}  {'CV mean':>8s}  {'CV std':>7s}  {'holdout':>8s}  {'d macro':>8s}  {'decision':>9s}")
    print("-" * 80)
    for s, r in results.items():
        print(
            f"{s:<28s}  {r['cv_macro_mean']:>8.4f}  {r['cv_macro_std']:>7.4f}  "
            f"{r['holdout_macro']:>8.4f}  {r['delta_macro_vs_baseline']:>+8.4f}  "
            f"{r['decision']:>9s}"
        )

    print("\nWatched class F1 deltas vs baseline_v4_1 (per strategy):\n")
    for s, r in results.items():
        print(f"  {s}")
        print(f"    Improve targets  (want positive):")
        for c in WATCHED_IMPROVE:
            print(f"      {c:<22s}  {r['watched_improve_deltas'][c]:+.4f}")
        print(f"    Regress check (flag if < -{REGRESS_THRESHOLD}):")
        for c in WATCHED_REGRESS:
            d = r["watched_regress_deltas"][c]
            tag = "  <-- BIG DROP" if d < -REGRESS_THRESHOLD else ""
            print(f"      {c:<22s}  {d:+.4f}{tag}")
        print(f"    Decision: {r['decision']}   ({r['decision_rule']})")
        print()

    print(f"Saved -> {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
