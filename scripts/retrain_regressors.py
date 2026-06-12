"""
scripts/retrain_regressors.py

Regressor-only retrain — produces PER-TYPE + DROP-NULL impact regressors WITHOUT
touching the deployed v4.2 classifier (disaster_predictor.pkl) or SHAP.

Why a separate script: a full run_training.py run would retrain (and change) the
classifier. We only want to upgrade the impact regressors, reusing the v4.2 bundle's
encoders so the regressor feature space matches the deployed classifier EXACTLY.

What changes vs the old regressors (validated in
streamlit_eda/experiments/combined_regressor_experiment.py):
  * per-type   — one regressor per disaster type; a type x target combo with fewer
                 than MIN_TYPE_ROWS observed rows falls back to the global model.
  * drop-null  — each regressor trains only on rows where that target was actually
                 recorded (the old code filled nulls with 0, which poisoned the
                 low-coverage targets and produced absurd values like injuries=1
                 next to billion-dollar damage).

New impact_regressor.pkl structure (predictor.py routes on "structure"):
  {
    "structure": "per_type_v1",
    "per_type":  { <disaster_type>: {deaths, injuries, affected, damage} },
    "global":    {deaths, injuries, affected, damage},   # drop-null fallback
    "targets_are_log1p": True,
    "min_type_rows": MIN_TYPE_ROWS,
  }

Run from project root:  py -3.12 scripts/retrain_regressors.py
"""
import re
import warnings
warnings.filterwarnings("ignore")
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from xgboost import XGBRegressor

ROOT = Path(__file__).resolve().parent.parent
TRAIN_CSV = ROOT / "data" / "train" / "1900_2021_DISASTERS.xlsx - train data.csv"
TEST_CSV = ROOT / "data" / "test" / "1970-2021_DISASTERS.xlsx - test data.csv"
MODELS = ROOT / "backend" / "saved_models"

VALID = ["Flood", "Storm", "Earthquake", "Wildfire",
         "Volcanic activity", "Landslide", "Drought", "Extreme temperature"]
TARGET_COLS = {
    "deaths": "Total Deaths", "injuries": "No Injured",
    "affected": "No Affected", "damage": "Total Damages ('000 US$)",
}
RF_TARGETS = {"injuries", "affected"}
MIN_TYPE_ROWS = 30  # below this observed-row count, a type x target falls back to global


def make_reg(key):
    if key in RF_TARGETS:
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


def _enc(le, vals):
    known = set(le.classes_)
    return np.array([le.transform([v])[0] if v in known else 0 for v in vals], dtype=np.int32)


def build(raw, *, le_c, le_r, le_ct, rfm, feats, month_mode_map):
    """16-feature matrix (median imputation) + raw NaN-preserving targets + type array.

    Mirrors scripts/run_training.py exactly so the regressor feature space matches the
    deployed v4.2 classifier. `month_mode_map` is used for the train split (per-type
    mode fill); pass None for the test split (fillna 6), matching run_training.py.
    """
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
    print("Loading v4.2 classifier bundle (for encoders)…")
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
    print("\nTraining global (drop-null) + per-type regressors…")
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
    joblib.dump(new_bundle, MODELS / "impact_regressor.pkl")
    sz = (MODELS / "impact_regressor.pkl").stat().st_size / 1024
    print(f"\nSaved impact_regressor.pkl ({sz:.0f} KB)")

    # ── Honest holdout validation (observed-target rows only) ────────────────
    def route(key, dtype):
        return per_type_reg[dtype].get(key, global_reg[key])

    print("\n=== Honest holdout log-MAE (observed rows) — NEW per-type+drop ===")
    print(f"  {'target':<9}{'new MAE':>10}{'factor':>9}{'  (production fill-0 ref)':>26}")
    prod_ref = {"deaths": 1.0421, "injuries": 2.1919, "affected": 3.1973, "damage": 4.7120}
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
        print(f"  {key:<9}{mae:>10.4f}{np.exp(mae):>8.1f}x"
              f"{f'{prod_ref[key]:.3f} ({np.exp(prod_ref[key]):.0f}x)':>26}")

    print("\nDONE — classifier (disaster_predictor.pkl) and SHAP untouched.")


if __name__ == "__main__":
    main()
