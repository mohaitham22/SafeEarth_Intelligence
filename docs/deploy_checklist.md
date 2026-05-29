# Render Deployment — Environment Variable Checklist

Set every variable in **Render dashboard → Environment → Environment Variables** before deploying.

Legend:
- 🔴 **CRITICAL** — app will crash or refuse to start without this
- 🟡 **IMPORTANT** — feature degrades silently without this (fallback exists)
- 🟢 **OPTIONAL** — v1 can ship without it; add later

---

## Database

| Variable | Value | Priority |
|----------|-------|----------|
| `DATABASE_URL` | `postgresql+asyncpg://<user>:<pw>@<host>/<db>?sslmode=require` — Neon.tech **direct** URL | 🔴 CRITICAL |

> Use the **direct** (non-pooled) Neon URL. The pooled URL can cause `asyncpg` connection errors with SQLAlchemy 2.0.

---

## Auth / Security

| Variable | Value | Priority |
|----------|-------|----------|
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_hex(32))"` | 🔴 CRITICAL |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | 🟢 OPTIONAL (default 30) |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | 🟢 OPTIONAL (default 7) |

---

## ML Models (HuggingFace)

| Variable | Value | Priority |
|----------|-------|----------|
| `HUGGINGFACE_REPO_ID` | `<your-hf-username>/safeearth-models` | 🔴 CRITICAL |
| `HUGGINGFACE_TOKEN` | `hf_...` (read-only token from huggingface.co/settings/tokens) | 🔴 CRITICAL |

> Without these, `disaster_predictor.pkl`, `impact_regressor.pkl`, `shap_explainer.pkl` won't download and the app crashes at startup.

---

## RAG / Recommendations

| Variable | Value | Priority |
|----------|-------|----------|
| `GROQ_API_KEY` | `gsk_...` (free at console.groq.com) | 🟡 IMPORTANT |

> Without `GROQ_API_KEY`, recommendations fall back to the DB table (static). Predictions still work. Get a free key at console.groq.com — no billing required.

---

## Frontend / CORS

| Variable | Value | Priority |
|----------|-------|----------|
| `FRONTEND_URL` | `https://safeearth.tech` | 🔴 CRITICAL |
| `CORS_ORIGINS` | `https://safeearth.tech,https://www.safeearth.tech` | 🔴 CRITICAL |

> `FRONTEND_URL` is used to build unsubscribe links in emails. `CORS_ORIGINS` must include both www and non-www or the browser will block API calls.

---

## Payment

| Variable | Value | Priority |
|----------|-------|----------|
| `PAYMENT_PROVIDER` | `mock` | 🔴 CRITICAL |
| `PAYMENT_WEBHOOK_SECRET` | `python -c "import secrets; print(secrets.token_hex(32))"` | 🔴 CRITICAL |

---

## Alerts / Automation

| Variable | Value | Priority |
|----------|-------|----------|
| `ALERT_DISPATCH_SECRET` | `python -c "import secrets; print(secrets.token_hex(32))"` | 🟡 IMPORTANT |

> Without this, the n8n weekly dispatch path is disabled (admin JWT path still works). Can be filled later when n8n is wired.

---

## Email — Verification (Gmail SMTP)

| Variable | Value | Priority |
|----------|-------|----------|
| `SMTP_HOST` | `smtp.gmail.com` | 🟢 OPTIONAL |
| `SMTP_PORT` | `587` | 🟢 OPTIONAL |
| `SMTP_USER` | `your@gmail.com` | 🟢 OPTIONAL |
| `SMTP_PASSWORD` | 16-char Gmail App Password (NOT your Gmail password) | 🟢 OPTIONAL |

> Without SMTP creds, verification emails fall back to `_dev_log()` — token is printed in Render logs. Users can still verify via Render log token. Fill these to send real verification emails.

---

## Email — Premium Alerts (Resend)

| Variable | Value | Priority |
|----------|-------|----------|
| `RESEND_API_KEY` | `re_...` (from resend.com) | 🟢 OPTIONAL |
| `RESEND_FROM_EMAIL` | `alerts@safeearth.tech` | 🟢 OPTIONAL |

> Without Resend creds, premium alert emails fall back to `_dev_log()`. Fill after verifying `safeearth.tech` domain in Resend dashboard.

---

## Summary: Minimum Set to Go Live

These 8 variables are the absolute minimum for a working v1 deployment:

```
DATABASE_URL          = postgresql+asyncpg://...  (Neon direct URL)
SECRET_KEY            = <hex32>
FRONTEND_URL          = https://safeearth.tech
CORS_ORIGINS          = https://safeearth.tech,https://www.safeearth.tech
HUGGINGFACE_REPO_ID   = <username>/safeearth-models
HUGGINGFACE_TOKEN     = hf_...
PAYMENT_PROVIDER      = mock
PAYMENT_WEBHOOK_SECRET = <hex32>
```

Add `GROQ_API_KEY` for live AI recommendations. Add SMTP/Resend when ready for real emails.

---

## After Deploy — Verify

```bash
# Should return: {"status":"ok","models_loaded":true,"rag_loaded":true_or_false}
curl https://api.safeearth.tech/api/v1/health

# Run the full smoke test
py -3.12 docs/smoke_production.py --base-url https://api.safeearth.tech
```
