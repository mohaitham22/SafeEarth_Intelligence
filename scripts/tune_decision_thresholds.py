"""
Tune per-class decision thresholds (one-vs-rest) to improve macro F1.

Uses the v4.1 saved ensemble (XGB=0.6 + LGB=0.1 + CAT=0.3) — the current
saved bundle. Probabilities are computed ONCE per half (val + holdout); models
are not retrained.

Procedure:
  1. Stratified 50/50 split of the test CSV (random_state=42) into val + holdout.
     Identical split to scripts/tune_weights_macro_f1.py for traceability.
  2. Compute ensemble probabilities once per half.
  3. For each class c in [0, n_classes):
       y_bin = (y_val == c).astype(int)
       Use sklearn.precision_recall_curve to enumerate candidate thresholds on
       p_val[:, c]. Pick the threshold that maximizes binary F1 for class c.
  4. Tie-breaking rule for multiclass prediction:
       y_pred = argmax_c (p[:, c] - t_c)
     A class "wins" when its threshold-adjusted score is the highest, even if
     multiple classes' raw probabilities exceed their thresholds.
  5. Evaluate the multiclass predictor on the HOLDOUT half via evaluate().
  6. Compare against:
       - baseline_v4_1_metrics.json (full test set, n=13,070) — reference only
       - argmax of the same probabilities on the same holdout half (apples-to-apples)
  7. Save thresholds and metrics to metrics/v4_1_per_class_thresholds.json.

DOES NOT modify backend/saved_models/*.pkl — pure evaluation.
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
from sklearn.metrics import f1_score, precision_recall_curve
from sklearn.model_selection import train_test_split

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_model import evaluate, _preprocess_test_for_v4_1  # noqa: E402


# ── Public: threshold tuning ─────────────────────────────────────────────────

def tune_per_class_thresholds(
    y_val: np.ndarray,
    p_val: np.ndarray,
    class_names: list[str],
) -> tuple[np.ndarray, dict[str, dict]]:
    """One-vs-rest threshold tuning to maximise per-class F1.

    Returns:
        thresholds: shape (n_classes,) optimal threshold per class.
        diagnostics: per-class dict with chosen threshold, val binary F1,
                     and a few neighbouring thresholds for context.
    """
    n_classes = len(class_names)
    thresholds = np.zeros(n_classes, dtype=np.float64)
    diagnostics: dict[str, dict] = {}

    for c, name in enumerate(class_names):
        y_bin = (y_val == c).astype(np.int32)
        p_c   = p_val[:, c]

        precision, recall, ts = precision_recall_curve(y_bin, p_c)
        # precision_recall_curve returns:
        #   precision/recall of length n_thresholds + 1 (last entry has no threshold)
        #   thresholds of length n_thresholds
        f1 = 2.0 * precision * recall / (precision + recall + 1e-12)
        # f1 has length n_thresholds + 1; the trailing entry corresponds to
        # the "predict nothing" point — exclude it from argmax.
        f1_for_ts = f1[:-1]
        if len(ts) == 0:
            # Pathological: no positive probabilities; default threshold to 0.5
            best_t  = 0.5
            best_f1 = 0.0
        else:
            best_idx = int(np.argmax(f1_for_ts))
            best_t   = float(ts[best_idx])
            best_f1  = float(f1_for_ts[best_idx])
        thresholds[c] = best_t

        # Argmax-equivalent F1 for context — what threshold tuning beats per class
        argmax_pred  = (np.argmax(p_val, axis=1) == c).astype(np.int32)
        argmax_f1    = float(f1_score(y_bin, argmax_pred, zero_division=0))

        diagnostics[name] = {
            "threshold":        round(best_t, 6),
            "val_binary_f1":    round(best_f1, 4),
            "val_argmax_f1":    round(argmax_f1, 4),
            "n_positives_val":  int(y_bin.sum()),
        }

    return thresholds, diagnostics


def predict_with_thresholds(p: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Tie-break: y_pred = argmax_c (p_c - t_c)."""
    return np.argmax(p - t, axis=1)


# ── v4.1 probability builder ─────────────────────────────────────────────────

