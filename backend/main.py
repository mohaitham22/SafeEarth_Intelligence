import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from config import get_settings
from ml import emdat_lookup
from ml import predictor as ml_predictor
from rag import recommender as rag_recommender
from routers import auth, predictions, regions, alerts, subscriptions, recommendations, premium, admin
from services.premium_service import run_expiry_loop

logger = logging.getLogger("safeearth")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting SafeEarth API...")

    # ── Phase 2: Load all 7 precomputed EM-DAT JSON files ──────────────────
    settings = get_settings()
    try:
        emdat_lookup.load_all(settings.data_generated_dir)
        n_types     = len(emdat_lookup.EMDAT_STATS.get("global", {}))
        n_countries = len(emdat_lookup.EMDAT_STATS.get("by_country", {}))
        n_regions   = len(emdat_lookup.EMDAT_STATS.get("by_region", {}))
        logger.info(
            "Loaded EM-DAT lookup: %d disaster types, %d countries, %d regions",
            n_types, n_countries, n_regions,
        )
    except FileNotFoundError as exc:
        logger.critical("STARTUP FAILURE — EM-DAT data files missing: %s", exc)
        logger.critical("Fix: run  python scripts/generate_emdat_stats.py  then restart.")
        raise

    # ── Phase 3: Load ML models ───────────────────────────────────────────────
    try:
        ml_predictor.load_models(
            settings.saved_models_dir,
            huggingface_repo_id=settings.huggingface_repo_id,
            huggingface_token=settings.huggingface_token,
        )
        app.state.models_loaded = True
        logger.info("ML models loaded (classifier + 4 regressors + SHAP explainer)")
    except FileNotFoundError as exc:
        logger.critical("STARTUP FAILURE — ML model files missing: %s", exc)
        logger.critical("Fix: run notebooks/02_model_training.ipynb to generate .pkl files.")
        raise

    # ── Phase 4: Load RAG (ChromaDB + sentence-transformers + optional Groq) ──
    # Degrade-on-failure: the service layer falls back to the DB recommendations
    # table when the recommender raises, so a missing ChromaDB shouldn't take
    # down predictions or auth. Surface the degradation via /health.rag_loaded.
    try:
        rag_recommender.load_rag()
        app.state.rag_loaded = True
        logger.info("RAG pipeline loaded (ChromaDB + embedder + Groq client)")
    except FileNotFoundError as exc:
        app.state.rag_loaded = False
        logger.critical("RAG ChromaDB store missing — DEGRADING to DB-fallback only: %s", exc)
        logger.critical("Fix: run  py -3.12 backend/rag/ingest.py  to (re)build ChromaDB.")
    except Exception:  # noqa: BLE001
        app.state.rag_loaded = False
        logger.critical("Unexpected RAG load failure — DEGRADING to DB-fallback only", exc_info=True)

    # ── Phase 7: Start premium expiry background task ────────────────────────
    app.state.expiry_task = asyncio.create_task(run_expiry_loop())
    logger.info("Premium expiry checker started (24h interval)")

    yield

    if hasattr(app.state, "expiry_task"):
        app.state.expiry_task.cancel()
        try:
            await app.state.expiry_task
        except asyncio.CancelledError:
            pass

    app.state.rag_loaded = False
    app.state.models_loaded = False
    logger.info("Shutting down...")


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    lifespan=lifespan,
    title="SafeEarth Intelligence API",
    version="0.1.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin.health_router, prefix="/api/v1")   # → /api/v1/health
app.include_router(auth.router, prefix="/api/v1")           # → /api/v1/auth/...
app.include_router(predictions.router, prefix="/api/v1")    # → /api/v1/predictions/...
app.include_router(regions.router, prefix="/api/v1")        # → /api/v1/regions/...
app.include_router(alerts.router, prefix="/api/v1")         # → /api/v1/alerts/...
app.include_router(subscriptions.router, prefix="/api/v1")  # → /api/v1/subscriptions/...
app.include_router(recommendations.router, prefix="/api/v1") # → /api/v1/recommendations/...
app.include_router(premium.router, prefix="/api/v1")        # → /api/v1/premium/...
app.include_router(admin.router, prefix="/api/v1")          # → /api/v1/admin/...


@app.get("/")
async def root():
    return {"name": "SafeEarth Intelligence", "version": "0.1.0"}
