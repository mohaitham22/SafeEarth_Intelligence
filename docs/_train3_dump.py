"""
_train3_dump.py — fast reproduction of notebook 07's pipeline (Optuna OFF) to dump the
confusion matrix + SHAP feature importance as JSON for the train3 ML deck.

The HEADLINE scoreboard / regression numbers in the deck come from the tuned executed
notebook. This script only supplies the two qualitative visuals (class-confusion structure
and feature importance), which are stable w.r.t. tuning. Run: py -3.12 docs/_train3_dump.py
"""
import json, warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
from catboost import CatBoostClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import confusion_matrix, f1_score
import shap

RS = 42
DATA = next(p for p in [Path("data/train 3/disasters_8types_enriched.csv"),
                        Path("../data/train 3/disasters_8types_enriched.csv")] if p.exists())
df = pd.read_csv(DATA); df["disaster_type"] = df["disaster_type"].astype(str).str.strip()
df["cpi"] = pd.to_numeric(df["cpi"], errors="coerce"); df["cpi"] = df["cpi"].fillna(df["cpi"].median())

NUM = ["latitude","longitude","abs_latitude","lon_sin","lon_cos","month_sin","month_cos","year",
       "decade","duration_days","historical_freq","log_hist_freq","has_magnitude","dis_mag_value",
       "has_exact_coords","n_associated_disasters","cpi"]
ENC = ["continent_enc","region_enc","country_enc"]
FEATS = NUM + ENC

tr, te = train_test_split(df, test_size=0.2, random_state=RS, stratify=df["disaster_type"])
tr, te = tr.reset_index(drop=True), te.reset_index(drop=True)
lec, ler, leco, let = (LabelEncoder() for _ in range(4))
lec.fit(tr["continent"]); ler.fit(tr["region"]); leco.fit(tr["country"]); let.fit(tr["disaster_type"])
def enc(le, vals):
    known = set(le.classes_)
    return np.array([le.transform([v])[0] if v in known else 0 for v in vals], dtype=np.int32)
def add(f):
    f = f.copy(); f["continent_enc"]=enc(lec,f["continent"]); f["region_enc"]=enc(ler,f["region"])
    f["country_enc"]=enc(leco,f["country"]); return f
tr, te = add(tr), add(te)
Xtr = tr[FEATS].values.astype(np.float32); Xte = te[FEATS].values.astype(np.float32)
ytr = let.transform(tr["disaster_type"]); yte = let.transform(te["disaster_type"])
CLASSES = list(let.classes_); L = np.arange(len(CLASSES))

counts = tr["disaster_type"].value_counts()
cw = (np.sqrt(counts.max()/counts)).clip(1.0,4.0).round(2).to_dict()
sw = np.array([cw[c] for c in tr["disaster_type"]], dtype=np.float32)

xgb = XGBClassifier(n_estimators=600,max_depth=7,learning_rate=0.05,min_child_weight=3,gamma=0.5,
        subsample=0.8,colsample_bytree=0.8,reg_alpha=0.5,reg_lambda=2.0,eval_metric="mlogloss",
        random_state=RS,n_jobs=-1,verbosity=0).fit(Xtr,ytr,sample_weight=sw)
lgb = LGBMClassifier(n_estimators=600,num_leaves=63,max_depth=8,learning_rate=0.05,min_child_samples=20,
        colsample_bytree=0.8,subsample=0.8,subsample_freq=1,reg_alpha=0.5,reg_lambda=2.0,
        random_state=RS,n_jobs=-1,verbose=-1).fit(pd.DataFrame(Xtr,columns=FEATS),ytr,sample_weight=sw)
cat = CatBoostClassifier(iterations=500,depth=6,learning_rate=0.05,l2_leaf_reg=3.0,
        loss_function="MultiClass",random_seed=RS,thread_count=-1,verbose=0,
        allow_writing_files=False).fit(Xtr,ytr,sample_weight=sw)

# ensemble weights from the tuned run: XGB=0.3 LGB=0.1 CAT=0.6
pe = 0.3*xgb.predict_proba(Xte)+0.1*lgb.predict_proba(pd.DataFrame(Xte,columns=FEATS))+0.6*cat.predict_proba(Xte)
yp = np.argmax(pe,axis=1)
cm = confusion_matrix(yte, yp, labels=L).tolist()

expl = shap.TreeExplainer(xgb)
n = min(800, len(Xte)); sv = np.array(expl.shap_values(Xte[:n]))
imp = np.abs(sv).mean(axis=(0,1)) if (sv.ndim==3 and sv.shape[0]==len(CLASSES)) else \
      (np.abs(sv).mean(axis=(0,2)) if sv.ndim==3 else np.abs(sv).mean(axis=0))
imp = (imp/imp.sum()*100.0)
shap_imp = sorted(zip(FEATS, imp.tolist()), key=lambda x:-x[1])

out = {"classes": CLASSES, "confusion": cm,
       "macro_f1_reproduction": round(float(f1_score(yte,yp,average="macro",zero_division=0)),4),
       "shap_importance_pct": shap_imp}
Path("docs/_train3_extra.json").write_text(json.dumps(out, indent=2))
print("macro-F1 (curated-default reproduction):", out["macro_f1_reproduction"])
print("top SHAP:", [(f, round(v,1)) for f,v in shap_imp[:6]])
print("wrote docs/_train3_extra.json")
