# SKILL: Add a New API Endpoint

Read this file completely before creating any FastAPI route.
This is the binding pattern for every endpoint in SafeEarth Intelligence.
Do not deviate from this structure.

---

## The 5-File Rule

Every new endpoint touches exactly 5 files in this order:
1. `backend/schemas/{feature}.py` → Pydantic request + response models
2. `backend/models/{table}.py` → SQLAlchemy ORM model (if new table needed)
3. `backend/services/{feature}_service.py` → all business logic
4. `backend/routers/{feature}.py` → route definition only, calls service
5. `backend/main.py` → register the router (one line only)

Never put logic in the router. Never put DB calls in the router.
The router's only job is: validate input → call service → return output.

---

## Step 1 — Schema (backend/schemas/{feature}.py)

Always define both a Request schema and a Response schema.
Never use raw dicts as request bodies or responses.

```python
# backend/schemas/predictions.py
from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime

class PredictionRequest(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    disaster_type: Optional[str] = None

class SHAPFeature(BaseModel):
    feature: str
    contribution_pct: float

class PredictionResponse(BaseModel):
    id: UUID
    disaster_type: str
    probability_score: float
    severity_level: str
    risk_score: float
    estimated_deaths: int
    estimated_injuries: int
    estimated_affected: int
    estimated_damage_usd: int
    uninsured_loss_usd: int
    shap_explanation: list[SHAPFeature]
    secondary_disaster_warning: Optional[str]
    seasonal_peak_months: list[int]
    data_quality: str  # 'full' or 'limited'
    recommendations: list[dict]

    class Config:
        from_attributes = True
```

---

## Step 2 — Service (backend/services/{feature}_service.py)

All logic lives here. Never in the router.
Always use async functions. Always accept db: AsyncSession as parameter.

```python
# backend/services/prediction_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.prediction import Prediction
from schemas.predictions import PredictionRequest, PredictionResponse
from ml.predictor import run_prediction
from ml.emdat_lookup import resolve_impact_stats
import uuid

class PredictionService:

    @staticmethod
    async def create_prediction(
        request: PredictionRequest,
        db: AsyncSession,
        user_id: uuid.UUID | None = None
    ) -> PredictionResponse:

        result = run_prediction(request.latitude, request.longitude)
        impact = resolve_impact_stats(result["disaster_type"])

        prediction = Prediction(
            user_id=user_id,
            latitude=request.latitude,
            longitude=request.longitude,
            disaster_type=result["disaster_type"],
            probability_score=result["probability_score"],
            severity_level=result["severity_level"],
            risk_score=result["risk_score"],
            estimated_deaths=impact["median_deaths"],
            # ... all other fields
        )
        db.add(prediction)
        await db.commit()
        await db.refresh(prediction)

        return PredictionResponse.model_validate(prediction)
```

---

## Step 3 — Router (backend/routers/{feature}.py)

The router ONLY handles:
- HTTP method + path
- Auth dependency
- Rate limit decorator
- Calling the service
- Returning the response

Nothing else. No if/else logic. No DB queries. No ML calls.

```python
# backend/routers/predictions.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from routers.auth import get_current_user, get_optional_user
from schemas.predictions import PredictionRequest, PredictionResponse
from services.prediction_service import PredictionService
from models.user import User
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

router = APIRouter(prefix="/predictions", tags=["predictions"])
limiter = Limiter(key_func=get_remote_address)

@router.post("/predict", response_model=PredictionResponse)
@limiter.limit("10/minute")
async def predict_disaster(
    request: Request,
    body: PredictionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
):
    return await PredictionService.create_prediction(
        request=body,
        db=db,
        user_id=current_user.id if current_user else None,
    )

@router.get("/history", response_model=list[PredictionResponse])
async def get_prediction_history(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await PredictionService.get_user_history(db=db, user_id=current_user.id)
```

---

## Step 4 — Register in main.py

Add exactly ONE line in the routers section of main.py.
Never add any logic to main.py — just router registration.

```python
# backend/main.py — routers section only
from routers import auth, predictions, regions, alerts, subscriptions, recommendations, premium, admin

app.include_router(auth.router, prefix="/api/v1")
app.include_router(predictions.router, prefix="/api/v1")
app.include_router(regions.router, prefix="/api/v1")
app.include_router(alerts.router, prefix="/api/v1")
app.include_router(subscriptions.router, prefix="/api/v1")
app.include_router(recommendations.router, prefix="/api/v1")
app.include_router(premium.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
```

---

## Step 5 — Auth Dependencies

Use exactly these dependency functions. Never roll your own JWT checking inside a route.

```python
# Requires valid JWT → returns User object. Raises 401 if missing/invalid.
async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User

# Returns User if token present and valid, None if no token (guest). Never raises.
async def get_optional_user(token: str = Depends(oauth2_scheme_optional), db: AsyncSession = Depends(get_db)) -> User | None

# Requires role='admin'. Raises 403 if user is not admin.
async def require_admin(current_user: User = Depends(get_current_user)) -> User

# Requires role='premium' or 'admin'. Raises 403 otherwise.
async def require_premium(current_user: User = Depends(get_current_user)) -> User
```

Usage:
```python
async def my_route(current_user = Depends(get_optional_user))   # guest allowed
async def my_route(current_user = Depends(get_current_user))    # any logged-in user
async def my_route(current_user = Depends(require_premium))     # premium only
async def my_route(current_user = Depends(require_admin))       # admin only
```

---

## Step 6 — Error Handling

Always raise HTTPException. Never return error dicts manually.

```python
# CORRECT
raise HTTPException(status_code=404, detail="Prediction not found")
raise HTTPException(status_code=403, detail="Premium subscription required")
raise HTTPException(status_code=422, detail="Invalid disaster type")

# WRONG — never do this
return {"error": "not found"}
```

---

## Rate Limiting Rules

| Endpoint | Guest limit | Authenticated limit |
|---|---|---|
| POST /predictions/predict | 10/minute | 60/minute |
| POST /predictions/forecast-30d | N/A | 5/hour |
| GET /regions/* | No limit | No limit |
| Auth endpoints | 5/minute | 5/minute |
| Admin endpoints | N/A | No limit |

---

## Checklist Before Committing a New Endpoint

- [ ] Schema defined in /schemas/ (both Request and Response)
- [ ] Logic is in /services/ not in the router
- [ ] Router function body is max 5 lines (validate → call service → return)
- [ ] Correct auth dependency used (get_optional_user / get_current_user / require_admin / require_premium)
- [ ] Rate limit decorator applied where required
- [ ] HTTPException used for all error cases (never raw dicts)
- [ ] Router registered in main.py
- [ ] AsyncSession used (never sync Session)
