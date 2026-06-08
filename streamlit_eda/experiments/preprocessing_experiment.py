"""
Preprocessing experiment — ISOLATED, read-only w.r.t. production.
==================================================================
Goal: measure whether the EDA-motivated preprocessing/feature steps improve
accuracy, compared HEAD-TO-HEAD against the live v4.2 model.

This script:
  * touches NOTHING in backend/, scripts/, saved_models/, or metrics/
  * reproduces the production v4.2 pipeline EXACTLY as the baseline arm
    (XGB 0.6 + CatBoost 0.4, 16 features, latin-1 load, country->continent->global
     coord imputation, custom class weights, holdout = test CSV 1970-2021)
  * holds hyperparameters FIXED across every arm, so the only thing that changes
    is the feature set — a clean ablation
  * evaluates every arm on the SAME holdout protocol production used
  * runs 5-fold CV on TRAIN for the legitimate arms, then applies the project's
    decision rule:  keep iff  holdout_gain > CV_std

Arms:
  A. baseline            — the 16 production features (fixed-HP reproduction)
  B. geo_features        — baseline + coast distance + climate zone + hemisphere
                           (legitimate: pure functions of lat/lon, available at
                            inference for any point, NOT derived from the label)
  C. leaky_mag_scale     — baseline + per-scale magnitude columns
                           (ILLUSTRATIVE LEAK: Dis Mag Scale == the label for ~93%
                            of rows, so this inflates offline accuracy and will NOT
                            generalize — included to show a tempting trap)

Run from project root:  py -3.12 streamlit_eda/experiments/preprocessing_experiment.py
"""
from __future__ import annotations

import json
import re
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
from scipy import ndimage
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier
from catboost import CatBoostClassifier
from global_land_mask import globe

# --------------------------------------------------------------------------- #
# Paths & constants (mirror scripts/run_training.py)
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parents[2]
TRAIN_CSV = ROOT / "data" / "train" / "1900_2021_DISASTERS.xlsx - train data.csv"
TEST_CSV = ROOT / "data" / "test" / "1970-2021_DISASTERS.xlsx - test data.csv"
METRICS = ROOT / "metrics" / "baseline_v4_1_metrics.json"
OUT_JSON = Path(__file__).resolve().parent / "results.json"

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
GEO_FEATURES = ["coast_distance_km", "climate_zone", "hemisphere", "is_coastal"]
LEAK_FEATURES = ["mag_richter", "mag_kph", "mag_km2_log", "mag_celsius"]

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
# Coast-distance grid (pure function of lat/lon — no label, no network)
# --------------------------------------------------------------------------- #
print("Building global coast-distance grid (0.5 deg)…")
_GLAT = np.arange(-90.0, 90.01, 0.5)
_GLON = np.arange(-180.0, 180.01, 0.5)
_LonG, _LatG = np.meshgrid(_GLON, _GLAT)
_land = globe.is_land(_LatG, _LonG)
_dist_to_ocean = ndimage.distance_transform_edt(_land)
_dist_to_land = ndimage.distance_transform_edt(~_land)
_coast_cells = np.where(_land, _dist_to_ocean, _dist_to_land)
_KM_PER_CELL = 0.5 * 111.0  # ~55.5 km per 0.5deg cell (equatorial approx)
_COAST_KM = _coast_cells * _KM_PER_CELL


