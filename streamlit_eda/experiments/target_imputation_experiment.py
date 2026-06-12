"""
Missing-target handling experiment — ISOLATED, read-only w.r.t. production.
==========================================================================
Question (user): the regressor target columns (deaths/injuries/affected/damage)
have many nulls. Production fills them with 0. What if we fill with each column's
MEDIAN instead?

Critical point: these are TARGETS, not features. How you fill them changes what the
model learns AND what the MAE measures. A null in EM-DAT almost certainly means
"not recorded", not "zero". So both 0-fill and median-fill are guesses — the only
honest way to compare is to EVALUATE on rows where the target is actually OBSERVED.

Arms (16 features, type-blind, fixed HPs — only target handling changes):
  A_fill_zero    — train targets filled with 0 (production)
  B_fill_median  — train targets filled with the TRAIN-observed median
  C_drop_nulls   — train only on rows where the target is observed
All three are evaluated on the SAME honest holdout: test rows with an OBSERVED target.

  B_illusion     — the median-fill model scored on the MEDIAN-FILLED holdout, to show
                   how misleadingly low the MAE looks when you evaluate on imputed
                   targets (this is the trap, not a real result).

Run from project root:
  py -3.12 streamlit_eda/experiments/target_imputation_experiment.py
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
OUT_JSON = Path(__file__).resolve().parent / "target_imputation_results.json"

VALID = ["Flood", "Storm", "Earthquake", "Wildfire",
         "Volcanic activity", "Landslide", "Drought", "Extreme temperature"]

BASE_FEATURES = [
    "latitude", "longitude", "abs_latitude", "lon_sin", "lon_cos",
    "continent_enc", "region_enc", "country_enc", "month_sin", "month_cos",
    "dis_mag_value", "has_magnitude", "historical_freq", "log_hist_freq",
    "decade", "day_offset",
]
REG_TARGETS = {
    "deaths": "Total Deaths",
    "injuries": "No Injured",
    "affected": "No Affected",
    "damage": "Total Damages ('000 US$)",
}
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


def build_features(raw, *, region_freq_map, month_mode_map, encoders, fit: bool):
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

    # keep RAW numeric targets (NaN preserved) so each arm can fill its own way
    for key, col in REG_TARGETS.items():
        df["_raw_" + key] = pd.to_numeric(df[col], errors="coerce").clip(lower=0)
    return df


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
    encoders = {"continent": LabelEncoder(), "region": LabelEncoder(), "country": LabelEncoder()}

    df_tr = build_features(raw_train, region_freq_map=region_freq_map,
                           month_mode_map=month_mode_map, encoders=encoders, fit=True)
    df_te = build_features(raw_test, region_freq_map=region_freq_map,
                           month_mode_map=month_mode_map, encoders=encoders, fit=False)
    Xtr = df_tr[BASE_FEATURES].values.astype(np.float32)
    Xte = df_te[BASE_FEATURES].values.astype(np.float32)
    print(f"Train: {len(df_tr):,} | Holdout: {len(df_te):,}")

    results = {}
    for target in REG_TARGETS:
        raw_tr = df_tr["_raw_" + target]
        raw_te = df_te["_raw_" + target]
        obs_tr = raw_tr.notna().values
        obs_te = raw_te.notna().values
        med = float(raw_tr[obs_tr].median())  # TRAIN-observed median (no leakage)

        # honest holdout: only rows with an OBSERVED target
        Xte_obs = Xte[obs_te]
        yte_obs = np.log1p(raw_te[obs_te].values)

        # A — fill 0 (production)
        mA = make_regressor(target).fit(Xtr, np.log1p(raw_tr.fillna(0).values))
        a = mean_absolute_error(yte_obs, mA.predict(Xte_obs))

        # B — fill train-observed median
        mB = make_regressor(target).fit(Xtr, np.log1p(raw_tr.fillna(med).values))
        b = mean_absolute_error(yte_obs, mB.predict(Xte_obs))

        # C — drop nulls (train on observed rows only)
        mC = make_regressor(target).fit(Xtr[obs_tr], np.log1p(raw_tr[obs_tr].values))
        c = mean_absolute_error(yte_obs, mC.predict(Xte_obs))

        # B_illusion — median model scored on MEDIAN-FILLED holdout (the trap)
        yte_med = np.log1p(raw_te.fillna(med).values)
        b_ill = mean_absolute_error(yte_med, mB.predict(Xte))

        results[target] = {
            "coverage": round(float(obs_te.mean()), 3),
            "train_observed_median": round(med, 1),
            "honest_holdout_rows": int(obs_te.sum()),
            "A_fill_zero": round(float(a), 4),
            "B_fill_median": round(float(b), 4),
            "C_drop_nulls": round(float(c), 4),
            "B_illusion_on_filled_holdout": round(float(b_ill), 4),
        }
        print(f"  {target:<9} cov={obs_te.mean():.0%}  "
              f"A={a:.4f}  B={b:.4f}  C={c:.4f}   (illusion={b_ill:.4f})")

    results["_meta"] = {
        "metric": "holdout log1p-scale MAE on OBSERVED-target rows (lower=better)",
        "note": "B_illusion_on_filled_holdout evaluates the median model on median-FILLED "
                "targets — artificially low, NOT a real score. Shown to expose the trap.",
        "runtime_sec": round(time.time() - t0, 1),
    }
    OUT_JSON.write_text(json.dumps(results, indent=2))
    print(f"\nSaved -> {OUT_JSON}")

    def fac(m):
        return np.exp(m)

    print("\n" + "=" * 92)
    print("MISSING-TARGET HANDLING — honest holdout log-MAE (observed rows only) + e^MAE factor")
    print("=" * 92)
    print(f"{'target':<10}{'cov':>6}{'A fill-0':>16}{'B fill-median':>18}{'C drop-nulls':>16}{'best':>10}")
    for t in REG_TARGETS:
        r = results[t]
        a, b, c = r["A_fill_zero"], r["B_fill_median"], r["C_drop_nulls"]
        best = min([("A", a), ("B", b), ("C", c)], key=lambda x: x[1])
        print(f"{t:<10}{r['coverage']:>6.0%}"
              f"{f'{a:.3f} ({fac(a):.1f}x)':>16}"
              f"{f'{b:.3f} ({fac(b):.1f}x)':>18}"
              f"{f'{c:.3f} ({fac(c):.1f}x)':>16}{best[0]:>10}")
    print("-" * 92)
    print("THE TRAP — same B model, but scored on MEDIAN-FILLED holdout (looks great, means nothing):")
    for t in REG_TARGETS:
        r = results[t]
        print(f"  {t:<10} honest B={r['B_fill_median']:.3f}   "
              f"illusion={r['B_illusion_on_filled_holdout']:.3f}  "
              f"(fake improvement {r['B_fill_median']-r['B_illusion_on_filled_holdout']:+.3f})")
    print(f"\nTotal runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
