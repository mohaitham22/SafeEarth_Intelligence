# SafeEarth Intelligence — System Design Diagrams

This document contains eight design diagrams for the SafeEarth Intelligence platform, each with an explanation. All diagrams use [Mermaid](https://mermaid.js.org/) (renders natively in GitHub and VS Code) except the UI wireframe, which is ASCII.

**System summary:** A web app that predicts natural disasters for any region (XGBoost + CatBoost on 16,126 EM-DAT events), estimates human/economic impact with SHAP explanations, alerts users by email, and generates AI safety recommendations via a chapter-based Groq RAG pipeline. Four roles: Guest, Subscriber, Premium, Admin.

---

## Table of Contents
1. [Context Diagram](#1-context-diagram)
2. [Use Case Diagram](#2-use-case-diagram)
3. [Activity Diagram — Disaster Prediction Flow](#3-activity-diagram--disaster-prediction-flow)
4. [Sequence Diagram — Alert Dispatch](#4-sequence-diagram--alert-dispatch)
5. [Class Diagram](#5-class-diagram)
6. [Entity Relationship Diagram (ERD)](#6-entity-relationship-diagram-erd)
7. [Structure Chart](#7-structure-chart)
8. [UI Wireframes — Public Dashboard](#8-ui-wireframes--public-dashboard)

---

## 1. Context Diagram

**What it shows:** SafeEarth as a single black box (Level-0 DFD) and every external entity it exchanges data with — human roles on the left, third-party services on the right. It answers "what is inside the system boundary and what is outside."

```mermaid
flowchart LR
    Guest([Guest])
    Subscriber([Subscriber])
    Premium([Premium User])
    Admin([Admin])

    subgraph SYS [SafeEarth Intelligence Platform]
        CORE{{Next.js Frontend<br/>+ FastAPI Backend<br/>+ PostgreSQL}}
    end

    Groq[[Groq LLM API<br/>llama-3.1-8b-instant]]
    Resend[[Resend.com<br/>Premium email]]
    SMTP[[Gmail SMTP<br/>verification email]]
    N8N[[n8n<br/>weekly cron]]
    HF[[HuggingFace Hub<br/>model .pkl hosting]]
    PAY[[Payment Provider<br/>mock / Stripe]]
    UPTIME[[UptimeRobot<br/>health ping]]

    Guest -->|view map, analytics, forecast teaser| CORE
    CORE -->|public charts + heatmap JSON| Guest

    Subscriber -->|run prediction, subscribe, login| CORE
    CORE -->|prediction + recommendations + in-app alerts| Subscriber

    Premium -->|checkout, download PDF| CORE
    CORE -->|PDF reports + email alerts| Premium

    Admin -->|manage users, dispatch alerts, model stats| CORE
    CORE -->|admin panel data| Admin

    CORE -->|safety query + chapter context| Groq
    Groq -->|6 recommendations JSON| CORE

    CORE -->|HTML alert email| Resend
    CORE -->|verification token email| SMTP

    N8N -->|POST /alerts/dispatch + secret| CORE

    HF -->|download models at startup| CORE
    CORE -->|checkout session / webhook| PAY
    UPTIME -->|GET /health every 14 min| CORE
```

**Key flows explained:**
- **Humans (left):** Each role has a different read/write contract. Guests only consume public precomputed JSON; Subscribers gain the prediction pipeline; Premium adds email + PDF; Admin adds management.
- **Services (right):** Groq generates recommendations at request time; Resend/SMTP are outbound-only (email); n8n is inbound-only (it *calls* the system, never the reverse — an architectural rule); HuggingFace and the Payment Provider are dependencies the system reaches out to.
- The system boundary deliberately includes the database — PostgreSQL is internal state, not an external actor.

---

## 2. Use Case Diagram

**What it shows:** Every actor and the use cases each can perform. Mermaid has no native use-case notation, so actors are rounded nodes and use cases are pill-shaped, grouped by privilege tier. Higher tiers inherit everything below them (Subscriber ⊂ Premium ⊂ Admin).

```mermaid
flowchart TB
    GUEST([Guest])
    SUB([Subscriber])
    PREM([Premium])
    ADMIN([Admin])
    N8N([n8n / Scheduler])

    subgraph Public[Public — no login]
        UC1(View risk heatmap)
        UC2(View analytics / time series)
        UC3(View 30-day forecast teaser)
        UC4(Get safety recommendations)
        UC5(Register / Verify email / Login)
        UC6(Unsubscribe via email link)
    end

    subgraph SubArea[Subscriber+]
        UC7(Run disaster prediction)
        UC8(Run 30-day forecast)
        UC9(Manage region subscriptions - max 3)
        UC10(View prediction & alert history)
        UC11(Receive in-app alerts)
    end

    subgraph PremArea[Premium+]
        UC12(Receive HTML email alerts)
        UC13(Download PDF reports)
        UC14(Subscribe to up to 10 regions)
        UC15(Upgrade via checkout)
    end

    subgraph AdminArea[Admin only]
        UC16(Manage all users / roles)
        UC17(Manually dispatch alerts)
        UC18(View ML model stats)
    end

    GUEST --- UC1 & UC2 & UC3 & UC4 & UC5 & UC6
    SUB --- UC7 & UC8 & UC9 & UC10 & UC11
    PREM --- UC12 & UC13 & UC14 & UC15
    ADMIN --- UC16 & UC17 & UC18
    N8N --- UC17
```

**Key points explained:**
- **Tier inheritance:** A Premium user can still do everything a Subscriber can; the diagram only lists each tier's *new* capabilities to stay readable.
- **n8n as a non-human actor:** The scheduler triggers *Manually dispatch alerts* (UC17) on its weekly cron — the same use case an Admin can invoke manually. This reflects the dual-auth on `POST /alerts/dispatch` (X-Dispatch-Secret OR Admin JWT).
- **Personalisation:** *Get recommendations* (UC4) is public, but if the requester has a prior alert for the same disaster+region it prepends a "you were previously warned" notice — an `«extend»` relationship in formal UML.
- **Payment authority:** *Upgrade via checkout* (UC15) starts the flow, but role elevation happens only in the webhook handler — never from the frontend.

---

## 3. Activity Diagram — Disaster Prediction Flow

**What it shows:** The end-to-end control flow of `POST /predictions/predict`, from auth gate to the single JSON response, including the swimlane-style branch where Critical severity fires a background alert. This is the core ML request path.

```mermaid
flowchart TD
    A([User submits lat/lon + disaster_type]) --> B{Authenticated<br/>Subscriber+?}
    B -->|No| B1[Return 401 / show Sign-up CTA] --> Z([End])
    B -->|Yes| C{Rate limit<br/>60/min OK?}
    C -->|Exceeded| C1[Return 429] --> Z
    C -->|OK| D[predictor.predict: XGBoost+CatBoost ensemble]
    D --> E[Compute P of disaster_type]
    E --> F[Map probability to severity band]
    F --> G[predict_impact: blend ML regressors + EM-DAT medians]
    G --> H[resolve_impact_stats: 3-tier country -> region -> global]
    H --> I[Compute risk_score 0-100 + uninsured loss]
    I --> J[SHAP TreeExplainer: top-3 features]
    J --> K[Get recommendations via RAG]
    K --> K1{Groq available?}
    K1 -->|Yes| K2[Groq LLM -> 6 items]
    K1 -->|No| K3[Fallback: recommendations DB table]
    K2 --> L
    K3 --> L[Assemble full PredictionResponse]
    L --> M[Persist row to predictions table]
    M --> N{severity == Critical?}
    N -->|Yes| O[BackgroundTask: dispatch_critical_alert]
    N -->|No| P[Return JSON response]
    O --> P
    P --> Z([End])
```

**Key points explained:**
- **Two guard gates first:** Authentication (Subscriber+) and the slowapi rate limit (60/min) short-circuit before any ML work happens — cheap rejections protect the expensive path.
- **Impact is disaster-type aware:** `predict_impact` blends the location-aware ML regressors with EM-DAT disaster-type-specific medians (e.g. 70/30 for deaths), so a Flood and an Earthquake at the same coordinates return different numbers.
- **RAG never blocks the prediction:** If Groq is down, the flow silently falls back to the seeded `recommendations` DB table — a prediction never 500s because of RAG.
- **Critical = non-blocking fan-out:** When severity is Critical, alerts dispatch as a FastAPI `BackgroundTask` *after* the response is assembled, so the user still gets their result in one fast round-trip.
- **Always persisted:** Every prediction is saved to the DB (the response is returned in a single call with all fields together).

---

## 4. Sequence Diagram — Alert Dispatch

**What it shows:** The time-ordered message exchange when the weekly n8n cron triggers a dispatch, including the role-based fan-out (Subscriber → in-app only; Premium → in-app + email + log) and the non-blocking BackgroundTask for email.

```mermaid
sequenceDiagram
    participant N8N as n8n (cron Mon 08:00)
    participant API as FastAPI /alerts/dispatch
    participant DEP as require_dispatch_auth
    participant SVC as alert_service
    participant DB as PostgreSQL
    participant BG as BackgroundTask
    participant RS as Resend.com

    N8N->>API: POST /alerts/dispatch (X-Dispatch-Secret)
    API->>DEP: validate secret (compare_digest) OR Admin JWT
    alt invalid secret
        DEP-->>API: raise 401
        API-->>N8N: 401 Unauthorized
    else valid
        DEP-->>API: authorized
        API->>SVC: dispatch_alerts(db)
        SVC->>DB: SELECT active subscriptions by region
        DB-->>SVC: subscription rows

        loop each subscription
            SVC->>DB: INSERT Alert (in-app, status=sent)
            alt user is Premium
                SVC->>DB: INSERT PremiumEmailLog
                SVC->>BG: schedule _send_premium_email_background
            end
        end

        SVC->>DB: COMMIT
        SVC-->>API: {queued: N}
        API-->>N8N: 200 {queued: N} (≈0.14s)

        Note over BG,RS: runs AFTER response is sent
        BG->>RS: send_premium_alert_email(context)
        alt creds present
            RS-->>BG: message_id
        else creds empty (dev)
            BG->>BG: _dev_log -> "dev-fallback-..."
        end
        BG->>DB: update PremiumEmailLog.resend_message_id
    end
```

**Key points explained:**
- **Dual auth up front:** `require_dispatch_auth` accepts either the machine secret (constant-time `secrets.compare_digest`) or an Admin JWT — the same endpoint serves both n8n and the Admin panel's "Manual Dispatch" button.
- **Role-based fan-out:** Free Subscribers get an in-app `Alert` row only; Premium users additionally get a `PremiumEmailLog` row and a scheduled email. This matches the strict "Subscribers receive no email" rule.
- **Response returns before email sends:** The HTTP response (`200 {queued: N}`) is committed and returned in ~0.14s; the actual Resend call happens in a `BackgroundTask` afterward, so dispatch is never blocked by SMTP/Resend latency.
- **Degrade-not-fail:** If Resend credentials are empty (current dev/prod state), the email path logs a `dev-fallback-...` sentinel instead of throwing — the dispatch still succeeds.
- **Same shape for Critical predictions:** The immediate Critical-severity path (`dispatch_critical_alert`) follows this exact pattern but opens its own `AsyncSessionLocal` because it runs after the request session has closed.

---

## 5. Class Diagram

**What it shows:** The backend's main classes across three layers — Pydantic/ORM data models, the service layer (business logic), and the abstract PaymentService strategy. Routers are intentionally thin and call only services, so they're omitted.

```mermaid
classDiagram
    class User {
        +UUID id
        +str email
        +str password_hash
        +UserRole role
        +bool is_verified
        +str verification_token
    }
    class Subscription {
        +UUID id
        +UUID user_id
        +str region_name
        +float latitude
        +float longitude
        +AlertFrequency alert_frequency
        +bool is_active
        +str unsubscribe_token
    }
    class Prediction {
        +UUID id
        +UUID user_id
        +str disaster_type
        +float probability_score
        +SeverityLevel severity_level
        +float risk_score
        +int estimated_deaths
        +JSONB shap_explanation
        +UUID forecast_batch_id
    }
    class Alert {
        +UUID id
        +UUID subscription_id
        +AlertType alert_type
        +SeverityLevel severity_level
        +AlertStatus status
    }
    class Payment {
        +UUID id
        +UUID user_id
        +PaymentStatus status
        +datetime premium_expires_at
    }
    class PremiumPlan {
        +UUID id
        +str name
        +Numeric price_usd
        +int duration_days
    }

    class PredictorService {
        +run_prediction_for_request()
        +run_forecast_30d()
    }
    class RecommendationService {
        +get_recommendations()
        +get_for_prediction()
    }
    class AlertService {
        +dispatch_critical_alert()
        +dispatch_alerts()
        +get_alert_history()
    }
    class PremiumService {
        +create_checkout()
        +handle_webhook_event()
        +downgrade_expired_premium()
    }
    class EmailService {
        +send_verification_email()
        +send_premium_alert_email()
    }

    class PaymentService {
        <<abstract>>
        +create_checkout_session()*
        +verify_webhook_signature()*
    }
    class MockPaymentService {
        +create_checkout_session()
        +verify_webhook_signature()
    }

    User "1" --> "*" Subscription : owns
    User "1" --> "*" Prediction : runs
    User "1" --> "*" Payment : makes
    Subscription "1" --> "*" Alert : triggers
    Payment "*" --> "1" PremiumPlan : for plan

    PredictorService ..> RecommendationService : uses
    PredictorService ..> Prediction : creates
    AlertService ..> EmailService : uses
    AlertService ..> Alert : creates
    PremiumService ..> PaymentService : uses
    PremiumService ..> Payment : creates
    PaymentService <|-- MockPaymentService : implements
```

**Key points explained:**
- **Three layers:** Data models (top) are persisted SQLAlchemy entities; services (middle) hold *all* business logic; the strategy pattern (bottom) abstracts payments.
- **Strategy pattern for payments:** `PaymentService` is an ABC; `MockPaymentService` is the v1 implementation. Swapping to Stripe is a one-file change selected by the `PAYMENT_PROVIDER` env var — no router or service edits.
- **Service dependencies (dashed arrows):** `PredictorService` orchestrates the prediction (calling `RecommendationService` for RAG); `AlertService` uses `EmailService` for Premium emails; `PremiumService` is the sole authority that elevates a user's role (in `handle_webhook_event`).
- **Why no router classes:** Per the project's coding rules, routers contain no logic — they validate input and call a service — so the meaningful object model lives entirely in models + services.

---

## 6. Entity Relationship Diagram (ERD)

**What it shows:** All 8 database tables with their columns, primary/foreign keys, and cardinalities. This is the physical data model backing the entire app.

```mermaid
erDiagram
    USERS ||--o{ SUBSCRIPTIONS : has
    USERS ||--o{ PREDICTIONS : runs
    USERS ||--o{ ALERTS : receives
    USERS ||--o{ PAYMENTS : makes
    USERS ||--o{ PREMIUM_EMAIL_LOGS : logged_for
    SUBSCRIPTIONS ||--o{ ALERTS : generates
    PREMIUM_PLANS ||--o{ PAYMENTS : purchased_as
    ALERTS ||--o{ PREMIUM_EMAIL_LOGS : emailed_as

    USERS {
        UUID id PK
        string email UK
        string password_hash
        string full_name
        enum role
        bool is_verified
        string verification_token
        timestamp created_at
    }
    SUBSCRIPTIONS {
        UUID id PK
        UUID user_id FK
        string region_name
        float latitude
        float longitude
        enum alert_frequency
        bool is_active
        string unsubscribe_token UK
    }
    PREDICTIONS {
        UUID id PK
        UUID user_id FK
        string disaster_type
        float probability_score
        enum severity_level
        float risk_score
        int estimated_deaths
        int estimated_injuries
        int estimated_affected
        bigint estimated_damage_usd
        bigint uninsured_loss_usd
        jsonb shap_explanation
        int_array seasonal_peak_months
        UUID forecast_batch_id
        int forecast_day_offset
    }
    ALERTS {
        UUID id PK
        UUID subscription_id FK
        UUID user_id FK
        enum alert_type
        string disaster_type
        enum severity_level
        text message_body
        enum status
        timestamp sent_at
    }
    RECOMMENDATIONS {
        UUID id PK
        string disaster_type
        enum severity_level
        string title
        text body
        enum category
    }
    PREMIUM_PLANS {
        UUID id PK
        string name UK
        numeric price_usd
        int duration_days
        int max_subscriptions
        bool is_active
    }
    PAYMENTS {
        UUID id PK
        UUID user_id FK
        UUID plan_id FK
        string provider
        string provider_transaction_id
        numeric amount_usd
        enum status
        timestamp premium_activated_at
        timestamp premium_expires_at
    }
    PREMIUM_EMAIL_LOGS {
        UUID id PK
        UUID user_id FK
        UUID alert_id FK
        string resend_message_id
        enum email_type
        enum status
        timestamp sent_at
    }
```

**Key points explained:**
- **Users is the hub:** Five tables hang off `users` via `user_id` FK (all `ON DELETE CASCADE`), making it the central entity.
- **RECOMMENDATIONS stands alone:** It has no FK — it's a static RAG *fallback* lookup table keyed by `(disaster_type, severity_level)`, used only when Groq is unavailable.
- **Forecast grouping:** `predictions.forecast_batch_id` (nullable UUID) groups the 30 rows of a single 30-day forecast; `forecast_day_offset` (0–29) orders them. A null batch id marks a single prediction.
- **Soft-delete & immutability rules:** Subscriptions use `is_active=False` rather than hard delete; `payments` rows are immutable (only status/timestamps update on the same row) for an audit trail.
- **Units worth noting:** `estimated_damage_usd` / `uninsured_loss_usd` are stored in **thousands** of USD; the frontend multiplies by 1,000 before formatting.

---

## 7. Structure Chart

**What it shows:** A top-down functional decomposition of the backend — how `main.py` delegates down through routers to services to the ML/RAG/data layers. Unlike the class diagram (objects), this shows *module call hierarchy* (who invokes whom).

```mermaid
flowchart TD
    MAIN[main.py<br/>FastAPI + lifespan]

    MAIN --> R1[auth router]
    MAIN --> R2[predictions router]
    MAIN --> R3[recommendations router]
    MAIN --> R4[subscriptions router]
    MAIN --> R5[alerts router]
    MAIN --> R6[premium router]
    MAIN --> R7[regions router]
    MAIN --> R8[admin router]

    R1 --> S1[auth_service]
    R2 --> S2[predictor_service]
    R3 --> S3[recommendation_service]
    R4 --> S4[subscription_service]
    R5 --> S5[alert_service]
    R6 --> S6[premium_service]
    R2 --> S7[pdf_service]

    S2 --> M1[ml/predictor<br/>XGBoost+CatBoost+SHAP]
    S2 --> M2[ml/emdat_lookup<br/>3-tier medians]
    S2 --> S3
    S3 --> M3[rag/recommender<br/>chapters + Groq]
    S5 --> S8[email_service]
    S6 --> S9[payment_service<br/>Mock/Stripe]

    M1 --> DATA[(saved_models/*.pkl)]
    M2 --> JSON[(data/generated/*.json)]
    M3 --> CHAP[(rag/chapters.json)]
    S8 --> EMAIL[[SMTP / Resend]]
    S1 & S2 & S4 & S5 & S6 --> ORM[(SQLAlchemy / PostgreSQL)]
```

**Key points explained:**
- **Strict layering:** `main.py` → routers → services → ml/rag/data. Control only flows downward; no router imports another router, and no router contains logic (it just calls one service).
- **predictor_service is the orchestrator:** It's the busiest module — it calls `ml/predictor` (the models), `ml/emdat_lookup` (impact medians), and `recommendation_service` (which in turn calls the Groq RAG), then persists to the DB.
- **Load-once resources (leaf data stores):** The `.pkl` models, generated JSON, and `chapters.json` are loaded a single time in the FastAPI lifespan and held in memory — never re-read per request.
- **Reading the chart:** Each box is a module/function; each arrow is a "calls" relationship. This is the classic structured-design view that complements the object-oriented class diagram.

---

## 8. UI Wireframes — Public Dashboard

**What it shows:** The low-fidelity layout of the public home page (`app/(public)/page.tsx`) as a Guest sees it — a Server Component that fetches `/regions/*` in parallel and renders hero stats, insight cards, a locked forecast teaser, and a features grid.

```
┌──────────────────────────────────────────────────────────────────────┐
│  🌍 SafeEarth Intelligence    Map  Analytics  Pricing      [ Log In ] │  ← Nav (guest)
├──────────────────────────────────────────────────────────────────────┤
│                                                                        │
│        Predict Natural Disasters Anywhere on Earth                     │
│        AI-powered risk, impact estimates & safety guidance            │  ← Hero
│              [ Explore Risk Map ]   [ Sign Up Free ]                   │
│                                                                        │
├──────────────────────────────────────────────────────────────────────┤
│   ┌───────────┐   ┌───────────┐   ┌───────────┐                        │
│   │  13,939   │   │     8     │   │     5     │                        │  ← Stat tiles
│   │  events   │   │ disaster  │   │continents │                        │   (from JSON)
│   │ 1900–2021 │   │  types    │   │  covered  │                        │
│   └───────────┘   └───────────┘   └───────────┘                        │
├──────────────────────────────────────────────────────────────────────┤
│   ┌──────────────────────────┐  ┌──────────────────────────┐          │
│   │ 📈 Floods grew 3.3×       │  │ 🛡️ Insurance gap          │          │  ← Insight cards
│   │ 524 (1980s) → 1,725       │  │ Earthquake 17% • Flood    │          │   (live values)
│   │ (2000s)                   │  │ 26% of damage covered     │          │
│   └──────────────────────────┘  └──────────────────────────┘          │
├──────────────────────────────────────────────────────────────────────┤
│   30-Day Forecast                              🔒 Sign up to unlock    │
│   ┌──┬──┬──┬──┬──┬──┐   ╳ ╳ ╳ ╳ ╳ ╳   (blurred 5×6 grid teaser)        │  ← Forecast teaser
│   ├──┼──┼──┼──┼──┼──┤   ╳ ╳ ╳ ╳ ╳ ╳                                     │   (zero API calls,
│   └──┴──┴──┴──┴──┴──┘   ╳ ╳ ╳ ╳ ╳ ╳        [ Create Free Account ]     │    guest-only)
├──────────────────────────────────────────────────────────────────────┤
│   Why SafeEarth?                                                       │
│   ┌────────────────┐ ┌────────────────┐ ┌────────────────┐            │
│   │ 🎯 Predictions │ │ 🗺️ Risk Map     │ │ 📨 Alerts       │            │  ← Features grid
│   │ ML + SHAP      │ │ Leaflet heatmap │ │ Email & in-app  │            │
│   └────────────────┘ └────────────────┘ └────────────────┘            │
├──────────────────────────────────────────────────────────────────────┤
│   © SafeEarth Intelligence · Data: EM-DAT (1900–2021)                  │  ← Footer
└──────────────────────────────────────────────────────────────────────┘
```

**Key points explained:**
- **Server-rendered, data-driven:** The page is a Next.js Server Component that fetches `/regions/trends` + `/regions/continent-stats` in parallel (revalidate 3600s). The stat tiles and insight cards show *live* values computed from the precomputed JSON — not hardcoded.
- **Guest-locked forecast teaser:** The 5×6 grid is purely decorative (blurred, zero API calls). Its only action is the "Create Free Account" CTA → `/register`. The real forecast lives behind auth at `/dashboard/forecast`.
- **Auth-aware nav:** As a Guest, the nav shows only public links + "Log In". After login it swaps to a role badge, dashboard links, and a Log Out button (rendered by the `Nav` client component).
- **Two primary CTAs in the hero** route to the two entry points: explore the map (public) or sign up (to unlock predictions). Every visible string comes from `lib/strings.ts` (no hardcoded UI text).

---

*Generated for SafeEarth Intelligence v1. Diagrams reflect the architecture documented in CLAUDE.md.*
