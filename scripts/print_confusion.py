"""
Print the confusion matrix for the current v4.2 ensemble on the holdout
test set (data/test/1970-2021_DISASTERS.xlsx - test data.csv, n=13,070).

Rows    = true class
Columns = predicted class
Diagonal = correctly classified

Usage:
    py -3.12 scripts/print_confusion.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import confusion_matrix

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from evaluate_model import _preprocess_test_for_v4_1, _v4_1_ensemble_proba  # noqa: E402


def main() -> None:
    ROOT       = Path(__file__).resolve().parent.parent
    TEST_CSV   = ROOT / "data" / "test" / "1970-2021_DISASTERS.xlsx - test data.csv"
    MODELS_DIR = ROOT / "backend" / "saved_models"

    bundle = joblib.load(MODELS_DIR / "disaster_predictor.pkl")
    version = bundle.get("version", "(unversioned)")
    class_names = list(bundle["le_target"].classes_)

    X_test, y_test, _ = _preprocess_test_for_v4_1(TEST_CSV, bundle)
    proba = _v4_1_ensemble_proba(X_test, bundle)
    y_pred = np.argmax(proba, axis=1)

    cm = confusion_matrix(y_test, y_pred, labels=list(range(len(class_names))))

    # Use shortened labels for column headers so the matrix fits on screen
    short = {
        "Drought":             "Drght",
        "Earthquake":          "Erthq",
        "Extreme temperature": "ExTmp",
        "Flood":               "Flood",
        "Landslide":           "Lndsl",
        "Storm":               "Storm",
        "Volcanic activity":   "Volc",
        "Wildfire":            "Wldfr",
    }
    short_names = [short[c] for c in class_names]

    print()
    print(f"Confusion matrix  -  model {version}  -  holdout n={len(y_test):,}")
    print(f"Rows = true,  columns = predicted,  diagonal = correct.")
    print()

    # Column header
    print(f"  {'true \\ pred':<22s}  " + "  ".join(f"{s:>6s}" for s in short_names) + f"   {'total':>6s}   {'recall':>6s}")
    print(f"  {'-'*22}  " + "  ".join("-"*6 for _ in short_names) + f"   {'-'*6}   {'-'*6}")

    for i, name in enumerate(class_names):
        row_total = cm[i].sum()
        row_correct = cm[i, i]
        recall = row_correct / row_total if row_total else 0.0
        cells = "  ".join(f"{cm[i, j]:>6,}" for j in range(len(class_names)))
        print(f"  {name:<22s}  {cells}   {row_total:>6,}   {recall:>6.3f}")

    # Bottom: column totals + precision
    print(f"  {'-'*22}  " + "  ".join("-"*6 for _ in short_names) + f"   {'-'*6}   {'-'*6}")
    col_totals = cm.sum(axis=0)
    precisions = [cm[j, j] / col_totals[j] if col_totals[j] else 0.0 for j in range(len(class_names))]
    print(
        f"  {'total predicted':<22s}  "
        + "  ".join(f"{t:>6,}" for t in col_totals)
        + f"   {cm.sum():>6,}   {'':>6s}"
    )
    print(
        f"  {'precision':<22s}  "
        + "  ".join(f"{p:>6.3f}" for p in precisions)
    )

    print()
    print(f"Short labels: " + ", ".join(f"{s}={name}" for s, name in zip(short_names, class_names)))
    print()


if __name__ == "__main__":
    main()
