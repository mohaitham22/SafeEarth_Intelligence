"""
Type-aware regressor experiment — ISOLATED, read-only w.r.t. production.
========================================================================
Hypothesis (user): the impact regressors are disaster-type-BLIND (same 16 features
as the classifier, no disaster_type input), so a Flood and an Earthquake at the same
coordinates get the same raw deaths/injuries/affected/damage. Making them type-aware
should cut regression error — especially on `affected` and `damage`.

This is deployable, not hypothetical: production predict() already takes disaster_type
as INPUT, and predict_impact() derives it from argmax — so a regressor MAY read it.

Three arms, IDENTICAL hyperparameters + preprocessing (median imputation, the same
4 production regressor types). Only the type-handling changes:
  A. baseline     — 16 features, type-blind (reproduces the deployed regressors)
  B. type_feature — 16 + disaster_type_enc (17 features); type is a known input
  C. per_type     — one regressor per disaster type (8 models per target)

Metric: holdout log1p-scale MAE per target (what the models optimise), plus the
"typical error factor" e^MAE for interpretability. Lower is better.

Run from project root:
  py -3.12 streamlit_eda/experiments/regressor_typeaware_experiment.py
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
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parents[2]
TRAIN_CSV = ROOT / "data" / "train" / "1900_2021_DISASTERS.xlsx - train data.csv"
TEST_CSV = ROOT / "data" / "test" / "1970-2021_DISASTERS.xlsx - test data.csv"
OUT_JSON = Path(__file__).resolve().parent / "regressor_typeaware_results.json"

VALID = ["Flood", "Storm", "Earthquake", "Wildfire",
         "Volcanic activity", "Landslide", "Drought", "Extreme temperature"]

BASE_FEATURES = [
    "latitude", "longitude", "abs_latitude", "lon_sin", "lon_cos",
    "continent_enc", "region_enc", "country_enc", "month_sin", "month_cos",
    "dis_mag_value", "has_magnitude", "historical_freq", "log_hist_freq",
    "decade", "day_offset",
]
TYPE_FEATURE = "disaster_type_enc"

# Production v4.2 regressor targets + EXACT columns (from scripts/run_training.py).
REG_TARGETS = {
    "deaths": "Total Deaths",
    "injuries": "No Injured",
    "affected": "No Affected",
    "damage": "Total Damages ('000 US$)",
}
# Production model class per target (XGB for deaths/damage, RF for injuries/affected).
RF_TARGETS = {"injuries", "affected"}


def make_regressor(target: str):
    if target in RF_TARGETS:
        return RandomForestRegressor(n_estimators=200, max_depth=10,
                                     min_samples_leaf=5, random_state=42, n_jobs=-1)
    return XGBRegressor(n_estimators=300, max_depth=5, learning_rate=0.08,
                        subsample=0.8, colsample_bytree=0.8,
                        random_state=42, n_jobs=-1, verbosity=0)


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


def build(raw, *, region_freq_map, month_mode_map, encoders, le_type, fit: bool):
    """Median-imputation 16-feature build + disaster_type_enc + log1p targets."""
    df = raw.copy()
    df["Disaster Type"] = df["Disaster Type"].str.strip()
    df = df[df["Disaster Type"].isin(VALID)].reset_index(drop=True)

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

    # disaster type encoding (known input at predict time — not leakage)
    df[TYPE_FEATURE] = le_type.transform(df["Disaster Type"])

    for col in REG_TARGETS.values():
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).clip(lower=0)

    return df


def log_mae(df_tr, df_te, feats, target):
    col = REG_TARGETS[target]
    ytr = np.log1p(df_tr[col].values)
    yte = np.log1p(df_te[col].values)
    m = make_regressor(target)
    m.fit(df_tr[feats].values.astype(np.float32), ytr)
    pred = m.predict(df_te[feats].values.astype(np.float32))
    return float(mean_absolute_error(yte, pred))


def log_mae_per_type(df_tr, df_te, feats, target):
    """Train one regressor per disaster type; concatenate holdout predictions."""
    col = REG_TARGETS[target]
    preds = np.empty(len(df_te), dtype=float)
    preds[:] = np.nan
    for dtype in VALID:
        tr = df_tr[df_tr["Disaster Type"] == dtype]
        te_idx = np.where(df_te["Disaster Type"].values == dtype)[0]
        if len(te_idx) == 0:
            continue
        if len(tr) < 10:  # too few to train — fall back to global model
            tr = df_tr
        ytr = np.log1p(tr[col].values)
        m = make_regressor(target)
        m.fit(tr[feats].values.astype(np.float32), ytr)
        preds[te_idx] = m.predict(df_te.iloc[te_idx][feats].values.astype(np.float32))
    yte = np.log1p(df_te[col].values)
    return float(mean_absolute_error(yte, preds))


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
    le_type = LabelEncoder().fit(rt["Disaster Type"])
    encoders = {"continent": LabelEncoder(), "region": LabelEncoder(), "country": LabelEncoder()}

    df_tr = build(raw_train, region_freq_map=region_freq_map, month_mode_map=month_mode_map,
                  encoders=encoders, le_type=le_type, fit=True)
    df_te = build(raw_test, region_freq_map=region_freq_map, month_mode_map=month_mode_map,
                  encoders=encoders, le_type=le_type, fit=False)
    print(f"Train: {len(df_tr):,} rows | Holdout: {len(df_te):,} rows")

    base_feats = BASE_FEATURES
    typed_feats = BASE_FEATURES + [TYPE_FEATURE]

    results = {"A_baseline": {}, "B_type_feature": {}, "C_per_type": {}}
    for target in REG_TARGETS:
        ts = time.time()
        results["A_baseline"][target] = round(log_mae(df_tr, df_te, base_feats, target), 4)
        results["B_type_feature"][target] = round(log_mae(df_tr, df_te, typed_feats, target), 4)
        results["C_per_type"][target] = round(log_mae_per_type(df_tr, df_te, base_feats, target), 4)
        print(f"  {target:<9} A={results['A_baseline'][target]:.4f}  "
              f"B={results['B_type_feature'][target]:.4f}  "
              f"C={results['C_per_type'][target]:.4f}   ({time.time()-ts:.0f}s)")

    for arm in results:
        results[arm]["mean"] = round(float(np.mean([results[arm][t] for t in REG_TARGETS])), 4)

    results["_meta"] = {
        "metric": "holdout log1p-scale MAE (lower=better)",
        "production_baseline_ref": {"deaths": 1.1294, "injuries": 1.1079,
                                    "affected": 3.7110, "damage": 3.4623},
        "runtime_sec": round(time.time() - t0, 1),
    }
    OUT_JSON.write_text(json.dumps(results, indent=2))
    print(f"\nSaved -> {OUT_JSON}")

    def factor(mae):
        return np.exp(mae)

    print("\n" + "=" * 86)
    print("TYPE-AWARE REGRESSORS — holdout log-MAE (and typical error factor e^MAE)")
    print("=" * 86)
    print(f"{'target':<10}{'A baseline':>20}{'B type-feat':>20}{'C per-type':>20}{'best':>14}")
    for target in REG_TARGETS:
        a, b, c = (results['A_baseline'][target], results['B_type_feature'][target],
                   results['C_per_type'][target])
        best = min([("A", a), ("B", b), ("C", c)], key=lambda x: x[1])
        print(f"{target:<10}{f'{a:.3f} ({factor(a):.1f}x)':>20}"
              f"{f'{b:.3f} ({factor(b):.1f}x)':>20}"
              f"{f'{c:.3f} ({factor(c):.1f}x)':>20}"
              f"{f'{best[0]} {best[1]:.3f}':>14}")
    print("-" * 86)
    a_m, b_m, c_m = results['A_baseline']['mean'], results['B_type_feature']['mean'], results['C_per_type']['mean']
    print(f"{'mean':<10}{a_m:>20.4f}{b_m:>20.4f}{c_m:>20.4f}")
    print(f"\nDelta vs baseline (negative = better):")
    for target in REG_TARGETS:
        a = results['A_baseline'][target]
        print(f"  {target:<10} B {results['B_type_feature'][target]-a:+.4f}   "
              f"C {results['C_per_type'][target]-a:+.4f}")
    print(f"\nTotal runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
