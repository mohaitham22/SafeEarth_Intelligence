"""
Centroid-imputation experiment — ISOLATED, read-only w.r.t. production.
=======================================================================
Hypothesis under test (user request):
  "If we fill the missing lat/lon with accurate per-country coordinates instead
   of the country event-median, does classification accuracy go up and regression
   error go down?"

Design — a clean A/B where the ONLY thing that changes is the lat/lon imputation
source. Both arms use:
  * the SAME 16 production features
  * the SAME fixed hyperparameters (XGB 0.6 + CatBoost 0.4, mirroring v4.2)
  * the SAME holdout protocol (test CSV 1970-2021)
  * the SAME 4 production regressors (XGB deaths/damage, RF injuries/affected)

Arms:
  A_median_impute   — production behaviour: country -> continent -> global EVENT median
  D_centroid_impute — fill NaN lat/lon from curated ISO3 centroids
                      (_ISO3_CENTROIDS, scripts/generate_emdat_stats.py), then the
                      SAME median chain as a fallback for the ~1% with no centroid

Decision rule (same as preprocessing_experiment.py):
  keep iff  holdout_macro_gain > baseline CV_std

This script touches NOTHING in backend/, scripts/, saved_models/, or metrics/.

Run from project root:
  py -3.12 streamlit_eda/experiments/centroid_impute_experiment.py
"""
from __future__ import annotations

import json
import re
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier, XGBRegressor
from catboost import CatBoostClassifier

# --------------------------------------------------------------------------- #
# Paths & constants (mirror scripts/run_training.py + preprocessing_experiment)
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parents[2]
TRAIN_CSV = ROOT / "data" / "train" / "1900_2021_DISASTERS.xlsx - train data.csv"
TEST_CSV = ROOT / "data" / "test" / "1970-2021_DISASTERS.xlsx - test data.csv"
OUT_JSON = Path(__file__).resolve().parent / "centroid_results.json"

# Curated per-country centroids already in the repo (the "accurate per-country
# coordinates" the hypothesis proposes — 211 of 225 ISO codes covered).
sys.path.insert(0, str(ROOT / "scripts"))
from generate_emdat_stats import _ISO3_CENTROIDS  # noqa: E402

VALID = ["Flood", "Storm", "Earthquake", "Wildfire",
         "Volcanic activity", "Landslide", "Drought", "Extreme temperature"]

CUSTOM_CLASS_WEIGHTS = {
    "Flood": 1.0, "Storm": 1.0, "Earthquake": 1.0, "Extreme temperature": 1.5,
    "Wildfire": 2.5, "Volcanic activity": 3.0, "Drought": 4.0, "Landslide": 3.0,
}

BASE_FEATURES = [
    "latitude", "longitude", "abs_latitude", "lon_sin", "lon_cos",
    "continent_enc", "region_enc", "country_enc", "month_sin", "month_cos",
    "dis_mag_value", "has_magnitude", "historical_freq", "log_hist_freq",
    "decade", "day_offset",
]

# Production v4.2 regressor targets (EXACT columns from scripts/run_training.py —
# note 'No Affected', not 'Total Affected').
REG_TARGETS = {
    "deaths": "Total Deaths",
    "injuries": "No Injured",
    "affected": "No Affected",
    "damage": "Total Damages ('000 US$)",
}

# Fixed hyperparameters — IDENTICAL for every arm (clean ablation).
XGB_PARAMS = dict(
    n_estimators=500, max_depth=7, learning_rate=0.05, subsample=0.85,
    colsample_bytree=0.8, min_child_weight=3, reg_lambda=2.0, gamma=0.0,
    eval_metric="mlogloss", tree_method="hist", random_state=42,
    n_jobs=-1, verbosity=0,
)
CAT_PARAMS = dict(
    iterations=500, depth=6, learning_rate=0.05, l2_leaf_reg=3.0,
    loss_function="MultiClass", random_seed=42, thread_count=-1,
    verbose=0, allow_writing_files=False,
)
W_XGB, W_CAT = 0.6, 0.4  # production v4.2 ensemble weights


# --------------------------------------------------------------------------- #
# Coordinate parser (identical to scripts/run_training.py)
# --------------------------------------------------------------------------- #
def parse_coord(val) -> float:
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


