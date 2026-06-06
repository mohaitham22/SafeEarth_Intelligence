# SafeEarth Intelligence — Architecture Reference

> A concise, **as-built** map of the system, grounded in the current code (verified 2026-06-03).
> CLAUDE.md is the session *log* and feature spec; this file is the architecture *reference*.
> Where the two disagree, the code (and this file) wins — see [§12 Known Drift & Gaps](#12-known-drift--gaps).
>
> Design diagrams (context, use-case, activity, sequence, class, ERD, structure, wireframe) live in
> [docs/DIAGRAMS.md](docs/DIAGRAMS.md) and are not duplicated here.

---

## 1. System Overview

SafeEarth Intelligence predicts natural disasters for any lat/lon, estimates human/economic impact
with SHAP explanations, alerts subscribers (in-app + email), and generates AI safety recommendations
via a chapter-based Groq RAG pipeline. It also serves 30-day risk forecasts and global EM-DAT analytics.

**As-built stack:** Next.js 14 (App Router) + FastAPI (async, Python 3.11) + PostgreSQL 15 (Neon) +
XGBoost/CatBoost ensemble + Groq `llama-3.1-8b-instant` (chapter-based RAG, **no runtime vector store**).
Frontend on Vercel, backend on Render, models on Hugging Face Hub.

Four roles, each strictly a superset of the previous: **Guest ⊂ Subscriber ⊂ Premium ⊂ Admin**.

---

## 2. Tech Stack (as-built, confirmed)

Reconciled against [backend/requirements.txt](backend/requirements.txt) and
[frontend/package.json](frontend/package.json).

| Layer | Technology (confirmed) |
|---|---|
| Frontend framework | Next.js 14.2.18, App Router, React 18.3, TypeScript 5.6 |
| Styling / charts / maps | Tailwind v3, Recharts 2.13, Leaflet 1.9 + react-leaflet 4.2 + leaflet.heat |
| Auth (client) | NextAuth v5 (beta.22), JWT in HttpOnly cookie |
| HTTP (client) | Axios 1.7 via `lib/api.ts` (`api` server instance + `apiClient` client instance) |
| PWA | next-pwa (production only) |
| Backend framework | FastAPI + uvicorn[standard], async SQLAlchemy 2.0, asyncpg, Alembic |
| Validation / config | Pydantic v2, pydantic-settings, python-dotenv |
| Auth (server) | python-jose (HS256) + passlib/bcrypt (**bcrypt pinned 4.0.1**) |
| Rate limiting | slowapi (`@limiter.limit`) |
| Classifier | **XGBoost + CatBoost soft ensemble** (v4.2, 60/40), 16 features |
| Impact regressors | XGBoost (deaths, damage) + scikit-learn RandomForest (injuries, affected) |
| Explainability | SHAP `TreeExplainer`, cached at startup, top-3 features |
| RAG retrieval | **Chapter-based**: PyMuPDF extracts PDF → `chapters.json` at build time; loaded at startup. **No embeddings, no vector store at runtime.** |
| LLM | Groq API `llama-3.1-8b-instant` (temp 0.3) → 6 recommendations; DB fallback when unavailable |
| Email | smtplib + Jinja2 (verification) · Resend SDK (premium alerts) |
| PDF | ReportLab |
| Model hosting | Hugging Face Hub — `.pkl` downloaded at startup if absent |
| Database | PostgreSQL 15 (Neon free tier) |
| Deploy | Vercel (frontend) · Render (backend, free web service) · UptimeRobot health ping |

**Not installed at runtime** (deliberate): `chromadb`, `sentence-transformers` (OOM on Render 512 MB —
replaced by chapter-based Groq); `lightgbm`, `optuna` (training-only). The legacy vector-store files
([backend/rag/ingest.py](backend/rag/ingest.py), [benchmark.py](backend/rag/benchmark.py),
`backend/rag/chroma_db/`) are **dev/legacy-only**.

---

## 3. Backend Layering

Strict downward call hierarchy — enforced by the project skills (`.claude/commands/`):

```
main.py  →  routers/  →  services/  →  ml/ · rag/ · models/ · core/
(lifespan)  (thin,       (ALL business    (load-once resources:
            no logic)     logic)           pkl, JSON, chapters.json)
```

- **Routers are thin**: validate input → call one service → return. No DB calls, no `if/else` business
  logic, no ML calls in a router. (See the 5-file rule in [.claude/commands/add-api-endpoint.md](.claude/commands/add-api-endpoint.md).)
- **Services own all logic** and always take `db: AsyncSession`.
- **Load-once resources** (`.pkl` models, generated JSON, `chapters.json`) are loaded a single time in
  the FastAPI lifespan and held as module-level globals — never re-read per request.
- `main.py` never contains routes; it only wires the lifespan, middleware, and router registration.

The busiest module is `services/predictor_service.py` (the orchestrator) — it calls `ml/predictor`,
`ml/emdat_lookup`, and `recommendation_service` (which calls the Groq RAG), then persists to the DB.
This mirrors the Structure Chart in [docs/DIAGRAMS.md §7](docs/DIAGRAMS.md).

---

## 4. Routing Map

### Backend — 8 routers, all under `/api/v1` ([main.py:109-117](backend/main.py#L109-L117))

| Router | Prefix | Key endpoints |
|---|---|---|
| `admin.health_router` | _(none)_ | `GET/HEAD /health` — `{status, models_loaded, rag_loaded}`, pinged by UptimeRobot |
| `auth` | `/auth` | register, login, verify-email, refresh, logout |
| `predictions` | `/predictions` | `POST /predict` (60/min), `POST /forecast-30d` (5/hr), `GET /history`, `GET /{id}`, `GET /{id}/pdf` + `GET /forecast-30d/pdf` (Premium) |
| `regions` | `/regions` | 8 **public** read-only: risk-map, stats, trends, continent-stats, insurance-gap, seasonal-peaks, secondary-disasters, timeseries |
| `alerts` | `/alerts` | `POST /dispatch` (dual-auth), `GET /history` (Subscriber+) |
| `subscriptions` | `/subscriptions` | `POST` (201 + token), `GET` (active), `DELETE /{token}` (**public**, one-click unsubscribe) |
| `recommendations` | `/recommendations` | `GET` (public, RAG → 6 items, personalisation notice) |
| `premium` | `/premium` | `POST /checkout` (Subscriber+), `POST /webhook` (public, verify-first) |
| `ads` | `/ads` | `GET` (public) — active home-page promotional content for guests; Studio CRUD = Phase 10 |
| `admin` | `/admin` | `GET /data-status`, `GET /stub` — **user/role CRUD endpoints not yet built** (see §12) |

### Frontend — 14 page routes (Next.js App Router groups)

| Group | Routes |
|---|---|
| `(public)` | `/` (home) · `/map` · `/analytics` · `/analytics/timeseries` · `/forecast` · `/pricing` · `/mock-checkout` · `/unsubscribe` |
| `(auth)` | `/login` · `/register` · `/verify-email` |
| `(protected)` | `/dashboard` · `/dashboard/forecast` · `/admin` |

Plus the NextAuth handler at `app/api/auth/[...nextauth]/route.ts`. (CLAUDE.md's "17 routes" reflects
the Next build output, which counts the auth handler and `_not-found` alongside the pages.)

---

## 5. ML & Prediction Pipeline

| Concern | Location |
|---|---|
| Model load + inference | [backend/ml/predictor.py](backend/ml/predictor.py) |
| EM-DAT impact lookup | [backend/ml/emdat_lookup.py](backend/ml/emdat_lookup.py) |
| Orchestration + DB persist | [backend/services/predictor_service.py](backend/services/predictor_service.py) |
| `.pkl` artifacts | `backend/saved_models/` |

- **`MODEL_VERSION = "v4.2"`**, 16-feature soft ensemble (XGB 0.60 + CatBoost 0.40). Three pkl bundles:
  `disaster_predictor.pkl` (classifier + encoders), `impact_regressor.pkl` (4 regressors),
  `shap_explainer.pkl` (cached `TreeExplainer`).
- **Loaded once** in the lifespan ([main.py:42-54](backend/main.py#L42-L54)); `_ensure_models_downloaded()`
  pulls missing pkl from Hugging Face Hub when `HUGGINGFACE_REPO_ID` is set, else relies on local files.
- **`disaster_type` is an input** to `predict()` — the model returns P(that type), not an argmax.
- **Impact** is disaster-type-aware: `predict_impact()` blends location-aware ML regressors with EM-DAT
  type-specific medians (coverage-weighted), so Flood vs Earthquake at the same coordinates differ.
- **Risk score (0–100)** = `0.35·deaths + 0.30·affected + 0.20·damage + 0.15·probability`, each
  normalised against per-type p99 (`_EMDAT_P99` in predictor.py). **Median, never mean** — a hard rule.
- **Severity bands** (fixed): ≤0.30 Low · ≤0.55 Medium · ≤0.75 High · >0.75 Critical. Critical fires a
  non-blocking `BackgroundTask` alert dispatch.
- **30-day forecast**: loops `predict()` × 30 with `day_offset` 0–29, shares a `forecast_batch_id`, and
  caches per (lat, lon) for 24 h. RAG enrichment is de-duplicated by severity (≤4 Groq calls per batch).

---

## 6. RAG Pipeline (as-built — chapter-based Groq)

The runtime RAG path has **no embeddings and no vector store** ([backend/rag/recommender.py](backend/rag/recommender.py)):

1. **Build time** ([backend/rag/extract_chapters.py](backend/rag/extract_chapters.py), PyMuPDF):
   PDF safety guidelines → `backend/rag/chapters.json` (8 disaster types → chapter text). Wired into
   [render_build.sh](backend/scripts/render_build.sh).
2. **Startup** (`load_rag()` in the lifespan): load `chapters.json` + init the Groq client (only if
   `GROQ_API_KEY` set). Degrade-not-fail — a missing chapters file degrades to DB fallback, never blocks startup.
3. **Query time** (`get_recommendations`): look up the chapter for `disaster_type` → send as context to
   Groq `llama-3.1-8b-instant` (temp 0.3, JSON mode) → parse + validate **exactly 6** items → sort
   `evacuation → kit → shelter → medical → contact`. Any failure raises `GroqUnavailableError`.
4. **Fallback** ([backend/services/recommendation_service.py](backend/services/recommendation_service.py)):
   on `GroqUnavailableError` (incl. empty `GROQ_API_KEY`), serve from the `recommendations` DB table,
   keyed by `(disaster_type, severity_level)`. A prediction never 500s because of RAG.

> The legacy ChromaDB + sentence-transformers path (`ingest.py`, `benchmark.py`, `chunking_report.md`,
> `chroma_db/`) remains in the repo for reference but is **not used at runtime**.

---

## 7. Database Schema

9 tables, async SQLAlchemy 2.0, UUID PKs, UTC timestamps, registered in
[backend/models/__init__.py](backend/models/__init__.py). Migrations:
`a3f1d2e4b5c6_initial_schema` + `45befcdf72a9_add_unsubscribe_token_to_subscriptions`
+ `b7c1e9d4a2f0_add_ads_table`.

| Table | Role / notes |
|---|---|
| `users` | role enum (guest/subscriber/premium/admin), `is_verified`, `verification_token`. Hub for 5 FKs. |
| `subscriptions` | region + lat/lon, `alert_frequency`, `is_active` (soft delete), unique `unsubscribe_token` (powers public DELETE). 3 free / 10 premium, enforced server-side. |
| `predictions` | full result incl. `shap_explanation` (JSONB), `seasonal_peak_months` (int[]), `forecast_batch_id`/`forecast_day_offset` (group + order forecast rows). Damage stored in **thousands USD**. |
| `alerts` | per-dispatch in-app row; FK to subscription + user; `alert_type`, `severity_level`, `status`. |
| `recommendations` | **Standalone RAG fallback** — **no FK**. Keyed by `(disaster_type, severity_level)` → `title/body/category`. Used only when Groq is unavailable. ([models/recommendation.py](backend/models/recommendation.py)) |
| `premium_plans` | pre-seeded monthly $5/30d, yearly $48/365d, `max_subscriptions`. Never user-editable. |
| `payments` | **append-only/immutable** (only status + timestamps update on the same row). `premium_activated_at/expires_at` drive expiry. |
| `premium_email_logs` | Resend message-id audit trail; FK to user + alert. |
| `ads` | **Standalone home-page promotional content** — **no FK**. `title/body/image_url/link_url/cta_label`, `is_active` (soft delete), `sort_order`. Read by public `GET /ads`; seeded by migration; Studio admin CRUD = Phase 10. ([models/ad.py](backend/models/ad.py)) |

Rules: soft-delete via `is_active` (never hard-delete user data); `payments` immutable for audit;
all FKs declare explicit `ON DELETE` (CASCADE / SET NULL / RESTRICT). Full ERD in [docs/DIAGRAMS.md §6](docs/DIAGRAMS.md).

---

## 8. Auth & Role Enforcement

**The backend `Depends()` is the real security boundary; the frontend gate is UX only.**

**Single source of truth: [backend/core/permissions.py](backend/core/permissions.py).** Defines `Feature`,
`ROLE_RANK` (guest 0 · `free`/subscriber 1 · premium 2 · admin 3 — **`free` is an alias for `subscriber`**,
no separate DB role), and `can(user, feature)` / `meets_role` / `subscription_limit(role)`. Every role decision
funnels through it; there are no inline `role == "..."` checks left in routers or services. The frontend mirror
[frontend/lib/permissions.ts](frontend/lib/permissions.ts) re-implements `can`/`meetsRole`/`isAdmin` for UX
show/hide only and is never trusted.

Central dependencies in [backend/core/deps.py](backend/core/deps.py) (all built on `permissions.py`):

| Dependency | Behaviour |
|---|---|
| `get_current_user` | Requires valid JWT → `User`, else **401**. |
| `get_optional_user` | Returns `User` or `None` (guest). **Never raises.** |
| `require_admin` | `role == "admin"`, else **403**. |
| `require_premium` | `role in {premium, admin}`, else **403**. |
| `require_dispatch_auth` | **Dual**: `X-Dispatch-Secret` (constant-time `compare_digest`, n8n) **OR** Admin JWT. Empty secret disables the machine path. |
| `require_subscriber` | `role >= subscriber`. Shared (no longer duplicated per-router). |
| `require(Feature.X)` | Dependency factory gating an endpoint on a single `Feature` via `can()`. |

Service-layer role decisions also go through `permissions.py`: `subscription_service.py` uses
`subscription_limit(role)`; `alert_service.py` fan-out uses `can(user, Feature.RECEIVE_EMAIL_ALERTS)`.

Frontend: `middleware.ts` guards `/dashboard`, `/alerts`, `/subscriptions`, `/admin` by **cookie
presence only**; the `/admin` page additionally checks `session.user.role` in a `useEffect` for UX —
neither is a security control.

---

## 9. Email & Alerts

All email lives in [backend/services/email_service.py](backend/services/email_service.py) and is
**degrade-not-fail** (falls back to `_dev_log()` → console + `.email_dev.log` when creds are absent):

- `send_verification_email(to, token)` — **smtplib SMTP+STARTTLS** + Jinja2 `verify_email.html`.
  For **email verification only** (Subscribers never get alert email).
- `send_premium_alert_email(to, context) -> str` — **Resend SDK** + Jinja2 `premium_alert.html`,
  returns the message-id (or a `dev-fallback-…` sentinel) for `premium_email_logs`. Builds the
  one-click unsubscribe URL from `context["unsubscribe_token"]`.

Both are dispatched via FastAPI `BackgroundTasks` — never blocking a response.

**Alert fan-out** ([backend/services/alert_service.py](backend/services/alert_service.py)):
n8n weekly cron **or** a Critical-severity prediction → `POST /alerts/dispatch` → query active
subscriptions by region → **Subscriber: in-app `Alert` row only**; **Premium: `Alert` + email +
`PremiumEmailLog`**. The Critical path opens its own `AsyncSessionLocal` (runs after the request
session closes). Time-ordered detail in [docs/DIAGRAMS.md §4](docs/DIAGRAMS.md).

---

## 10. Payments

- Abstract `PaymentService` (ABC) + `MockPaymentService`, selected by `PAYMENT_PROVIDER` env var
  ([backend/services/payment_service.py](backend/services/payment_service.py)). Swapping to Stripe/Paymob
  is a one-file change — no router or service edits.
- `POST /premium/checkout` → `{checkout_url, session_id}`; the mock checkout page confirms via webhook.
- `POST /premium/webhook` (public) — **verify signature FIRST**, then insert/update the `payments` row and
  elevate `user.role = premium`. **Role elevation happens only here**, never from frontend state.
- A 24 h background loop (`run_expiry_loop`) downgrades expired Premium users and deactivates excess
  subscriptions (soft, never deleted).

---

## 11. Config & Deploy

- **Config** ([backend/config.py](backend/config.py)): pydantic-settings `Settings` + `@lru_cache`
  `get_settings()`. Reads `.env` from the repo root regardless of CWD. `cors_origins` is a plain
  comma-separated string split at the use site (pydantic v2 JSON-decodes `list[str]` too eagerly).
- **Backend deploy** ([render.yaml](render.yaml)): `buildCommand = bash backend/scripts/render_build.sh`,
  `healthCheckPath = /api/v1/health`, secrets marked `sync: false`. Build steps: install deps → generate
  EM-DAT JSON → `extract_chapters.py` → `alembic upgrade head` → seed recommendations → seed test users.
- **Frontend deploy**: Vercel (root dir `frontend/`), env `NEXT_PUBLIC_API_BASE_URL`, `NEXTAUTH_*`/`AUTH_*`.
- **Local**: `docker-compose.yml` (postgres:15, named volume `safeearth-pgdata`). Run backend with
  `cd backend && uvicorn main:app --reload`.
- **Env inventory** (selected): `DATABASE_URL`, `SECRET_KEY`, `SMTP_*`, `RESEND_API_KEY`,
  `HUGGINGFACE_REPO_ID/TOKEN`, `GROQ_API_KEY`, `ALERT_DISPATCH_SECRET`, `PAYMENT_PROVIDER`, `CORS_ORIGINS`.

---

## 12. Known Drift & Gaps

Honest as-built vs aspirational notes (source for the forthcoming TODO.md):

1. **Stale ChromaDB references in live code** — [main.py:56-67](backend/main.py#L56-L67) comments, the
   startup log (`"RAG pipeline loaded (ChromaDB + embedder + Groq client)"`), and the FileNotFoundError
   hint (`run backend/rag/ingest.py to rebuild ChromaDB`) still describe the **removed** vector-store
   pipeline. The actual loader is chapter-based. Cosmetic but misleading.
2. **Admin backend CRUD not built** — [backend/routers/admin.py](backend/routers/admin.py) has only
   `/health`, `/admin/data-status`, `/admin/stub`. Missing: `GET /admin/users`, `PATCH /admin/users/{id}`,
   `GET /admin/model-stats`, `POST /admin/alerts/trigger`. The frontend `/admin` page handles the 404 gracefully.
3. **Live integrations unconfigured (creds empty)** — SMTP, Resend, `GROQ_API_KEY`,
   `ALERT_DISPATCH_SECRET` + n8n, and a real payment provider (`PAYMENT_PROVIDER=mock`). All degrade
   gracefully today but mean email/RAG/dispatch run in fallback mode.
4. **`GET /premium/history` + `schemas/payment.py`** are specified but not built.
5. **Test users seeded into production** every deploy (`seed_test_users.py` in render_build.sh) — review
   before a real launch.
6. **CLAUDE.md "Tech Stack" RAG rows** were stale (now corrected in place to match §2 / §6 above).

---

*Verified against the codebase on 2026-06-03. Update this file when the architecture changes — not after
every session (that's CLAUDE.md's job).*
