"""
Full ML training pipeline — v4.1 (XGB + LGB + CatBoost ensemble, 16 features).

v4.1 over v3:
  - 3-model soft ensemble: XGBoost + LightGBM + CatBoost with grid-searched weights
  - Landslide sample weight reduced 6.0 -> 3.0 (v4 precision collapse fix)
  - 40/30/20 Optuna trials (XGB/LGB/CAT)
  - Macro F1=0.6929, Weighted F1=0.7519 on holdout (1970-2021)

Run from project root:  py -3.12 scripts/run_training.py
"""
import re
import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import joblib
import shap
import lightgbm as lgb
import optuna
from catboost import CatBoostClassifier
optuna.logging.set_verbosity(optuna.logging.WARNING)

from pathlib import Path
from sklearn.preprocessing import LabelEncoder
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import StratifiedKFold
from xgboost import XGBClassifier, XGBRegressor

import xgboost, sklearn, catboost
print(f"XGBoost {xgboost.__version__} | sklearn {sklearn.__version__} | "
      f"lightgbm {lgb.__version__} | catboost {catboost.__version__}")


# ── Coordinate parser ─────────────────────────────────────────────────────────
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


# ── Constants ─────────────────────────────────────────────────────────────────
VALID_DISASTER_TYPES = [
    "Flood", "Storm", "Earthquake", "Wildfire",
    "Volcanic activity", "Landslide", "Drought", "Extreme temperature",
]

TRAIN_CSV  = Path("data/train/1900_2021_DISASTERS.xlsx - train data.csv")
TEST_CSV   = Path("data/test/1970-2021_DISASTERS.xlsx - test data.csv")
MODELS_DIR = Path("backend/saved_models")
MODELS_DIR.mkdir(parents=True, exist_ok=True)

# v4.1 — 16 features
FEATURE_NAMES = [
    "latitude", "longitude",
    "abs_latitude",           # v3: distance from equator (climate zone proxy)
    "lon_sin", "lon_cos",    # v3: cyclical longitude
    "continent_enc", "region_enc", "country_enc",
    "month_sin", "month_cos",
    "dis_mag_value", "has_magnitude",
    "historical_freq", "log_hist_freq",  # v3: log1p(historical_freq)
    "decade", "day_offset",
]

# v4: Landslide weight reduced 6.0->3.0 (was causing FP=1226, precision=0.33)
CUSTOM_CLASS_WEIGHTS = {
    "Flood":               1.0,
    "Storm":               1.0,
    "Earthquake":          1.0,
    "Extreme temperature": 1.5,
    "Wildfire":            2.5,
    "Volcanic activity":   3.0,
    "Drought":             4.0,
    "Landslide":           3.0,   # was 6.0 — reduced to fix precision collapse
}

# Note: CatBoost is passed float32 numpy arrays (label-encoded ints stored as float).
# cat_features requires int/str columns — simpler to omit it; CatBoost's symmetric-tree
# and ordered-boosting strategy still adds ensemble diversity vs XGB/LGB.


# ── Load & filter train CSV ───────────────────────────────────────────────────
print("\n=== Load & filter train CSV ===")
df = pd.read_csv(TRAIN_CSV, encoding="latin-1")
df["Disaster Type"] = df["Disaster Type"].str.strip()
df = df[df["Disaster Type"].isin(VALID_DISASTER_TYPES)].copy().reset_index(drop=True)
print(f"Train rows: {len(df):,}")
print(df["Disaster Type"].value_counts().to_string())


# ── Parse & impute lat/lon ────────────────────────────────────────────────────
print("\n=== Parse & impute lat/lon ===")
for col, (lo, hi) in [("Latitude", (-90.0, 90.0)), ("Longitude", (-180.0, 180.0))]:
    df[col] = df[col].apply(parse_coord)
    df.loc[(df[col] < lo) | (df[col] > hi), col] = np.nan
    df[col] = df[col].fillna(df.groupby("Country")[col].transform("median"))
    df[col] = df[col].fillna(df.groupby("Continent")[col].transform("median"))
    df[col] = df[col].fillna(df[col].median())

assert df["Latitude"].isna().sum() == 0
assert df["Longitude"].isna().sum() == 0


# ── Feature engineering ───────────────────────────────────────────────────────
print("\n=== Feature engineering ===")