# --------------------------------------------------------------------------- #
# Coordinate imputation — the ONLY thing that differs between arms
# --------------------------------------------------------------------------- #
def impute_coords(df: pd.DataFrame, mode: str) -> tuple[pd.DataFrame, dict]:
    """Parse + impute Latitude/Longitude in place. Returns (df, diagnostics).

    mode == "median":   country -> continent -> global EVENT median (production).
    mode == "centroid": fill NaN from ISO3 centroid first, then the SAME median
                        chain as a fallback for ISO codes with no centroid.
    """
    df = df.copy()
    for col in ("Latitude", "Longitude"):
        df[col] = df[col].apply(parse_coord)
    df.loc[(df["Latitude"] < -90) | (df["Latitude"] > 90), "Latitude"] = np.nan
    df.loc[(df["Longitude"] < -180) | (df["Longitude"] > 180), "Longitude"] = np.nan

    nan_mask = df["Latitude"].isna() | df["Longitude"].isna()
    n_missing = int(nan_mask.sum())

    diag = {"rows": int(len(df)), "missing_coord_rows": n_missing}

    if mode == "centroid":
        iso = df["ISO"].astype(str).str.strip().str.upper()
        cent_lat = iso.map(lambda c: _ISO3_CENTROIDS.get(c, (np.nan, np.nan))[0])
        cent_lon = iso.map(lambda c: _ISO3_CENTROIDS.get(c, (np.nan, np.nan))[1])
        # how many of the missing rows actually get a centroid (the rows that differ)
        filled_by_centroid = int((nan_mask & cent_lat.notna()).sum())
        diag["filled_by_centroid"] = filled_by_centroid
        df["Latitude"] = df["Latitude"].fillna(cent_lat)
        df["Longitude"] = df["Longitude"].fillna(cent_lon)

    # median fallback chain (full strategy for 'median' mode; tail for 'centroid')
    for col in ("Latitude", "Longitude"):
        df[col] = df[col].fillna(df.groupby("Country")[col].transform("median"))
        df[col] = df[col].fillna(df.groupby("Continent")[col].transform("median"))
        df[col] = df[col].fillna(df[col].median())

    assert df["Latitude"].notna().all() and df["Longitude"].notna().all()
    return df, diag


# --------------------------------------------------------------------------- #
# Feature engineering (16 production features) — shared by both arms
# --------------------------------------------------------------------------- #
def build_features(raw: pd.DataFrame, *, mode, region_freq_map, encoders,
                   month_mode_map, fit: bool) -> tuple[pd.DataFrame, dict]:
    df = raw.copy()
    df["Disaster Type"] = df["Disaster Type"].str.strip()
    df = df[df["Disaster Type"].isin(VALID)].reset_index(drop=True)

    df, diag = impute_coords(df, mode)

    df["latitude"] = df["Latitude"]
    df["longitude"] = df["Longitude"]
    df["abs_latitude"] = df["latitude"].abs()
    df["lon_sin"] = np.sin(2 * np.pi * df["longitude"] / 360)
    df["lon_cos"] = np.cos(2 * np.pi * df["longitude"] / 360)

    if fit:
        mr = df["Start Month"].copy()
        for dt, mv in month_mode_map.items():
            mr.loc[mr.isna() & (df["Disaster Type"] == dt)] = mv
        mr = mr.fillna(6).astype(int)
    else:
        mr = df["Start Month"].fillna(6).astype(int)
    df["month_sin"] = np.sin(2 * np.pi * mr / 12)
    df["month_cos"] = np.cos(2 * np.pi * mr / 12)

    df["decade"] = (df["Year"] // 10) * 10
    df["historical_freq"] = df["Region"].map(region_freq_map).fillna(1).astype(int)
    df["log_hist_freq"] = np.log1p(df["historical_freq"])
    df["has_magnitude"] = df["Dis Mag Value"].notna().astype(int)
    df["dis_mag_value"] = pd.to_numeric(df["Dis Mag Value"], errors="coerce").fillna(0.0)
    df["day_offset"] = 0

    le_cont, le_reg, le_ctry = encoders["continent"], encoders["region"], encoders["country"]
    if fit:
        df["continent_enc"] = le_cont.fit_transform(df["Continent"])
        df["region_enc"] = le_reg.fit_transform(df["Region"])
        df["country_enc"] = le_ctry.fit_transform(df["Country"])
    else:
        def enc(le, vals):
            known = set(le.classes_)
            return np.array([le.transform([v])[0] if v in known else 0 for v in vals], dtype=np.int32)
        df["continent_enc"] = enc(le_cont, df["Continent"])
        df["region_enc"] = enc(le_reg, df["Region"])
        df["country_enc"] = enc(le_ctry, df["Country"])

    # regression targets (log1p) — same prep as run_training.py
    for col in REG_TARGETS.values():
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).clip(lower=0)

    return df, diag


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
def fit_ensemble(Xtr, ytr, w):
    xgb = XGBClassifier(**XGB_PARAMS); xgb.fit(Xtr, ytr, sample_weight=w)
    cat = CatBoostClassifier(**CAT_PARAMS); cat.fit(Xtr, ytr, sample_weight=w)
    return xgb, cat


