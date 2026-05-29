# SKILL: ML Inference Pattern

Read this file completely before writing any code that touches ML models,
SHAP explainability, or model loading.
One wrong pattern here causes 2–5 second latency on every request.

---

## The Cardinal Rule

**Models load ONCE at FastAPI startup.**
**Models are never loaded inside a route function.**
**Models are never loaded inside a service function.**
**Models are stored as module-level variables in backend/ml/.**

If you see `joblib.load()` or `shap.TreeExplainer()` inside any function
that runs per-request — stop and fix it immediately.

---

## The 3 Model Files

```
backend/saved_models/
├── disaster_predictor.pkl   ← XGBClassifier — disaster type classification
├── impact_regressor.pkl     ← dict of 4 regressors: deaths, injuries, affected, damage
└── shap_explainer.pkl       ← shap.TreeExplainer — cached for XGBClassifier
```

Downloaded from Hugging Face at startup if not present locally.

---

## Startup Loading — FastAPI Lifespan Pattern

All models are loaded in the lifespan context manager in main.py.
This runs once when FastAPI starts, before any request is accepted.

```python
# backend/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from ml import predictor
from ml import emdat_lookup

@asynccontextmanager
async def lifespan(app: FastAPI):
    # — Startup —
    print("Loading ML models...")
    predictor.load_models()       # loads all 3 .pkl files
    emdat_lookup.load_data()      # loads all 7 JSON files into memory
    print("✓ All models loaded")
    app.state.models_loaded = True

    yield  # ← application runs here

    # — Shutdown —
    app.state.models_loaded = False

app = FastAPI(lifespan=lifespan)
```

---

## predictor.py — XGBoost Inference

```python
# backend/ml/predictor.py
import joblib
import shap
import numpy as np
from pathlib import Path
import os

# — Module-level variables — loaded ONCE at startup —
_classifier     = None   # XGBClassifier
_regressors     = None   # dict: {"deaths": model, "injuries": model, "affected": model, "damage": model}
_shap_explainer = None   # shap.TreeExplainer

MODELS_DIR = Path(os.getenv("MODELS_DIR", "saved_models"))

def load_models():
    """Called ONCE at FastAPI startup. Never call from a route or service."""
    global _classifier, _regressors, _shap_explainer

    _ensure_models_downloaded()

    _classifier     = joblib.load(MODELS_DIR / "disaster_predictor.pkl")
    _regressors     = joblib.load(MODELS_DIR / "impact_regressor.pkl")
    _shap_explainer = joblib.load(MODELS_DIR / "shap_explainer.pkl")

    print(f"  ✓ Classifier: {type(_classifier).__name__}")
    print(f"  ✓ Regressors: {list(_regressors.keys())}")
    print(f"  ✓ SHAP explainer loaded")

def _ensure_models_downloaded():
    """Download model files from Hugging Face Hub if not already present."""
    from huggingface_hub import hf_hub_download
    repo_id = os.getenv("HUGGINGFACE_REPO_ID")
    token   = os.getenv("HUGGINGFACE_TOKEN")

    for filename in ["disaster_predictor.pkl", "impact_regressor.pkl", "shap_explainer.pkl"]:
        dest = MODELS_DIR / filename
        if not dest.exists():
            print(f"  Downloading {filename} from Hugging Face...")
            hf_hub_download(repo_id=repo_id, filename=filename,
                            local_dir=MODELS_DIR, token=token)

# — Inference functions — called by services, never by routes —

def run_prediction(
    latitude: float,
    longitude: float,
    continent: str,
    region: str,
    month: int,
    historical_freq: int,
    decade: int,
    dis_mag_value: float | None = None,
    day_offset: int = 0,          # 0 for single prediction, 0–29 for 30-day forecast
    derived_season: str | None = None,
) -> dict:
    """
    Run disaster type classification + impact regression + SHAP.
    Returns a complete prediction dict ready for the service layer.
    Never call this from a router.
    """
    if _classifier is None:
        raise RuntimeError("Models not loaded. Did load_models() run at startup?")

    has_magnitude = 1 if dis_mag_value is not None else 0
    mag_value     = dis_mag_value if dis_mag_value is not None else 0.0

    features = np.array([[
        latitude, longitude,
        _encode_continent(continent),
        _encode_region(region),
        month,
        mag_value,
        has_magnitude,
        historical_freq,
        decade,
        day_offset,
    ]])

    # Classification
    proba         = _classifier.predict_proba(features)[0]
    class_idx     = int(np.argmax(proba))
    disaster_type = _classifier.classes_[class_idx]
    probability   = float(proba[class_idx])

    severity = _probability_to_severity(probability)

    # Impact regression
    impact = {
        "estimated_deaths":    max(0, int(_regressors["deaths"].predict(features)[0])),
        "estimated_injuries":  max(0, int(_regressors["injuries"].predict(features)[0])),
        "estimated_affected":  max(0, int(_regressors["affected"].predict(features)[0])),
        "estimated_damage_usd": max(0, int(_regressors["damage"].predict(features)[0])),
    }

    # SHAP — uses cached explainer, never re-instantiated
    shap_values = _shap_explainer.shap_values(features)
    shap_result = _extract_top_shap(shap_values, class_idx)

    return {
        "disaster_type":     disaster_type,
        "probability_score": probability,
        "severity_level":    severity,
        **impact,
        "shap_explanation":  shap_result,
    }

def _probability_to_severity(p: float) -> str:
    # Thresholds from CLAUDE.md — do not change
    if p <= 0.30: return "Low"
    if p <= 0.55: return "Medium"
    if p <= 0.75: return "High"
    return "Critical"

def _extract_top_shap(shap_values, class_idx: int) -> list[dict]:
    """Extract top 3 SHAP features as percentage contributions."""
    FEATURE_NAMES = [
        "latitude", "longitude", "continent", "region", "month",
        "dis_mag_value", "has_magnitude", "historical_frequency", "decade", "day_offset"
    ]
    vals  = np.abs(shap_values[0, :, class_idx]) if shap_values.ndim == 3 else np.abs(shap_values[0])
    total = vals.sum()
    if total == 0:
        return []
    ranked = sorted(zip(FEATURE_NAMES, vals), key=lambda x: x[1], reverse=True)[:3]
    return [{"feature": name, "contribution_pct": round(float(val / total * 100), 1)}
            for name, val in ranked]
```

