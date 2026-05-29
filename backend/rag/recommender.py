"""
backend/rag/recommender.py — Runtime RAG pipeline.

Module-level singletons (embedder + ChromaDB collection + Groq client) are
populated by load_rag() in the FastAPI lifespan in main.py.

Cardinal rules — any violation breaks the latency budget or correctness contract:
  - load_rag()             NEVER called from a route or service function
  - SentenceTransformer    NEVER instantiated per-request (cached at startup)
  - PersistentClient       NEVER instantiated per-request (cached at startup)
  - Groq client            NEVER instantiated per-request (cached at startup)
  - get_recommendations()  NEVER called from a router (service layer only)
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Optional

from config import get_settings
from rag.constants import CHROMA_PATH, COLLECTION_NAME, EMBED_MODEL
from schemas.recommendation import RecommendationItem

if TYPE_CHECKING:
    import chromadb
    from sentence_transformers import SentenceTransformer

# ── Tunable constants ─────────────────────────────────────────────────────────

RAG_TOP_K            = 5                       # ChromaDB top-k retrieved chunks
RECOMMENDATION_COUNT = 6                       # Per CLAUDE.md Feature 5 contract
GROQ_MODEL           = "llama-3.1-8b-instant"  # Per CLAUDE.md RAG Pipeline spec
GROQ_TEMPERATURE     = 0.3                     # Per CLAUDE.md RAG Pipeline spec

_CATEGORY_ORDER  = ["evacuation", "kit", "shelter", "medical", "contact"]
_CATEGORY_RANK   = {c: i for i, c in enumerate(_CATEGORY_ORDER)}
_VALID_CATEGORIES = set(_CATEGORY_ORDER)


# ── Module-level singletons — None until load_rag() runs at startup ───────────
# Types use Any to avoid importing heavy libraries (torch/chromadb) at module load.

_embedder:      Any = None   # SentenceTransformer | None
_chroma_client: Any = None   # chromadb.PersistentClient | None
_collection:    Any = None   # chromadb.Collection | None
_groq_client:   Any = None   # groq.Groq | None


# ── Exceptions ────────────────────────────────────────────────────────────────

class GroqUnavailableError(Exception):
    """Raised when Groq cannot deliver a valid 6-item JSON response.

    The service layer catches this and falls back to the `recommendations` DB
    table (Phase 4 Step 5 in CLAUDE.md). Reasons include: missing/invalid
    GROQ_API_KEY, network error, rate-limit, malformed JSON, wrong item count,
    invalid category value, or any per-item Pydantic validation failure.
    """


# ── Startup loader ────────────────────────────────────────────────────────────

def load_rag() -> None:
    """Initialise embedder + ChromaDB collection + Groq client.

    Called ONCE in the FastAPI lifespan context manager in main.py.
    Never call from a route or service function.

    Raises:
        FileNotFoundError: if the ChromaDB store hasn't been built yet.
    """
    global _embedder, _chroma_client, _collection, _groq_client

    if not CHROMA_PATH.exists():
        raise FileNotFoundError(
            f"ChromaDB store missing: {CHROMA_PATH}\n"
            f"Run: py -3.12 backend/rag/ingest.py from the project root."
        )

    # Lazy imports — only reach here if ChromaDB store exists.
    # Keeps torch (~500 MB) and chromadb off the import path on Render free tier
    # where the store is absent and load_rag() exits via FileNotFoundError above.
    import chromadb as _chromadb  # noqa: PLC0415
    from sentence_transformers import SentenceTransformer  # noqa: PLC0415

    _embedder      = SentenceTransformer(EMBED_MODEL)
    _chroma_client = _chromadb.PersistentClient(path=str(CHROMA_PATH))
    _collection    = _chroma_client.get_collection(COLLECTION_NAME)

    settings = get_settings()
    if settings.groq_api_key:
        # Local import — keeps `groq` off the import path for tests that don't need it
        from groq import Groq
        _groq_client = Groq(api_key=settings.groq_api_key)
        groq_status = "ready"
    else:
        _groq_client = None
        groq_status  = "DISABLED (GROQ_API_KEY empty — fallback to DB recommendations)"

    print(f"  Embedder     : {EMBED_MODEL}")
    print(f"  ChromaDB     : collection={COLLECTION_NAME} chunks={_collection.count()}")
    print(f"  Groq         : {groq_status}")


# ── Public API ────────────────────────────────────────────────────────────────

def get_recommendations(
    disaster_type: str,
    severity: str,
    region_name: str,
) -> list[RecommendationItem]:
    """Run the runtime RAG pipeline and return exactly 6 recommendations.

    Query string is built EXACTLY per CLAUDE.md RAG Flow:
        "{severity} {disaster_type} emergency safety recommendations {region_name}"

    Returns:
        Exactly 6 RecommendationItem objects, sorted:
        evacuation -> kit -> shelter -> medical -> contact.

    Raises:
        RuntimeError: if load_rag() was not called at startup.
        GroqUnavailableError: any Groq failure or malformed response — the
            service layer catches this and falls back to the DB table.
    """
    if _collection is None or _embedder is None:
        raise RuntimeError(
            "RAG not loaded — load_rag() must run in the FastAPI lifespan at startup."
        )
    if _groq_client is None:
        raise GroqUnavailableError("Groq client not initialised (GROQ_API_KEY missing)")

    query = f"{severity} {disaster_type} emergency safety recommendations {region_name}"

    q_emb   = _embedder.encode([query], convert_to_numpy=True).tolist()
    results = _collection.query(
        query_embeddings=q_emb,
        n_results=RAG_TOP_K,
        include=["documents", "metadatas"],
    )
    chunks: list[str] = results.get("documents", [[]])[0]
    if not chunks:
        raise GroqUnavailableError("ChromaDB returned no chunks for query")

    user_prompt = _build_user_prompt(disaster_type, severity, region_name, chunks)

    try:
        completion = _groq_client.chat.completions.create(
            model=GROQ_MODEL,
            temperature=GROQ_TEMPERATURE,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_prompt},
            ],
        )
    except Exception as exc:
        raise GroqUnavailableError(f"Groq API call failed: {exc}") from exc

    raw = completion.choices[0].message.content or ""
    items = _parse_and_validate(raw)
    return _sort_by_category(items)


# ── Prompts ───────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a disaster safety expert assistant. Generate EXACTLY 6 calibrated, "
    "actionable safety recommendations based on the provided official safety "
    "guidelines context. Respond with a JSON object containing a 'recommendations' "
    "array of exactly 6 items. Each item MUST have these three fields: "
    "'category' (one of: evacuation, kit, shelter, medical, contact), "
    "'title' (short imperative, max 60 characters), "
    "'body' (1-2 sentence actionable instruction, max 280 characters). "
    "Cover all five categories across the 6 items. Base every recommendation strictly "
    "on the provided context — do not invent procedures."
)


def _build_user_prompt(
    disaster_type: str,
    severity: str,
    region_name: str,
    chunks: list[str],
) -> str:
    context = "\n\n---\n\n".join(chunks)
    return (
        f"Disaster type: {disaster_type}\n"
        f"Severity: {severity}\n"
        f"Region: {region_name}\n\n"
        f"Context from official safety guidelines:\n{context}\n\n"
        f"Return JSON in this exact shape:\n"
        f'{{"recommendations": [{{"category": "evacuation", "title": "...", "body": "..."}}, '
        f'... 6 items total]}}'
    )


# ── Parsing + validation ──────────────────────────────────────────────────────

def _parse_and_validate(raw_json: str) -> list[RecommendationItem]:
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise GroqUnavailableError(f"Groq returned malformed JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise GroqUnavailableError(
            f"Groq response must be a JSON object, got {type(data).__name__}"
        )

    items_raw = data.get("recommendations")
    if not isinstance(items_raw, list):
        raise GroqUnavailableError(
            "Groq response missing 'recommendations' list"
        )

    if len(items_raw) != RECOMMENDATION_COUNT:
        raise GroqUnavailableError(
            f"Expected {RECOMMENDATION_COUNT} items, got {len(items_raw)}"
        )

    items: list[RecommendationItem] = []
    for i, raw in enumerate(items_raw):
        if not isinstance(raw, dict):
            raise GroqUnavailableError(f"Item {i} is not a JSON object: {raw!r}")
        try:
            item = RecommendationItem.model_validate(raw)
        except Exception as exc:
            raise GroqUnavailableError(f"Item {i} failed validation: {exc}") from exc
        items.append(item)

    return items


def _sort_by_category(items: list[RecommendationItem]) -> list[RecommendationItem]:
    return sorted(items, key=lambda x: _CATEGORY_RANK.get(x.category, len(_CATEGORY_ORDER)))
