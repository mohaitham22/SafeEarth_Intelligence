"""
backend/rag/recommender.py — Runtime RAG pipeline (chapter-based Groq).

Architecture (Render-free-tier compatible):
  - At startup: load chapters.json (plain text, no PyTorch, no ChromaDB).
  - At query time: look up the chapter for the requested disaster_type,
    send it as context to Groq llama-3.1-8b-instant, parse 6 recommendations.
  - Falls back to the recommendations DB table on any Groq failure.

Why chapters instead of ChromaDB:
  sentence-transformers pulls in PyTorch + CUDA packages (~2 GB), which causes
  OOM on Render's 512 MB free tier.  Chapter-level retrieval requires only the
  `groq` SDK (already in requirements.txt) and the pre-extracted chapters.json.

Cardinal rules (unchanged from original):
  - load_rag()            NEVER called from a route or service function
  - Groq client           NEVER instantiated per-request (cached at startup)
  - get_recommendations() NEVER called from a router (service layer only)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import get_settings
from schemas.recommendation import RecommendationItem

# ── Paths ─────────────────────────────────────────────────────────────────────

_THIS_DIR     = Path(__file__).resolve().parent
CHAPTERS_PATH = _THIS_DIR / "chapters.json"

# ── Tunable constants ─────────────────────────────────────────────────────────

RECOMMENDATION_COUNT = 6                       # Per CLAUDE.md Feature 5 contract
GROQ_MODEL           = "llama-3.1-8b-instant"  # Per CLAUDE.md RAG Pipeline spec
GROQ_TEMPERATURE     = 0.3                     # Per CLAUDE.md RAG Pipeline spec

_CATEGORY_ORDER   = ["evacuation", "kit", "shelter", "medical", "contact"]
_CATEGORY_RANK    = {c: i for i, c in enumerate(_CATEGORY_ORDER)}
_VALID_CATEGORIES = set(_CATEGORY_ORDER)

# ── Module-level singletons — None until load_rag() runs at startup ───────────

_chapters:    dict[str, str] | None = None   # {emdat_disaster_type: chapter_text}
_groq_client: Any                   = None   # groq.Groq | None


# ── Exceptions ────────────────────────────────────────────────────────────────

class GroqUnavailableError(Exception):
    """Raised when Groq cannot deliver a valid 6-item JSON response.

    The service layer catches this and falls back to the `recommendations` DB
    table.  Reasons: missing GROQ_API_KEY, network error, rate-limit,
    malformed JSON, wrong item count, invalid category, or Pydantic failure.
    """


# ── Startup loader ────────────────────────────────────────────────────────────

def load_rag() -> None:
    """Load chapters.json and initialise the Groq client.

    Called ONCE in the FastAPI lifespan context manager in main.py.
    Never call from a route or service function.

    Raises:
        FileNotFoundError: if chapters.json hasn't been generated yet.
            Fix: run  py -3.12 backend/rag/extract_chapters.py
    """
    global _chapters, _groq_client

    if not CHAPTERS_PATH.exists():
        raise FileNotFoundError(
            f"chapters.json missing: {CHAPTERS_PATH}\n"
            f"Run: py -3.12 backend/rag/extract_chapters.py from the project root."
        )

    _chapters = json.loads(CHAPTERS_PATH.read_text(encoding="utf-8"))
    print(f"  Chapters     : {len(_chapters)} disaster types loaded from chapters.json")

    settings = get_settings()
    if settings.groq_api_key:
        from groq import Groq  # local import — keeps groq off path for tests
        _groq_client = Groq(api_key=settings.groq_api_key)
        groq_status  = f"ready (model={GROQ_MODEL})"
    else:
        _groq_client = None
        groq_status  = "DISABLED (GROQ_API_KEY empty — fallback to DB recommendations)"

    print(f"  Groq         : {groq_status}")


# ── Public API ────────────────────────────────────────────────────────────────

def get_recommendations(
    disaster_type: str,
    severity: str,
    region_name: str,
) -> list[RecommendationItem]:
    """Return exactly 6 recommendations using chapter context + Groq.

    Raises:
        RuntimeError: if load_rag() was not called at startup.
        GroqUnavailableError: any Groq failure — service layer catches this
            and falls back to the DB recommendations table.
    """
    if _chapters is None:
        raise RuntimeError(
            "RAG not loaded — load_rag() must run in the FastAPI lifespan at startup."
        )
    if _groq_client is None:
        raise GroqUnavailableError("Groq client not initialised (GROQ_API_KEY missing)")

    chapter_text = _chapters.get(disaster_type) or _chapters.get(
        next((k for k in _chapters if k.lower() == disaster_type.lower()), ""),
        "",
    )
    if not chapter_text:
        raise GroqUnavailableError(
            f"No chapter found for disaster_type={disaster_type!r}"
        )

    user_prompt = _build_user_prompt(disaster_type, severity, region_name, chapter_text)

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
    chapter_text: str,
) -> str:
    # Truncate chapter to ~6000 chars to stay well within Groq's context window
    # while keeping the prompt fast.  The full chapter is ~3000–5000 chars.
    context = chapter_text[:6000]
    return (
        f"Disaster type: {disaster_type}\n"
        f"Severity: {severity}\n"
        f"Region: {region_name}\n\n"
        f"Context from official safety guidelines:\n{context}\n\n"
        f"Return JSON in this exact shape:\n"
        f'{{"recommendations": [{{"category": "evacuation", "title": "...", "body": "..."}}, '
        f"... 6 items total]}}"
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
        raise GroqUnavailableError("Groq response missing 'recommendations' list")

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