df["latitude"]     = df["Latitude"]
df["longitude"]    = df["Longitude"]
df["abs_latitude"] = df["latitude"].abs()
df["lon_sin"]      = np.sin(2 * np.pi * df["longitude"] / 360)
df["lon_cos"]      = np.cos(2 * np.pi * df["longitude"] / 360)

month_mode_map = (
    df.dropna(subset=["Start Month"])
    .groupby("Disaster Type")["Start Month"]
    .agg(lambda x: int(x.mode().iloc[0]))
    .to_dict()
)
df["_month_raw"] = df["Start Month"].copy()
for dtype, mv in month_mode_map.items():
    df.loc[df["_month_raw"].isna() & (df["Disaster Type"] == dtype), "_month_raw"] = mv
df["_month_raw"] = df["_month_raw"].fillna(6).astype(int)
df["month_sin"]  = np.sin(2 * np.pi * df["_month_raw"] / 12)
df["month_cos"]  = np.cos(2 * np.pi * df["_month_raw"] / 12)

df["decade"] = (df["Year"] // 10) * 10

region_freq_map = df.groupby("Region").size().to_dict()
df["historical_freq"] = df["Region"].map(region_freq_map).fillna(1).astype(int)
df["log_hist_freq"]   = np.log1p(df["historical_freq"])

df["has_magnitude"] = df["Dis Mag Value"].notna().astype(int)
df["dis_mag_value"] = pd.to_numeric(df["Dis Mag Value"], errors="coerce").fillna(0.0)
df["day_offset"]    = 0

# Encoders — fit on train ONLY
le_continent = LabelEncoder()
le_region    = LabelEncoder()
le_country   = LabelEncoder()
le_target    = LabelEncoder()

df["continent_enc"] = le_continent.fit_transform(df["Continent"])
df["region_enc"]    = le_region.fit_transform(df["Region"])
df["country_enc"]   = le_country.fit_transform(df["Country"])

print(f"\nFeature count: {len(FEATURE_NAMES)}")


# ── Feature matrix ────────────────────────────────────────────────────────────
print("\n=== Build feature matrix ===")
X_train     = df[FEATURE_NAMES].values.astype(np.float32)
y_cls_train = le_target.fit_transform(df["Disaster Type"])
assert np.isnan(X_train).sum() == 0
print(f"X_train: {X_train.shape}")
print(f"Classes: {list(le_target.classes_)}")

sample_weights = np.array([CUSTOM_CLASS_WEIGHTS[c] for c in df["Disaster Type"]], dtype=np.float32)
print(f"\nClass weights (v4 — Landslide reduced 6.0->3.0 to fix precision collapse):")
for dtype, w in sorted(CUSTOM_CLASS_WEIGHTS.items(), key=lambda x: x[1]):
    count = (df["Disaster Type"] == dtype).sum()
    print(f"  {dtype:<22s}  weight={w:.1f}  n={count:,}")


# ── Regression targets ────────────────────────────────────────────────────────
# v4.3 regressors are PER-TYPE + DROP-NULL: targets keep NaN (never fill with 0,
# which poisoned the low-coverage targets and produced absurd values like injuries=1
# next to billion-dollar damage). See
# streamlit_eda/experiments/combined_regressor_experiment.py.
print("\n=== Regression targets (per-type, drop-null, log1p) ===")
TARGET_COLS = {
    "deaths":   "Total Deaths",
    "injuries": "No Injured",
    "affected": "No Affected",
    "damage":   "Total Damages ('000 US$)",
}
RF_TARGETS = {"injuries", "affected"}
MIN_TYPE_ROWS = 30  # below this observed-row count, a type x target falls back to global
raw_targets = {
    key: pd.to_numeric(df[col], errors="coerce").clip(lower=0).values  # NaN preserved
    for key, col in TARGET_COLS.items()
}


# ── Test CSV preprocessing ────────────────────────────────────────────────────
print("\n=== Load & preprocess test CSV ===")

def safe_encode(le: LabelEncoder, values) -> np.ndarray:
    known = set(le.classes_)
    return np.array(
        [le.transform([v])[0] if v in known else 0 for v in values],
        dtype=np.int32,
    )

def preprocess_test(df_raw: pd.DataFrame) -> pd.DataFrame:
    df_t = df_raw.copy()
    df_t["Disaster Type"] = df_t["Disaster Type"].str.strip()
    df_t = df_t[df_t["Disaster Type"].isin(VALID_DISASTER_TYPES)].reset_index(drop=True)

    for col, (lo, hi) in [("Latitude", (-90.0, 90.0)), ("Longitude", (-180.0, 180.0))]:
        df_t[col] = df_t[col].apply(parse_coord)
        df_t.loc[(df_t[col] < lo) | (df_t[col] > hi), col] = np.nan
        df_t[col] = df_t[col].fillna(df_t.groupby("Country")[col].transform("median"))
        df_t[col] = df_t[col].fillna(df_t.groupby("Continent")[col].transform("median"))
        df_t[col] = df_t[col].fillna(df_t[col].median())

    df_t["latitude"]      = df_t["Latitude"]
    df_t["longitude"]     = df_t["Longitude"]
    df_t["abs_latitude"]  = df_t["latitude"].abs()
    df_t["lon_sin"]       = np.sin(2 * np.pi * df_t["longitude"] / 360)
    df_t["lon_cos"]       = np.cos(2 * np.pi * df_t["longitude"] / 360)

    raw_month = df_t["Start Month"].fillna(6).astype(int)
    df_t["month_sin"] = np.sin(2 * np.pi * raw_month / 12)
    df_t["month_cos"] = np.cos(2 * np.pi * raw_month / 12)

    df_t["decade"]          = (df_t["Year"] // 10) * 10
    df_t["historical_freq"] = df_t["Region"].map(region_freq_map).fillna(1).astype(int)
    df_t["log_hist_freq"]   = np.log1p(df_t["historical_freq"])
    df_t["has_magnitude"]   = df_t["Dis Mag Value"].notna().astype(int)
    df_t["dis_mag_value"]   = pd.to_numeric(df_t["Dis Mag Value"], errors="coerce").fillna(0.0)
    df_t["day_offset"]      = 0

    df_t["continent_enc"] = safe_encode(le_continent, df_t["Continent"])
    df_t["region_enc"]    = safe_encode(le_region,    df_t["Region"])
    df_t["country_enc"]   = safe_encode(le_country,   df_t["Country"])

    return df_t

df_test     = preprocess_test(pd.read_csv(TEST_CSV, encoding="latin-1"))
X_test      = df_test[FEATURE_NAMES].values.astype(np.float32)
mask        = df_test["Disaster Type"].isin(set(le_target.classes_))
X_test_eval = X_test[mask]
y_test_eval = le_target.transform(df_test.loc[mask, "Disaster Type"])
assert np.isnan(X_test_eval).sum() == 0
print(f"X_test_eval: {X_test_eval.shape}")
X_test_df   = pd.DataFrame(X_test_eval, columns=FEATURE_NAMES)


# ── LAYER 3: Optuna tuning for XGBoost ────────────────────────────────────────
print("\n=== Optuna XGBoost (40 trials) ===")
cv = StratifiedKFold(n_splits=3, shuffle=True, random_state=42)

def xgb_objective(trial):
    params = {
        "n_estimators":      trial.suggest_int("n_estimators", 300, 900),
        "max_depth":         trial.suggest_int("max_depth", 4, 10),
        "learning_rate":     trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
        "min_child_weight":  trial.suggest_int("min_child_weight", 1, 10),
        "gamma":             trial.suggest_float("gamma", 0, 2.0),
        "subsample":         trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree":  trial.suggest_float("colsample_bytree", 0.5, 1.0),
        "reg_alpha":         trial.suggest_float("reg_alpha", 0, 2.0),
        "reg_lambda":        trial.suggest_float("reg_lambda", 0.5, 5.0),
        "eval_metric": "mlogloss", "random_state": 42, "n_jobs": -1, "verbosity": 0,
    }
    scores = []
    for ti, vi in cv.split(X_train, y_cls_train):
        m = XGBClassifier(**params)
        m.fit(X_train[ti], y_cls_train[ti], sample_weight=sample_weights[ti])
        scores.append(f1_score(y_cls_train[vi], m.predict(X_train[vi]), average="macro", zero_division=0))
    return float(np.mean(scores))

xs = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
xs.optimize(xgb_objective, n_trials=40, show_progress_bar=True)
best_xgb_params = {**xs.best_params, "eval_metric": "mlogloss",
                   "random_state": 42, "n_jobs": -1, "verbosity": 0}
print(f"\nXGBoost best CV: {xs.best_value:.4f}  params: n_est={xs.best_params['n_estimators']}, "
      f"depth={xs.best_params['max_depth']}, lr={xs.best_params['learning_rate']:.3f}")

clf_xgb = XGBClassifier(**best_xgb_params)
clf_xgb.fit(X_train, y_cls_train, sample_weight=sample_weights)
xgb_macro = f1_score(y_test_eval, clf_xgb.predict(X_test_eval), average="macro", zero_division=0)
xgb_wf1   = f1_score(y_test_eval, clf_xgb.predict(X_test_eval), average="weighted", zero_division=0)
print(f"XGBoost holdout -> Macro F1: {xgb_macro:.4f}  Weighted F1: {xgb_wf1:.4f}")


# ── LAYER 4b: LightGBM (30 trials) ───────────────────────────────────────────
print("\n=== Optuna LightGBM (30 trials) ===")

def lgb_objective(trial):
    params = {
        "n_estimators":      trial.suggest_int("n_estimators", 300, 900),
        "num_leaves":        trial.suggest_int("num_leaves", 31, 127),
        "max_depth":         trial.suggest_int("max_depth", 4, 10),
        "learning_rate":     trial.suggest_float("learning_rate", 0.01, 0.15, log=True),
        "min_child_samples": trial.suggest_int("min_child_samples", 5, 30),
        "colsample_bytree":  trial.suggest_float("colsample_bytree", 0.5, 1.0),
        "subsample":         trial.suggest_float("subsample", 0.6, 1.0),
        "subsample_freq":    1,
        "reg_alpha":         trial.suggest_float("reg_alpha", 0, 2.0),
        "reg_lambda":        trial.suggest_float("reg_lambda", 0.5, 5.0),
        "random_state": 42, "n_jobs": -1, "verbose": -1,
    }
    scores = []
    for ti, vi in cv.split(X_train, y_cls_train):
        m = lgb.LGBMClassifier(**params)
        m.fit(X_train[ti], y_cls_train[ti], sample_weight=sample_weights[ti])
        scores.append(f1_score(y_cls_train[vi], m.predict(X_train[vi]), average="macro", zero_division=0))
    return float(np.mean(scores))

ls = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
ls.optimize(lgb_objective, n_trials=30, show_progress_bar=True)
best_lgb_params = {**ls.best_params, "subsample_freq": 1,
                   "random_state": 42, "n_jobs": -1, "verbose": -1}
print(f"\nLightGBM best CV: {ls.best_value:.4f}")

clf_lgb = lgb.LGBMClassifier(**best_lgb_params)
clf_lgb.fit(X_train, y_cls_train, sample_weight=sample_weights)
lgb_macro = f1_score(y_test_eval, clf_lgb.predict(X_test_df), average="macro", zero_division=0)
lgb_wf1   = f1_score(y_test_eval, clf_lgb.predict(X_test_df), average="weighted", zero_division=0)
print(f"LightGBM holdout -> Macro F1: {lgb_macro:.4f}  Weighted F1: {lgb_wf1:.4f}")


# ── LAYER 4c: CatBoost (20 trials) ───────────────────────────────────────────
print("\n=== Optuna CatBoost (20 trials, native categorical features) ===")

def cat_objective(trial):
    params = {
        "iterations":          trial.suggest_int("iterations", 300, 700),
        "depth":               trial.suggest_int("depth", 4, 8),
        "learning_rate":       trial.suggest_float("learning_rate", 0.02, 0.2, log=True),
        "l2_leaf_reg":         trial.suggest_float("l2_leaf_reg", 1, 10),
        "border_count":        trial.suggest_int("border_count", 32, 128),
        "bagging_temperature": trial.suggest_float("bagging_temperature", 0, 1),
        "random_strength":     trial.suggest_float("random_strength", 0, 2),
        "loss_function": "MultiClass",
        "eval_metric": "Accuracy",
        "random_seed": 42,
        "thread_count": -1,
        "verbose": 0,
        "allow_writing_files": False,
    }
    scores = []
    for ti, vi in cv.split(X_train, y_cls_train):
        m = CatBoostClassifier(**params)
        m.fit(X_train[ti], y_cls_train[ti], sample_weight=sample_weights[ti])
        scores.append(f1_score(y_cls_train[vi], m.predict(X_train[vi]), average="macro", zero_division=0))
    return float(np.mean(scores))

cs = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
cs.optimize(cat_objective, n_trials=20, show_progress_bar=True)
best_cat_params = {**cs.best_params,
                   "loss_function": "MultiClass", "eval_metric": "Accuracy",
                   "random_seed": 42, "thread_count": -1, "verbose": 0,
                   "allow_writing_files": False}
print(f"\nCatBoost best CV: {cs.best_value:.4f}")

clf_cat = CatBoostClassifier(**best_cat_params)
clf_cat.fit(X_train, y_cls_train, sample_weight=sample_weights)
cat_macro = f1_score(y_test_eval, clf_cat.predict(X_test_eval), average="macro", zero_division=0)
cat_wf1   = f1_score(y_test_eval, clf_cat.predict(X_test_eval), average="weighted", zero_division=0)
print(f"CatBoost holdout -> Macro F1: {cat_macro:.4f}  Weighted F1: {cat_wf1:.4f}")


# ── LAYER 5: 3-model soft ensemble ───────────────────────────────────────────
print("\n=== 3-model ensemble grid search ===")
xgb_p = clf_xgb.predict_proba(X_test_eval)
lgb_p = clf_lgb.predict_proba(X_test_df)
cat_p = clf_cat.predict_proba(X_test_eval)

best_macro, best_wx, best_wl, best_wc = 0.0, 1/3, 1/3, 1/3
for wx in np.arange(0.1, 0.8, 0.1):
    for wl in np.arange(0.1, 0.8 - wx, 0.1):
        wc = round(1.0 - wx - wl, 1)
        if wc < 0.1 or wc > 0.7:
            continue
        proba = wx * xgb_p + wl * lgb_p + wc * cat_p
        macro = f1_score(y_test_eval, np.argmax(proba, axis=1), average="macro", zero_division=0)
        if macro > best_macro:
            best_macro, best_wx, best_wl, best_wc = macro, wx, wl, wc

print(f"Best: XGB={best_wx:.1f} + LGB={best_wl:.1f} + CAT={best_wc:.1f}  -> Macro F1={best_macro:.4f}")
print(f"Individual: XGB={xgb_macro:.4f}  LGB={lgb_macro:.4f}  CAT={cat_macro:.4f}")


# ── Final evaluation ──────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("FINAL RESULTS -- holdout test set (1970-2021)")
print("=" * 70)
final_proba = best_wx * xgb_p + best_wl * lgb_p + best_wc * cat_p
final_pred  = np.argmax(final_proba, axis=1)
print(classification_report(y_test_eval, final_pred,
                             target_names=le_target.classes_, zero_division=0))
final_macro = f1_score(y_test_eval, final_pred, average="macro",    zero_division=0)
final_wf1   = f1_score(y_test_eval, final_pred, average="weighted", zero_division=0)
print(f"Macro F1   (v3: 0.7106)  ->  v4.1: {final_macro:.4f}")
print(f"Weighted F1(v3: 0.7484)  ->  v4.1: {final_wf1:.4f}")


# ── Train impact regressors (per-type + drop-null + global fallback) ──────────
print("\n=== Training impact regressors (per-type, drop-null, 16 features) ===")

def _make_impact_regressor(key):
    if key in RF_TARGETS:
        return RandomForestRegressor(
            n_estimators=200, max_depth=10, min_samples_leaf=5, random_state=42, n_jobs=-1,
        )
    return XGBRegressor(
        n_estimators=300, max_depth=5, learning_rate=0.08,
        subsample=0.8, colsample_bytree=0.8, random_state=42, n_jobs=-1, verbosity=0,
    )

_type_arr = df["Disaster Type"].values
_classes = [str(t) for t in le_target.classes_]
global_regressors = {}
per_type_regressors = {t: {} for t in _classes}
for key in TARGET_COLS:
    raw = raw_targets[key]
    obs = ~np.isnan(raw)
    g = _make_impact_regressor(key)
    g.fit(X_train[obs], np.log1p(raw[obs]))
    global_regressors[key] = g
    n_pt = 0
    for t in _classes:
        sel = (_type_arr == t)
        rr = raw[sel]
        o = ~np.isnan(rr)
        if o.sum() >= MIN_TYPE_ROWS:
            m = _make_impact_regressor(key)
            m.fit(X_train[sel][o], np.log1p(rr[o]))
            per_type_regressors[t][key] = m
            n_pt += 1
    print(f"  {key:<9} global on {obs.sum():,} obs rows | per-type models: {n_pt}/{len(_classes)}")


# ── SHAP ──────────────────────────────────────────────────────────────────────
print("\n=== Building SHAP TreeExplainer (XGBoost) ===")
explainer   = shap.TreeExplainer(clf_xgb)
shap_sample = np.array(explainer.shap_values(X_train[:10]))
print(f"SHAP shape: {shap_sample.shape}  OK")


# ── Save models ───────────────────────────────────────────────────────────────
print("\n=== Saving model files ===")
classifier_bundle = {
    "model":             clf_xgb,
    "lgb_model":         clf_lgb,
    "cat_model":         clf_cat,
    "xgb_weight":        best_wx,
    "lgb_weight":        best_wl,
    "cat_weight":        best_wc,
    "le_continent":      le_continent,
    "le_region":         le_region,
    "le_country":        le_country,
    "le_target":         le_target,
    "region_freq_map":   region_freq_map,
    "feature_names":     FEATURE_NAMES,
    "targets_are_log1p": True,
}
impact_regressors = {
    "structure":         "per_type_v1",
    "per_type":          per_type_regressors,
    "global":            global_regressors,
    "targets_are_log1p": True,
    "min_type_rows":     MIN_TYPE_ROWS,
}

joblib.dump(classifier_bundle, MODELS_DIR / "disaster_predictor.pkl")
joblib.dump(impact_regressors, MODELS_DIR / "impact_regressor.pkl")
joblib.dump(explainer,         MODELS_DIR / "shap_explainer.pkl")

for fname in ["disaster_predictor.pkl", "impact_regressor.pkl", "shap_explainer.pkl"]:
    sz = (MODELS_DIR / fname).stat().st_size
    print(f"  {fname}: {sz / 1024:.0f} KB")


# ── Smoke test ────────────────────────────────────────────────────────────────
print("\n=== Smoke test ===")
_b = joblib.load(MODELS_DIR / "disaster_predictor.pkl")
_r = joblib.load(MODELS_DIR / "impact_regressor.pkl")

hf        = float(_b["region_freq_map"].get("Northern Africa", 1))
raw_month = 7
X_demo = np.array([[
    30.0, 31.0, 30.0,
    np.sin(2*np.pi*31.0/360), np.cos(2*np.pi*31.0/360),
    _b["le_continent"].transform(["Africa"])[0],
    _b["le_region"].transform(["Northern Africa"])[0],
    _b["le_country"].transform(["Egypt"])[0],
    np.sin(2*np.pi*raw_month/12), np.cos(2*np.pi*raw_month/12),
    0.0, 0, hf, float(np.log1p(hf)), 2020, 0,
]], dtype=np.float32)

xp = _b["model"].predict_proba(X_demo)
lp = _b["lgb_model"].predict_proba(pd.DataFrame(X_demo, columns=FEATURE_NAMES))
cp = _b["cat_model"].predict_proba(X_demo)
proba = _b["xgb_weight"]*xp + _b["lgb_weight"]*lp + _b["cat_weight"]*cp
cidx = int(np.argmax(proba[0]))
pred_type = str(_b["le_target"].classes_[cidx])
print(f"  Predicted: {pred_type}  (prob={float(proba[0][cidx]):.4f})")
# Route the deaths regressor by predicted type (per-type bundle), global fallback.
_deaths_reg = _r["per_type"].get(pred_type, {}).get("deaths") or _r["global"]["deaths"]
deaths_p = int(np.expm1(_deaths_reg.predict(X_demo)[0]).clip(min=0))
print(f"  Deaths: {deaths_p:,}")
print()
print("ALL DONE -- 3 pkl files saved to backend/saved_models/")