---

## 30-Day Forecast Loop (in predictor_service.py)

```python
# backend/services/predictor_service.py
from ml.predictor import run_prediction

async def create_forecast_30d(latitude, longitude, continent, region, db, user_id):
    results = []
    base_month = datetime.utcnow().month
    decade     = (datetime.utcnow().year // 10) * 10

    for day_offset in range(30):
        forecast_month = ((base_month - 1 + (day_offset // 30)) % 12) + 1
        result = run_prediction(
            latitude=latitude,
            longitude=longitude,
            continent=continent,
            region=region,
            month=forecast_month,
            historical_freq=historical_freq,
            decade=decade,
            day_offset=day_offset,
        )
        result["forecast_day_offset"] = day_offset
        result["date"] = (datetime.utcnow() + timedelta(days=day_offset)).date().isoformat()
        results.append(result)

    return results
```

---

## Health Check Endpoint

```python
# backend/routers/admin.py
from fastapi import APIRouter, Request
from datetime import datetime, timezone

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/health")
async def health_check(request: Request):
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "models_loaded": getattr(request.app.state, "models_loaded", False),
    }
```

If `models_loaded` is False in the /health response:
1. Check startup logs for errors during lifespan
2. Check MODELS_DIR env var — must be an absolute path on Render
3. Check HUGGINGFACE_TOKEN and HUGGINGFACE_REPO_ID are set
4. Check that .pkl files exist in the HF repo and are not corrupted

---

## Critical Rules Summary

```
✓ DO                                      ✗ NEVER DO
────────────────────────────────────────   ────────────────────────────────────────
Load models in lifespan at startup         Load models inside route functions
Store models as module-level vars          Load models inside service functions
Use _shap_explainer cached at startup      Instantiate shap.TreeExplainer per-request
Call run_prediction() from service only    Call run_prediction() from a router
Strip disaster type strings before lookup  Compare disaster types without .strip()
Raise RuntimeError if model is None        Assume model is always loaded
```

---

## Disaster Type Stripping Rule

Always strip whitespace before any comparison or lookup involving disaster type strings.
The source CSV has `'Extreme temperature '` with a trailing space.

```python
# ALWAYS do this before any disaster_type comparison or lookup
disaster_type = disaster_type.strip()
```

---

## Checklist Before Committing Any ML Code

- [ ] Models loaded in lifespan context manager in main.py — not anywhere else
- [ ] Module-level `_classifier`, `_regressors`, `_shap_explainer` variables used
- [ ] `run_prediction()` called from a service, never from a router
- [ ] SHAP explainer loaded from .pkl at startup — never `shap.TreeExplainer(model)` per-request
- [ ] `disaster_type.strip()` called before any lookup or comparison
- [ ] Severity thresholds match CLAUDE.md exactly (0.30 / 0.55 / 0.75 / 1.00)
- [ ] `day_offset` passed for 30-day forecast rows, defaults to 0 for single predictions
- [ ] /health endpoint returns `models_loaded: true` after startup
- [ ] HuggingFace download only runs if file does not already exist locally