def coast_distance_km(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    i = np.clip(np.round((np.asarray(lat) + 90.0) / 0.5).astype(int), 0, len(_GLAT) - 1)
    j = np.clip(np.round((np.asarray(lon) + 180.0) / 0.5).astype(int), 0, len(_GLON) - 1)
    return _COAST_KM[i, j]


# --------------------------------------------------------------------------- #
# Feature engineering — builds base + geo + leak columns on a dataframe
# --------------------------------------------------------------------------- #
def build_features(df: pd.DataFrame, *, region_freq_map, encoders, fit: bool) -> pd.DataFrame:
    df = df.copy()
    df["Disaster Type"] = df["Disaster Type"].str.strip()
    df = df[df["Disaster Type"].isin(VALID)].reset_index(drop=True)

    # lat/lon parse + impute (country -> continent -> global)
    for col, (lo, hi) in [("Latitude", (-90.0, 90.0)), ("Longitude", (-180.0, 180.0))]:
        df[col] = df[col].apply(parse_coord)
        df.loc[(df[col] < lo) | (df[col] > hi), col] = np.nan
        df[col] = df[col].fillna(df.groupby("Country")[col].transform("median"))
        df[col] = df[col].fillna(df.groupby("Continent")[col].transform("median"))
        df[col] = df[col].fillna(df[col].median())

    df["latitude"] = df["Latitude"]
    df["longitude"] = df["Longitude"]
    df["abs_latitude"] = df["latitude"].abs()
    df["lon_sin"] = np.sin(2 * np.pi * df["longitude"] / 360)
    df["lon_cos"] = np.cos(2 * np.pi * df["longitude"] / 360)

    if fit:
        raw = (df.dropna(subset=["Start Month"]).groupby("Disaster Type")["Start Month"]
               .agg(lambda x: int(x.mode().iloc[0])).to_dict())
        build_features._month_mode = raw
        mr = df["Start Month"].copy()
        for dt, mv in raw.items():
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

    # --- GEO features (legitimate, label-free) ---
    df["coast_distance_km"] = coast_distance_km(df["latitude"].values, df["longitude"].values)
    al = df["abs_latitude"].values
    df["climate_zone"] = np.digitize(al, [23.5, 35.0, 55.0, 66.5]).astype(float)
    df["hemisphere"] = (df["latitude"] >= 0).astype(float)
    df["is_coastal"] = (df["coast_distance_km"] < 100.0).astype(float)

    # --- LEAK features (per-scale magnitude — Dis Mag Scale ~= the label) ---
    scale = df["Dis Mag Scale"].astype(str).str.strip()
    val = pd.to_numeric(df["Dis Mag Value"], errors="coerce")
    df["mag_richter"] = np.where(scale.eq("Richter"), val, 0.0)
    df["mag_kph"] = np.where(scale.eq("Kph"), val, 0.0)
    df["mag_km2_log"] = np.where(scale.eq("Km2"), np.log1p(val.clip(lower=0)), 0.0)
    df["mag_celsius"] = np.where(scale.eq("°C") | scale.eq("Â°C"), val, 0.0)
    for c in LEAK_FEATURES:
        df[c] = df[c].fillna(0.0)

    return df


# --------------------------------------------------------------------------- #
# Model: XGB(0.6) + CatBoost(0.4) ensemble, fixed HPs
# --------------------------------------------------------------------------- #
def fit_ensemble(Xtr, ytr, w):
    xgb = XGBClassifier(**XGB_PARAMS)
    xgb.fit(Xtr, ytr, sample_weight=w)
    cat = CatBoostClassifier(**CAT_PARAMS)
    cat.fit(Xtr, ytr, sample_weight=w)
    return xgb, cat


def ensemble_pred(xgb, cat, X):
    return np.argmax(W_XGB * xgb.predict_proba(X) + W_CAT * cat.predict_proba(X), axis=1)


def eval_arm(feats, Xtr, ytr, w, Xte, yte, classes):
    xgb, cat = fit_ensemble(Xtr[feats].values.astype(np.float32), ytr, w)
    pred = ensemble_pred(xgb, cat, Xte[feats].values.astype(np.float32))
    per_class = f1_score(yte, pred, average=None, labels=range(len(classes)), zero_division=0)
    return {
        "macro_f1": float(f1_score(yte, pred, average="macro", zero_division=0)),
        "weighted_f1": float(f1_score(yte, pred, average="weighted", zero_division=0)),
        "accuracy": float(accuracy_score(yte, pred)),
        "per_class_f1": {classes[i]: float(per_class[i]) for i in range(len(classes))},
    }


def cv_macro(feats, Xtr, ytr, w, n_splits=5):
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    Xv = Xtr[feats].values.astype(np.float32)
    scores = []
    for ti, vi in skf.split(Xv, ytr):
        xgb, cat = fit_ensemble(Xv[ti], ytr[ti], w[ti])
        pred = ensemble_pred(xgb, cat, Xv[vi])
        scores.append(f1_score(ytr[vi], pred, average="macro", zero_division=0))
    return float(np.mean(scores)), float(np.std(scores)), [round(s, 4) for s in scores]


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    t0 = time.time()
    print("Loading train/test…")
    encoders = {"continent": LabelEncoder(), "region": LabelEncoder(), "country": LabelEncoder()}

    raw_train = pd.read_csv(TRAIN_CSV, encoding="latin-1")
    raw_train["Disaster Type"] = raw_train["Disaster Type"].str.strip()
    rt = raw_train[raw_train["Disaster Type"].isin(VALID)].reset_index(drop=True)
    region_freq_map = rt.groupby("Region").size().to_dict()

    df_tr = build_features(raw_train, region_freq_map=region_freq_map, encoders=encoders, fit=True)
    df_te = build_features(pd.read_csv(TEST_CSV, encoding="latin-1"),
                           region_freq_map=region_freq_map, encoders=encoders, fit=False)

    le_y = LabelEncoder()
    y_tr = le_y.fit_transform(df_tr["Disaster Type"])
    classes = list(le_y.classes_)

    mask = df_te["Disaster Type"].isin(set(classes))
    df_te = df_te[mask].reset_index(drop=True)
    y_te = le_y.transform(df_te["Disaster Type"])
    w_tr = np.array([CUSTOM_CLASS_WEIGHTS[c] for c in df_tr["Disaster Type"]], dtype=np.float32)

    print(f"Train: {len(df_tr):,} rows | Holdout: {len(df_te):,} rows | Classes: {classes}")
    print(f"Coast km — sample stats: min={_COAST_KM.min():.0f} max={_COAST_KM.max():.0f}")

    arms = {
        "A_baseline": BASE_FEATURES,
        "B_geo_features": BASE_FEATURES + GEO_FEATURES,
        "C_leaky_mag_scale": BASE_FEATURES + LEAK_FEATURES,
    }

    results = {}
    for name, feats in arms.items():
        print(f"\n=== Arm {name}  ({len(feats)} features) — holdout fit ===")
        ts = time.time()
        results[name] = eval_arm(feats, df_tr, y_tr, w_tr, df_te, y_te, classes)
        results[name]["n_features"] = len(feats)
        print(f"  macro_f1={results[name]['macro_f1']:.4f}  "
              f"weighted_f1={results[name]['weighted_f1']:.4f}  "
              f"accuracy={results[name]['accuracy']:.4f}  ({time.time()-ts:.0f}s)")

    # 5-fold CV (legitimate arms only) for the decision rule
    print("\n=== 5-fold CV (baseline + geo) ===")
    for name in ["A_baseline", "B_geo_features"]:
        ts = time.time()
        mean, std, folds = cv_macro(arms[name], df_tr, y_tr, w_tr)
        results[name]["cv_macro_mean"] = round(mean, 4)
        results[name]["cv_macro_std"] = round(std, 4)
        results[name]["cv_folds"] = folds
        print(f"  {name}: CV macro {mean:.4f} +/- {std:.4f}  ({time.time()-ts:.0f}s)")

    # Decision rule: keep geo iff holdout_gain > baseline CV_std
    gain = results["B_geo_features"]["macro_f1"] - results["A_baseline"]["macro_f1"]
    cv_std = results["A_baseline"].get("cv_macro_std", 0.0)
    results["_decision"] = {
        "geo_holdout_gain_vs_baseline": round(gain, 4),
        "baseline_cv_std": cv_std,
        "rule": "keep iff holdout_gain > baseline CV_std",
        "verdict": "KEEP" if gain > cv_std else "DISCARD (within noise)",
    }

    # Reference: live production numbers
    prod = json.loads(METRICS.read_text())
    results["_production_v42"] = {
        "macro_f1": 0.7052, "weighted_f1": 0.7587, "accuracy": 0.7467,
        "note": "live v4.2 (Optuna-tuned XGB+CAT). baseline arm here is a fixed-HP "
                "reproduction, so compare DELTAS not absolute values.",
        "v41_reference_per_class": prod["per_class_f1_sorted"],
    }
    results["_meta"] = {
        "fixed_hp": True, "xgb_params": XGB_PARAMS, "cat_params": CAT_PARAMS,
        "ensemble_weights": {"xgb": W_XGB, "cat": W_CAT},
        "holdout_protocol": "test CSV 1970-2021 (same as production)",
        "runtime_sec": round(time.time() - t0, 1),
    }

    OUT_JSON.write_text(json.dumps(results, indent=2))
    print(f"\nSaved -> {OUT_JSON}")

    # Console comparison table
    print("\n" + "=" * 78)
    print("COMPARISON vs LIVE v4.2 (0.7052 macro / 0.7587 weighted / 0.7467 acc)")
    print("=" * 78)
    print(f"{'Arm':<20}{'macro_f1':>10}{'weighted':>10}{'accuracy':>10}{'CV mean±std':>16}")
    for name in ["A_baseline", "B_geo_features", "C_leaky_mag_scale"]:
        r = results[name]
        cv = (f"{r['cv_macro_mean']:.3f}±{r['cv_macro_std']:.3f}"
              if "cv_macro_mean" in r else "—")
        print(f"{name:<20}{r['macro_f1']:>10.4f}{r['weighted_f1']:>10.4f}"
              f"{r['accuracy']:>10.4f}{cv:>16}")
    print("-" * 78)
    print(f"Decision (geo): gain={gain:+.4f}  baseline_cv_std={cv_std:.4f}  "
          f"-> {results['_decision']['verdict']}")
    print("\nPer-class F1 (baseline vs geo):")
    for c in classes:
        b = results["A_baseline"]["per_class_f1"][c]
        g = results["B_geo_features"]["per_class_f1"][c]
        print(f"  {c:<22}{b:>8.3f}{g:>8.3f}   delta {g-b:+.3f}")
    print(f"\nTotal runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
