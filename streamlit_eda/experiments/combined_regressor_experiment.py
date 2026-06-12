"""
Combined regressor experiment — ISOLATED, read-only w.r.t. production.
======================================================================
Combines the two orthogonal winners from the prior experiments:
  * model structure : GLOBAL (one model) vs PER-TYPE (one model per disaster type)
  * target handling : fill-0 (production) vs fill-median vs drop-nulls

Full 2 x 3 grid per target. EVERY cell is evaluated on the SAME honest holdout:
test rows where the target is actually OBSERVED (real ground truth). Metric is
log1p-scale MAE (lower=better); e^MAE is the typical multiplicative error factor.

Per-type details:
  * fill-median uses each TYPE's own observed-train median (the consistent choice).
  * drop-nulls trains each type on its observed rows; a type with <10 observed
    rows falls back to the global drop-nulls model.

Run from project root:
  py -3.12 streamlit_eda/experiments/combined_regressor_experiment.py
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
OUT_JSON = Path(__file__).resolve().parent / "combined_regressor_results.json"

VALID = ["Flood", "Storm", "Earthquake", "Wildfire",
         "Volcanic activity", "Landslide", "Drought", "Extreme temperature"]
BASE_FEATURES = [
    "latitude", "longitude", "abs_latitude", "lon_sin", "lon_cos",
    "continent_enc", "region_enc", "country_enc", "month_sin", "month_cos",
    "dis_mag_value", "has_magnitude", "historical_freq", "log_hist_freq",
    "decade", "day_offset",
]
REG_TARGETS = {
    "deaths": "Total Deaths", "injuries": "No Injured",
    "affected": "No Affected", "damage": "Total Damages ('000 US$)",
}
RF_TARGETS = {"injuries", "affected"}
MIN_TYPE_ROWS = 10  # below this, per-type drop-nulls falls back to the global model


def make_regressor(target):
    if target in RF_TARGETS:
        return RandomForestRegressor(n_estimators=200, max_depth=10,
                                     min_samples_leaf=5, random_state=42, n_jobs=-1)
    return XGBRegressor(n_estimators=300, max_depth=5, learning_rate=0.08,
                        subsample=0.8, colsample_bytree=0.8,
                        random_state=42, n_jobs=-1, verbosity=0)


def parse_coord(val):
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


def build_features(raw, *, region_freq_map, month_mode_map, encoders, fit):
    df = raw.copy()
    df["Disaster Type"] = df["Disaster Type"].str.strip()
    df = df[df["Disaster Type"].isin(VALID)].reset_index(drop=True)
    for col, (lo, hi) in [("Latitude", (-90.0, 90.0)), ("Longitude", (-180.0, 180.0))]:
        df[col] = df[col].apply(parse_coord)
        df.loc[(df[col] < lo) | (df[col] > hi), col] = np.nan
        df[col] = df[col].fillna(df.groupby("Country")[col].transform("median"))
        df[col] = df[col].fillna(df.groupby("Continent")[col].transform("median"))
        df[col] = df[col].fillna(df[col].median())
    df["latitude"] = df["Latitude"]; df["longitude"] = df["Longitude"]
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
    lc, lr, lct = encoders["continent"], encoders["region"], encoders["country"]
    if fit:
        df["continent_enc"] = lc.fit_transform(df["Continent"])
        df["region_enc"] = lr.fit_transform(df["Region"])
        df["country_enc"] = lct.fit_transform(df["Country"])
    else:
        def enc(le, vals):
            k = set(le.classes_)
            return np.array([le.transform([v])[0] if v in k else 0 for v in vals], dtype=np.int32)
        df["continent_enc"] = enc(lc, df["Continent"])
        df["region_enc"] = enc(lr, df["Region"])
        df["country_enc"] = enc(lct, df["Country"])
    for key, col in REG_TARGETS.items():
        df["_raw_" + key] = pd.to_numeric(df[col], errors="coerce").clip(lower=0)
    return df


def _ytrain(raw, mode, med):
    """Return (X-mask, log1p target) for a fill mode over a raw target series (np array)."""
    if mode == "fill0":
        return np.ones(len(raw), bool), np.log1p(np.nan_to_num(raw, nan=0.0))
    if mode == "median":
        filled = np.where(np.isnan(raw), med, raw)
        return np.ones(len(raw), bool), np.log1p(filled)
    # drop
    obs = ~np.isnan(raw)
    return obs, np.log1p(np.where(obs, raw, 0.0))


def global_mae(target, mode, Xtr, raw_tr, Xeval, yeval, med):
    mask, ytr = _ytrain(raw_tr, mode, med)
    m = make_regressor(target)
    m.fit(Xtr[mask], ytr[mask])
    return mean_absolute_error(yeval, m.predict(Xeval))


def per_type_mae(target, mode, Xtr, raw_tr, type_tr, eval_idx, Xte, yeval, type_te, glob_med):
    """Per-type predictions for the honest eval rows."""
    preds = np.full(len(eval_idx), np.nan)
    eval_types = type_te[eval_idx]
    Xeval = Xte[eval_idx]

    # global drop fallback model (trained once) for sparse types under 'drop'
    fallback = None
    if mode == "drop":
        obs = ~np.isnan(raw_tr)
        fb = make_regressor(target); fb.fit(Xtr[obs], np.log1p(raw_tr[obs]))
        fallback = fb

    for dtype in VALID:
        te_local = np.where(eval_types == dtype)[0]
        if len(te_local) == 0:
            continue
        tr_t = (type_tr == dtype)
        rt = raw_tr[tr_t]
        if mode == "drop":
            obs = ~np.isnan(rt)
            if obs.sum() < MIN_TYPE_ROWS:
                preds[te_local] = fallback.predict(Xeval[te_local])
                continue
            m = make_regressor(target); m.fit(Xtr[tr_t][obs], np.log1p(rt[obs]))
        else:
            med_t = np.nanmedian(rt) if (~np.isnan(rt)).any() else glob_med
            mask, ytr = _ytrain(rt, mode, med_t)
            m = make_regressor(target); m.fit(Xtr[tr_t][mask], ytr[mask])
        preds[te_local] = m.predict(Xeval[te_local])
    return mean_absolute_error(yeval, preds)


def main():
    t0 = time.time()
    print("Loading train/test…")
    raw_train = pd.read_csv(TRAIN_CSV, encoding="latin-1", low_memory=False)
    raw_test = pd.read_csv(TEST_CSV, encoding="latin-1", low_memory=False)
    rt = raw_train.copy(); rt["Disaster Type"] = rt["Disaster Type"].str.strip()
    rt = rt[rt["Disaster Type"].isin(VALID)].reset_index(drop=True)
    region_freq_map = rt.groupby("Region").size().to_dict()
    month_mode_map = (rt.dropna(subset=["Start Month"]).groupby("Disaster Type")["Start Month"]
                      .agg(lambda x: int(x.mode().iloc[0])).to_dict())
    enc = {"continent": LabelEncoder(), "region": LabelEncoder(), "country": LabelEncoder()}
    df_tr = build_features(raw_train, region_freq_map=region_freq_map, month_mode_map=month_mode_map, encoders=enc, fit=True)
    df_te = build_features(raw_test, region_freq_map=region_freq_map, month_mode_map=month_mode_map, encoders=enc, fit=False)
    Xtr = df_tr[BASE_FEATURES].values.astype(np.float32)
    Xte = df_te[BASE_FEATURES].values.astype(np.float32)
    type_tr = df_tr["Disaster Type"].values
    type_te = df_te["Disaster Type"].values
    print(f"Train: {len(df_tr):,} | Holdout: {len(df_te):,}")

    modes = ["fill0", "median", "drop"]
    results = {}
    for target in REG_TARGETS:
        raw_tr = df_tr["_raw_" + target].values
        raw_te = df_te["_raw_" + target].values
        obs_te = ~np.isnan(raw_te)
        eval_idx = np.where(obs_te)[0]
        yeval = np.log1p(raw_te[eval_idx])
        Xeval = Xte[eval_idx]
        med = float(np.nanmedian(raw_tr[~np.isnan(raw_tr)]))

        cell = {}
        for mode in modes:
            cell[f"global_{mode}"] = round(global_mae(target, mode, Xtr, raw_tr, Xeval, yeval, med), 4)
            cell[f"pertype_{mode}"] = round(per_type_mae(target, mode, Xtr, raw_tr, type_tr, eval_idx, Xte, yeval, type_te, med), 4)
        cell["coverage"] = round(float(obs_te.mean()), 3)
        results[target] = cell
        print(f"  {target:<9} cov={obs_te.mean():.0%}  "
              + "  ".join(f"{k.split('_')[0][0]}-{k.split('_')[1]}={v}" for k, v in cell.items() if k != "coverage"))

    results["_meta"] = {"metric": "honest holdout log1p-MAE (observed rows only)",
                        "runtime_sec": round(time.time() - t0, 1)}
    OUT_JSON.write_text(json.dumps(results, indent=2))
    print(f"\nSaved -> {OUT_JSON}")

    def fac(m):
        return np.exp(m)

    print("\n" + "=" * 100)
    print("COMBINED — honest holdout log-MAE (e^MAE factor). cols: GLOBAL | PER-TYPE for each fill")
    print("=" * 100)
    hdr = f"{'target':<10}{'cov':>5}"
    for m in modes:
        hdr += f"{'G '+m:>14}{'PT '+m:>14}"
    print(hdr)
    for target in REG_TARGETS:
        c = results[target]
        line = f"{target:<10}{c['coverage']:>5.0%}"
        for m in modes:
            line += f"{f'{c[f"global_{m}"]:.2f}({fac(c[f"global_{m}"]):.0f}x)':>14}"
            line += f"{f'{c[f"pertype_{m}"]:.2f}({fac(c[f"pertype_{m}"]):.0f}x)':>14}"
        print(line)
    print("-" * 100)
    print("\nBest cell per target (lowest honest log-MAE):")
    for target in REG_TARGETS:
        c = {k: v for k, v in results[target].items() if k != "coverage"}
        bk = min(c, key=c.get)
        prod = results[target]["global_fill0"]
        print(f"  {target:<10} {bk:<16} {c[bk]:.3f} ({fac(c[bk]):.1f}x)   "
              f"vs production global_fill0 {prod:.3f} ({fac(prod):.1f}x)   "
              f"factor cut {fac(prod)/fac(c[bk]):.1f}x")
    print(f"\nTotal runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