def ensemble_pred(xgb, cat, X):
    return np.argmax(W_XGB * xgb.predict_proba(X) + W_CAT * cat.predict_proba(X), axis=1)


def eval_classification(df_tr, y_tr, w, df_te, y_te, classes):
    Xtr = df_tr[BASE_FEATURES].values.astype(np.float32)
    Xte = df_te[BASE_FEATURES].values.astype(np.float32)
    xgb, cat = fit_ensemble(Xtr, y_tr, w)
    pred = ensemble_pred(xgb, cat, Xte)
    per_class = f1_score(y_te, pred, average=None, labels=range(len(classes)), zero_division=0)
    return {
        "macro_f1": float(f1_score(y_te, pred, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(y_te, pred, average="weighted", zero_division=0)),
        "accuracy": float(accuracy_score(y_te, pred)),
        "per_class_f1": {classes[i]: float(per_class[i]) for i in range(len(classes))},
    }


def cv_macro(df_tr, y_tr, w, n_splits=5):
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    Xv = df_tr[BASE_FEATURES].values.astype(np.float32)
    scores = []
    for ti, vi in skf.split(Xv, y_tr):
        xgb, cat = fit_ensemble(Xv[ti], y_tr[ti], w[ti])
        pred = ensemble_pred(xgb, cat, Xv[vi])
        scores.append(f1_score(y_tr[vi], pred, average="macro", zero_division=0))
    return float(np.mean(scores)), float(np.std(scores)), [round(s, 4) for s in scores]


def eval_regression(df_tr, df_te):
    """Train the 4 production regressors on log1p targets; report holdout MAE
    on the log1p scale (what the model optimises — stable, outlier-robust)."""
    Xtr = df_tr[BASE_FEATURES].values.astype(np.float32)
    Xte = df_te[BASE_FEATURES].values.astype(np.float32)
    out = {}
    builders = {
        "deaths": lambda: XGBRegressor(n_estimators=300, max_depth=5, learning_rate=0.08,
                                       subsample=0.8, colsample_bytree=0.8,
                                       random_state=42, n_jobs=-1, verbosity=0),
        "damage": lambda: XGBRegressor(n_estimators=300, max_depth=5, learning_rate=0.08,
                                       subsample=0.8, colsample_bytree=0.8,
                                       random_state=42, n_jobs=-1, verbosity=0),
        "injuries": lambda: RandomForestRegressor(n_estimators=200, max_depth=10,
                                                  min_samples_leaf=5, random_state=42, n_jobs=-1),
        "affected": lambda: RandomForestRegressor(n_estimators=200, max_depth=10,
                                                  min_samples_leaf=5, random_state=42, n_jobs=-1),
    }
    for key, make in builders.items():
        col = REG_TARGETS[key]
        ytr = np.log1p(df_tr[col].values)
        yte = np.log1p(df_te[col].values)
        model = make()
        model.fit(Xtr, ytr)
        pred = model.predict(Xte)
        out[key] = round(float(mean_absolute_error(yte, pred)), 4)  # log-scale MAE
    out["mean_log_mae"] = round(float(np.mean(list(out.values()))), 4)
    return out


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    t0 = time.time()
    print("Loading train/test…")
    raw_train = pd.read_csv(TRAIN_CSV, encoding="latin-1", low_memory=False)
    raw_test = pd.read_csv(TEST_CSV, encoding="latin-1", low_memory=False)

    rt = raw_train.copy()
    rt["Disaster Type"] = rt["Disaster Type"].str.strip()
    rt = rt[rt["Disaster Type"].isin(VALID)].reset_index(drop=True)
    region_freq_map = rt.groupby("Region").size().to_dict()
    month_mode_map = (rt.dropna(subset=["Start Month"]).groupby("Disaster Type")["Start Month"]
                      .agg(lambda x: int(x.mode().iloc[0])).to_dict())

    le_y = LabelEncoder()
    y_all = le_y.fit_transform(rt["Disaster Type"])
    classes = list(le_y.classes_)
    w_tr = np.array([CUSTOM_CLASS_WEIGHTS[c] for c in rt["Disaster Type"]], dtype=np.float32)

    results = {}
    diags = {}
    for arm, mode in [("A_median_impute", "median"), ("D_centroid_impute", "centroid")]:
        print(f"\n=== Arm {arm}  (impute={mode}) ===")
        # encoders are refit per arm but only depend on categoricals (identical across arms)
        encoders = {"continent": LabelEncoder(), "region": LabelEncoder(), "country": LabelEncoder()}
        df_tr, d_tr = build_features(raw_train, mode=mode, region_freq_map=region_freq_map,
                                     encoders=encoders, month_mode_map=month_mode_map, fit=True)
        df_te, _ = build_features(raw_test, mode=mode, region_freq_map=region_freq_map,
                                  encoders=encoders, month_mode_map=month_mode_map, fit=False)

        y_tr = le_y.transform(df_tr["Disaster Type"])
        mask = df_te["Disaster Type"].isin(set(classes))
        df_te = df_te[mask].reset_index(drop=True)
        y_te = le_y.transform(df_te["Disaster Type"])
        diags[arm] = d_tr

        ts = time.time()
        cls = eval_classification(df_tr, y_tr, w_tr, df_te, y_te, classes)
        reg = eval_regression(df_tr, df_te)
        cvm, cvs, folds = cv_macro(df_tr, y_tr, w_tr)
        cls.update({"cv_macro_mean": round(cvm, 4), "cv_macro_std": round(cvs, 4), "cv_folds": folds})
        results[arm] = {"classification": cls, "regression": reg}
        print(f"  train rows={d_tr['rows']}  missing_coord_rows={d_tr['missing_coord_rows']}"
              + (f"  filled_by_centroid={d_tr.get('filled_by_centroid')}" if mode == "centroid" else ""))
        print(f"  macro_f1={cls['macro_f1']:.4f}  weighted_f1={cls['weighted_f1']:.4f}  "
              f"acc={cls['accuracy']:.4f}  CV={cvm:.4f}±{cvs:.4f}")
        print(f"  regression log-MAE: " + "  ".join(f"{k}={v}" for k, v in reg.items()))
        print(f"  ({time.time()-ts:.0f}s)")

    # Decision rule
    a, d = results["A_median_impute"], results["D_centroid_impute"]
    gain = d["classification"]["macro_f1"] - a["classification"]["macro_f1"]
    cv_std = a["classification"]["cv_macro_std"]
    reg_delta = {k: round(d["regression"][k] - a["regression"][k], 4) for k in a["regression"]}
    results["_decision"] = {
        "centroid_holdout_macro_gain": round(gain, 4),
        "baseline_cv_std": cv_std,
        "rule": "keep iff holdout_macro_gain > baseline CV_std",
        "verdict": "KEEP" if gain > cv_std else "DISCARD (within noise)",
        "regression_log_mae_delta_centroid_minus_median": reg_delta,
    }
    results["_diagnostics"] = diags
    results["_meta"] = {
        "fixed_hp": True, "ensemble_weights": {"xgb": W_XGB, "cat": W_CAT},
        "holdout_protocol": "test CSV 1970-2021", "runtime_sec": round(time.time() - t0, 1),
    }

    OUT_JSON.write_text(json.dumps(results, indent=2))
    print(f"\nSaved -> {OUT_JSON}")

    print("\n" + "=" * 78)
    print("CENTROID vs MEDIAN IMPUTATION")
    print("=" * 78)
    print(f"{'Arm':<20}{'macro_f1':>10}{'weighted':>10}{'accuracy':>10}{'CV mean±std':>16}")
    for arm in ("A_median_impute", "D_centroid_impute"):
        c = results[arm]["classification"]
        print(f"{arm:<20}{c['macro_f1']:>10.4f}{c['weighted_f1']:>10.4f}"
              f"{c['accuracy']:>10.4f}{f'{c['cv_macro_mean']:.3f}±{c['cv_macro_std']:.3f}':>16}")
    print("-" * 78)
    print(f"Classification: macro gain={gain:+.4f}  baseline_cv_std={cv_std:.4f}  "
          f"-> {results['_decision']['verdict']}")
    print("\nPer-class F1 (median vs centroid):")
    for c in classes:
        bf = a["classification"]["per_class_f1"][c]
        gf = d["classification"]["per_class_f1"][c]
        print(f"  {c:<22}{bf:>8.3f}{gf:>8.3f}   delta {gf-bf:+.3f}")
    print("\nRegression holdout log-MAE (lower=better; centroid - median):")
    for k in a["regression"]:
        print(f"  {k:<14} median={a['regression'][k]:.4f}  centroid={d['regression'][k]:.4f}"
              f"   delta {reg_delta[k]:+.4f}")
    print(f"\nTotal runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