def v4_1_ensemble_proba(X: np.ndarray, bundle: dict) -> np.ndarray:
    feature_names = bundle["feature_names"]
    p_xgb = bundle["model"].predict_proba(X)
    p     = float(bundle["xgb_weight"]) * p_xgb

    if bundle.get("lgb_model") is not None and float(bundle.get("lgb_weight", 0.0)) > 0:
        X_df = pd.DataFrame(X, columns=feature_names)
        p   += float(bundle["lgb_weight"]) * bundle["lgb_model"].predict_proba(X_df)

    if bundle.get("cat_model") is not None and float(bundle.get("cat_weight", 0.0)) > 0:
        p   += float(bundle["cat_weight"]) * bundle["cat_model"].predict_proba(X)

    return p


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ROOT          = Path(__file__).resolve().parent.parent
    TEST_CSV      = ROOT / "data" / "test" / "1970-2021_DISASTERS.xlsx - test data.csv"
    MODELS_DIR    = ROOT / "backend" / "saved_models"
    METRICS_DIR   = ROOT / "metrics"
    OUT_PATH      = METRICS_DIR / "v4_1_per_class_thresholds.json"
    BASELINE_PATH = METRICS_DIR / "baseline_v4_1_metrics.json"

    METRICS_DIR.mkdir(exist_ok=True)

    print("Loading v4.1 bundle + preprocessing test CSV ...")
    bundle = joblib.load(MODELS_DIR / "disaster_predictor.pkl")
    X_test, y_test, class_names = _preprocess_test_for_v4_1(TEST_CSV, bundle)
    n_classes = len(class_names)
    print(f"  Test set: {X_test.shape}   classes: {n_classes}")

    # 50/50 stratified split (same as tune_weights_macro_f1.py)
    X_val, X_hold, y_val, y_hold = train_test_split(
        X_test, y_test,
        test_size=0.5,
        stratify=y_test,
        random_state=42,
    )
    print(f"  Val half:     n={len(y_val):,}")
    print(f"  Holdout half: n={len(y_hold):,}")

    # Compute ensemble probabilities once per half
    print("Computing ensemble probabilities on both halves ...")
    p_val  = v4_1_ensemble_proba(X_val,  bundle)
    p_hold = v4_1_ensemble_proba(X_hold, bundle)

    # ── Tune thresholds on VAL ────────────────────────────────────────────
    print("\nTuning per-class thresholds on VAL (one-vs-rest, precision_recall_curve)...")
    thresholds, diag = tune_per_class_thresholds(y_val, p_val, class_names)
    print(f"  {'class':<22s}  {'threshold':>10s}  {'val_bin_F1':>10s}  {'argmax_F1':>10s}  {'pos':>5s}")
    print(f"  {'-'*22}  {'-'*10}  {'-'*10}  {'-'*10}  {'-'*5}")
    for name in class_names:
        d = diag[name]
        print(f"  {name:<22s}  {d['threshold']:>10.4f}  "
              f"{d['val_binary_f1']:>10.4f}  {d['val_argmax_f1']:>10.4f}  "
              f"{d['n_positives_val']:>5d}")

    # ── Sanity check on VAL itself (no leakage — thresholds tuned here) ───
    val_pred_tuned    = predict_with_thresholds(p_val, thresholds)
    val_pred_argmax   = np.argmax(p_val, axis=1)
    val_macro_tuned   = f1_score(y_val, val_pred_tuned,  average="macro",    zero_division=0)
    val_macro_argmax  = f1_score(y_val, val_pred_argmax, average="macro",    zero_division=0)
    val_wf1_tuned     = f1_score(y_val, val_pred_tuned,  average="weighted", zero_division=0)
    val_wf1_argmax    = f1_score(y_val, val_pred_argmax, average="weighted", zero_division=0)
    print(f"\nVAL (tuning set):")
    print(f"  argmax     : macro F1 = {val_macro_argmax:.4f}   weighted F1 = {val_wf1_argmax:.4f}")
    print(f"  thresholded: macro F1 = {val_macro_tuned :.4f}   weighted F1 = {val_wf1_tuned :.4f}")
    print(f"  delta      : macro {val_macro_tuned-val_macro_argmax:+.4f}   weighted {val_wf1_tuned-val_wf1_argmax:+.4f}")

    # ── Evaluate on HOLDOUT ───────────────────────────────────────────────
    print("\n--- Argmax (no thresholds) on HOLDOUT half ---")
    m_argmax_hold = evaluate(
        y_hold, p_hold, class_names,
        model_name="v4.1 argmax (no thresholds) — holdout half",
    )

    # apply per-class thresholds to holdout probabilities
    pred_t_hold = predict_with_thresholds(p_hold, thresholds)
    # Build a synthetic "proba" matrix for evaluate(): one-hot from threshold predictions
    # — but evaluate() argmaxes the input, so we need to feed it something whose argmax
    # equals pred_t_hold. The simplest valid synthetic: identity per-row.
    # Cleanest: bypass evaluate's argmax by feeding (p - t) directly, since
    # evaluate uses argmax internally.
    print("\n--- Per-class thresholds on HOLDOUT half ---")
    m_tuned_hold = evaluate(
        y_hold, p_hold - thresholds, class_names,
        model_name="v4.1 + per-class thresholds — holdout half",
    )

    # ── Verdict ───────────────────────────────────────────────────────────
    d_macro = m_tuned_hold["macro_f1"]    - m_argmax_hold["macro_f1"]
    d_wf1   = m_tuned_hold["weighted_f1"] - m_argmax_hold["weighted_f1"]

    print("=" * 70)
    print("VERDICT  (holdout half — same probabilities, only decision rule differs)")
    print("=" * 70)
    print(f"  Argmax       : macro F1 = {m_argmax_hold['macro_f1']:.4f}   weighted F1 = {m_argmax_hold['weighted_f1']:.4f}")
    print(f"  Thresholded  : macro F1 = {m_tuned_hold ['macro_f1']:.4f}   weighted F1 = {m_tuned_hold ['weighted_f1']:.4f}")
    print(f"  Delta        : macro    {d_macro:+.4f}     weighted    {d_wf1:+.4f}")
    if d_macro > 0:
        print(f"  >>> Macro F1 IMPROVED on holdout by {d_macro:+.4f}.")
    elif d_macro == 0:
        print("  >>> Macro F1 unchanged.")
    else:
        print(f"  >>> Macro F1 REGRESSED on holdout by {d_macro:+.4f}.")

    # Reference baseline (full test set, n=13,070)
    baseline_full = json.loads(BASELINE_PATH.read_text())
    baseline_per_class_full = {row["class"]: row["f1"] for row in baseline_full["per_class_f1_sorted"]}
    print()
    print(f"  Reference baseline_v4_1_metrics.json (full test set, n={baseline_full['n_samples']:,}):")
    print(f"      macro F1    = {baseline_full['macro_f1']:.4f}")
    print(f"      weighted F1 = {baseline_full['weighted_f1']:.4f}")
    print(f"      (Reference only — different sample than holdout-half numbers above.)")

    # ── Per-class deltas the user explicitly asked about ──────────────────
    target_classes = ["Drought", "Landslide", "Wildfire", "Volcanic activity"]
    h_per = {row["class"]: row["f1"] for row in m_tuned_hold["per_class_f1_sorted"]}
    a_per = {row["class"]: row["f1"] for row in m_argmax_hold["per_class_f1_sorted"]}

    print("\nPer-class F1 on the holdout half (target classes only):\n")
    print(f"  {'class':<22s}  {'argmax':>8s}  {'tuned':>8s}  {'d (tuned-argmax)':>17s}  {'baseline*':>10s}  {'d vs base*':>11s}")
    print(f"  {'-'*22}  {'-'*8}  {'-'*8}  {'-'*17}  {'-'*10}  {'-'*11}")
    for c in target_classes:
        d_vs_a    = h_per[c] - a_per[c]
        d_vs_base = h_per[c] - baseline_per_class_full[c]
        print(f"  {c:<22s}  {a_per[c]:>8.4f}  {h_per[c]:>8.4f}  {d_vs_a:>+17.4f}  "
              f"{baseline_per_class_full[c]:>10.4f}  {d_vs_base:>+11.4f}")
    print(f"  * baseline column is from baseline_v4_1_metrics.json (full test set n={baseline_full['n_samples']:,}).")
    print(f"    'd vs base*' is NOT apples-to-apples (different sample); 'd (tuned-argmax)' IS.")

    # ── Save JSON ─────────────────────────────────────────────────────────
    out = {
        "tuning_method": "per_class_one_vs_rest_pr_curve",
        "tie_breaking":  "argmax(p_c - t_c)  i.e. argmax of threshold-adjusted score",
        "primary_metric": "macro_f1",
        "split": {
            "strategy":     "stratified_50_50_of_test_csv",
            "random_state": 42,
            "val_size":     int(len(y_val)),
            "holdout_size": int(len(y_hold)),
        },
        "thresholds": {class_names[c]: float(round(thresholds[c], 6)) for c in range(n_classes)},
        "per_class_diagnostics_val": diag,
        "val_metrics": {
            "argmax_macro_f1":         round(float(val_macro_argmax), 4),
            "thresholded_macro_f1":    round(float(val_macro_tuned), 4),
            "argmax_weighted_f1":      round(float(val_wf1_argmax), 4),
            "thresholded_weighted_f1": round(float(val_wf1_tuned), 4),
        },
        "holdout_argmax_metrics":     m_argmax_hold,
        "holdout_thresholded_metrics": m_tuned_hold,
        "delta_macro_f1_on_holdout":     round(float(d_macro), 4),
        "delta_weighted_f1_on_holdout":  round(float(d_wf1),   4),
        "improved_macro_f1":             bool(d_macro > 0),
        "target_classes": target_classes,
        "target_class_deltas_vs_baseline_full": {
            c: round(h_per[c] - baseline_per_class_full[c], 4)
            for c in target_classes
        },
        "target_class_deltas_vs_argmax_holdout": {
            c: round(h_per[c] - a_per[c], 4)
            for c in target_classes
        },
        "baseline_reference": {
            "source":      str(BASELINE_PATH.relative_to(ROOT)).replace("\\", "/"),
            "macro_f1":    baseline_full["macro_f1"],
            "weighted_f1": baseline_full["weighted_f1"],
            "n_samples":   baseline_full["n_samples"],
            "note":        "Computed on the FULL test set (n=13,070). Not directly comparable to holdout-half numbers.",
        },
        "ensemble":        {"xgb": float(bundle["xgb_weight"]),
                            "lgb": float(bundle["lgb_weight"]),
                            "cat": float(bundle["cat_weight"])},
        "feature_names":   list(bundle["feature_names"]),
        "class_names":     class_names,
        "timestamp_utc":   datetime.now(timezone.utc).isoformat(),
        "model_version":   "v4.1 (probabilities unchanged) + tuned per-class thresholds",
    }
    OUT_PATH.write_text(json.dumps(out, indent=2))
    print(f"\nSaved -> {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
