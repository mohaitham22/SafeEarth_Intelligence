from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from the project root regardless of the working directory
_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Phase 1: required at startup ──────────────────────────────────────────
    database_url: str
    secret_key: str
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ── Phase 6: email (optional until Phase 6) ───────────────────────────────
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    resend_api_key: str = ""
    resend_from_email: str = "alerts@safeearth.tech"
    frontend_url: str = "http://localhost:3000"
    # Email send robustness — applied to both SMTP (verification) and Resend (alerts).
    email_timeout_seconds: int = 15
    email_max_retries: int = 3

    # ── Phase 2: Data pipeline ────────────────────────────────────────────────
    data_generated_dir: Path = _ROOT / "data" / "generated"

    # ── Phase 3: ML models ────────────────────────────────────────────────────
    saved_models_dir: Path = _ROOT / "backend" / "saved_models"

    # ── Phase 2: ML model download (optional until Phase 2) ───────────────────
    huggingface_token: str = ""
    huggingface_repo_id: str = ""

    # ── Phase 4: RAG (optional until Phase 4) ─────────────────────────────────
    groq_api_key: str = ""

    # ── Phase 6: automation (optional until Phase 6) ──────────────────────────
    n8n_webhook_url: str = ""
    # Shared secret for POST /alerts/dispatch — n8n sends this in X-Dispatch-Secret header.
    # Empty = machine path disabled; admin JWT still works.
    alert_dispatch_secret: str = ""

    # ── Phase 7: payment (optional until Phase 7) ─────────────────────────────
    payment_provider: str = "mock"
    payment_webhook_secret: str = ""

    # ── CORS — stored as a plain comma-separated string so Render env var
    # "https://safeearth.tech,https://www.safeearth.tech" parses without error.
    # pydantic-settings v2 JSON-decodes list[str] fields before validators run,
    # which breaks on bare comma-separated values. Split at the use site instead.
    cors_origins: str = (
        "http://localhost:3000,https://safeearth.tech,https://www.safeearth.tech"
    )

    # ── Rate limiting ─────────────────────────────────────────────────────────
    rate_limit_guest: int = 10
    rate_limit_auth: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
