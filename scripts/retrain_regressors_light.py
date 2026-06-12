"""
scripts/retrain_regressors_light.py

LIGHTWEIGHT variant of retrain_regressors.py — same PER-TYPE + DROP-NULL approach,
but uses XGBoost for ALL four targets (no RandomForest). The two RandomForests
(injuries, affected) are the memory hogs that pushed the heavy bundle to ~317 MB
RAM and OOM-crashed Render's 512 MB free tier. XGBoost stores compact trees, so
this bundle is far smaller while keeping the per-type fix.

Writes to impact_regressor_light.pkl (does NOT overwrite the heavy
impact_regressor.pkl, so the two can be compared head-to-head).

Run from project root:  py -3.12 scripts/retrain_regressors_light.py
"""
import re
import warnings
warnings.filterwarnings("ignore")
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parent.parent
TRAIN_CSV = ROOT / "data" / "train" / "1900_2021_DISASTERS.xlsx - train data.csv"
TEST_CSV = ROOT / "data" / "test" / "1970-2021_DISASTERS.xlsx - test data.csv"
MODELS = ROOT / "backend" / "saved_models"
OUT_NAME = "impact_regressor_light.pkl"

VALID = ["Flood", "Storm", "Earthquake", "Wildfire",
         "Volcanic activity", "Landslide", "Drought", "Extreme temperature"]
TARGET_COLS = {
    "deaths": "Total Deaths", "injuries": "No Injured",
    "affected": "No Affected", "damage": "Total Damages ('000 US$)",
}
MIN_TYPE_ROWS = 30  # below this observed-row count, a type x target falls back to global


def make_reg(key):
    """XGBoost for every target. Same params the heavy bundle used for deaths/damage,
    now applied to injuries/affected too (replacing the heavy RandomForests)."""
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


def _enc(le, vals):
    known = set(le.classes_)
    return np.array([le.transform([v])[0] if v in known else 0 for v in vals], dtype=np.int32)


def build(raw, *, le_c, le_r, le_ct, rfm, feats, month_mode_map):
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

    if month_mode_map is not None:
        mr = df["Start Month"].copy()
        for dt, mv in month_mode_map.items():
            mr.loc[mr.isna() & (df["Disaster Type"] == dt)] = mv
        mr = mr.fillna(6).astype(int)
    else:
        mr = df["Start Month"].fillna(6).astype(int)
    df["month_sin"] = np.sin(2 * np.pi * mr / 12)
    df["month_cos"] = np.cos(2 * np.pi * mr / 12)

    df["decade"] = (df["Year"] // 10) * 10
    df["historical_freq"] = df["Region"].map(rfm).fillna(1).astype(int)
    df["log_hist_freq"] = np.log1p(df["historical_freq"])
    df["has_magnitude"] = df["Dis Mag Value"].notna().astype(int)
    df["dis_mag_value"] = pd.to_numeric(df["Dis Mag Value"], errors="coerce").fillna(0.0)
    df["day_offset"] = 0
    df["continent_enc"] = _enc(le_c, df["Continent"])
    df["region_enc"] = _enc(le_r, df["Region"])
    df["country_enc"] = _enc(le_ct, df["Country"])

    X = df[feats].values.astype(np.float32)
    raws = {k: pd.to_numeric(df[col], errors="coerce").clip(lower=0).values
            for k, col in TARGET_COLS.items()}
    return X, raws, df["Disaster Type"].values


def main():
    print("Loading v4.2 classifier bundle (for encoders)...")
    bundle = joblib.load(MODELS / "disaster_predictor.pkl")
    le_c, le_r, le_ct = bundle["le_continent"], bundle["le_region"], bundle["le_country"]
    rfm = bundle["region_freq_map"]
    feats = bundle["feature_names"]
    print(f"  features: {len(feats)}  | regions in freq map: {len(rfm)}")

    raw_tr = pd.read_csv(TRAIN_CSV, encoding="latin-1", low_memory=False)
    rt = raw_tr.copy(); rt["Disaster Type"] = rt["Disaster Type"].str.strip()
    rt = rt[rt["Disaster Type"].isin(VALID)]
    month_mode_map = (rt.dropna(subset=["Start Month"]).groupby("Disaster Type")["Start Month"]
                      .agg(lambda x: int(x.mode().iloc[0])).to_dict())

    Xtr, raws_tr, type_tr = build(raw_tr, le_c=le_c, le_r=le_r, le_ct=le_ct,
                                  rfm=rfm, feats=feats, month_mode_map=month_mode_map)
    Xte, raws_te, type_te = build(pd.read_csv(TEST_CSV, encoding="latin-1", low_memory=False),
                                  le_c=le_c, le_r=le_r, le_ct=le_ct, rfm=rfm, feats=feats,
                                  month_mode_map=None)
    print(f"  train: {Xtr.shape} | holdout: {Xte.shape}")

    global_reg = {}
    per_type_reg = {t: {} for t in VALID}
    print("\nTraining global (drop-null) + per-type regressors [XGBoost-only]...")
    for key in TARGET_COLS:
        raw = raws_tr[key]
        obs = ~np.isnan(raw)
        g = make_reg(key); g.fit(Xtr[obs], np.log1p(raw[obs])); global_reg[key] = g
        n_pt = 0
        for t in VALID:
            sel = (type_tr == t)
            rr = raw[sel]; o = ~np.isnan(rr)
            if o.sum() >= MIN_TYPE_ROWS:
                m = make_reg(key); m.fit(Xtr[sel][o], np.log1p(rr[o]))
                per_type_reg[t][key] = m
                n_pt += 1
        print(f"  {key:<9} global on {obs.sum():,} obs rows | per-type models: {n_pt}/8")

    new_bundle = {
        "structure": "per_type_v1",
        "per_type": per_type_reg,
        "global": global_reg,
        "targets_are_log1p": True,
        "min_type_rows": MIN_TYPE_ROWS,
    }
    joblib.dump(new_bundle, MODELS / OUT_NAME)
    sz = (MODELS / OUT_NAME).stat().st_size / 1024
    print(f"\nSaved {OUT_NAME} ({sz:.0f} KB on disk)")

    # ── Honest holdout validation (observed-target rows only) ────────────────
    def route(key, dtype):
        return per_type_reg[dtype].get(key, global_reg[key])

    print("\n=== Honest holdout log-MAE (observed rows) — LIGHT (XGB-only) ===")
    print(f"  {'target':<9}{'light MAE':>11}{'factor':>9}")
    for key in TARGET_COLS:
        raw = raws_te[key]; obs = ~np.isnan(raw)
        preds = np.empty(obs.sum())
        idx = np.where(obs)[0]
        types_obs = type_te[idx]
        Xobs = Xte[idx]
        for t in VALID:
            loc = np.where(types_obs == t)[0]
            if len(loc):
                preds[loc] = route(key, t).predict(Xobs[loc])
        mae = mean_absolute_error(np.log1p(raw[obs]), preds)
        print(f"  {key:<9}{mae:>11.4f}{np.exp(mae):>8.1f}x")

    print("\nDONE — wrote impact_regressor_light.pkl (heavy bundle untouched).")


if __name__ == "__main__":
    main()
