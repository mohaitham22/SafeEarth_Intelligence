# SafeEarth Intelligence — TODO

> Formal task list. Companion to PROGRESS.md (session log) and ARCHITECTURE.md (design).
> Created 2026-06-05. Check items off as they ship; move detail to PROGRESS.md.

## Done — premium "Alerts": subscription-driven forecast + email + PDF (2026-06-05)

The five premium capabilities, consolidated into the dashboard **Alerts** tab. No DB migration, no new
table. Decisions: forecast is **subscription-driven**; email is **auto on generate** (frontend-orchestrated).

- [x] **Premium Alerts = 30-day forecast WITH probabilities for a chosen (subscribed) region** —
      `components/AlertsForecastPanel.tsx` (region dropdown + type → `forecast30d` → calendar + per-day
      probability); `AlertsTab` is role-aware via `meetsRole`.
- [x] **Send HTML email alerts (reuse the hardened email pipeline)** — new premium
      `POST /alerts/email-forecast` (`alert_service.email_latest_forecast` → `send_premium_alert_email` +
      `PremiumEmailLog`); auto-fired by the panel after each Generate. Dev-logs until Resend creds set.
- [x] **Download PDF reports** — "Download PDF" button → `endpoints.predictions.forecastPdf()` (blob) →
      existing `GET /predictions/forecast-30d/pdf`; both it and the email now share
      `predictor_service.get_latest_forecast_days`.
- [x] **Subscribe up to 10 regions (role layer)** — verified: `subscription_limit("premium")==10` enforced
      in `create_subscription`; the new region dropdown surfaces all of them. (No new code.)
- [x] **Upgrade via checkout flow** — verified: non-premium Alerts tab shows an Upgrade CTA → `/pricing`
      (existing `CheckoutButton` → `POST /premium/checkout` → mock-checkout). (No new code.)

## Done — subscriptions: confirm · alerts · limits · CSV (2026-06-05)

- [x] **Clear unsubscribe confirmation** — dashboard modal naming the region + public `/unsubscribe`
      page now looks up the region and requires a confirm click (no more silent auto-delete on load).
      New public `GET /subscriptions/lookup/{token}`; `DELETE` returns `region_name`.
- [x] **Subscriptions generate real alerts** — `dispatch_alerts` runs the model per region
      (`alert_service._evaluate_subscription` + `ml/geo.continent_from_latlon`), by frequency: weekly
      digest always sends; immediate only on High/Critical. Degrade-not-fail.
- [x] **Region limits subscriber 8 / premium 10** — `_SUBSCRIPTION_LIMITS` in `core/permissions.py`;
      frontend mirrors via `subscriptionLimit()`.
- [x] **"Download data" for subscriptions** — Export CSV in `SubscriptionsTab`.

## Done — dashboard predictor fixes (2026-06-05)

- [x] **Location actually drives predictions** — un-froze `region_enc` / `country_enc` /
      `historical_freq` at inference via `_resolve_location_features` in `backend/ml/predictor.py`
      (no retraining; encoders already in the bundle).
- [x] **Disaster Type Predictor is location-aware** — `ClassifyRequest` gained optional `country`;
      `run_classify` + the `/classify` route + the frontend card now send it.
- [x] **Risk Level Classifier ↔ 30-day Forecast reconciled** — confirmed both use one shared
      `predict()`; `Risk(current month, day-0) == Forecast day-0`; both clearly labelled
      (`card3.reconcileNote`, `forecast.reconcileNote`).
- [x] **Consistent month/season input** — shared `frontend/components/MonthSelect.tsx` on all three
      single-shot cards; forecast auto-derives per-day months.
- [x] **Magnitude removed from the Risk Level Classifier** — dropped from `PredictRequest`
      (schema + TS type), the predict route/call, and the orphaned `form.magnitude.*` strings.
- [x] **"Download data" (CSV)** — `frontend/lib/csv.ts` + buttons on each result, the 30-day forecast,
      and the Predictions History tab (client-side, no backend).

## Done — earlier phases (see PROGRESS.md for detail)

- [x] Country → fixed lat/lon picker (`countries.json`, `GET /regions/countries`, `CountrySelect`).
- [x] Type-aware + plausible impact (`_blend_and_constrain_impact`, `deaths ≤ injured ≤ affected`).
- [x] Central permission layer (`backend/core/permissions.py`; `free` = alias for `subscriber`).
- [x] Email hardening + `POST /auth/resend-verification`.
- [x] Home page role-gating + `ads` table + `GET /ads`.
- [x] Risk map: discrete markers + `riskScale.ts` single source + click-to-predict.
- [x] Analytics + timeseries insight/filter fixes.

## Done — full admin panel (2026-06-05)

- [x] **Admin CRUD endpoints** — `GET /admin/users` + `PATCH /admin/users/{id}` now live and tested.
      Frontend admin Users tab no longer shows the "not implemented" banner.
- [x] **Studio editor for `ads`** — full CRUD (`GET/POST/PATCH/DELETE /admin/ads` + image upload to
      `backend/static/ads/`). Frontend Studio tab built with create form + inline edit + soft-delete.
- [x] **Site stats dashboard** — `GET /admin/stats` with 6 categories; frontend Overview tab with stat cards.
- [x] **Model stats from API** — `GET /admin/model-stats` reads `backend/ml/model_info.py`; frontend
      Model Stats tab replaces hardcoded values with live API data.
- [x] **Monthly alert digest** — `POST /alerts/monthly-dispatch` (dual-auth) + `n8n/monthly_digest.json`
      (cron `0 8 1 * *`). Emails full alert table to all premium users who had ≥1 alert that month.
- [x] **Dispatch preview** — `GET /admin/alerts/dispatch-preview` dry-run; shown in frontend Alerts tab.
- [x] **ADMIN_API.md** — full developer reference at repo root.

## Open / deferred

- [x] **Subscription limit reconciliation** — resolved to subscriber 8 / premium 10
      (`_SUBSCRIPTION_LIMITS` in `backend/core/permissions.py`).
- [ ] **Verification-token expiry** — template says "24 hours" but it isn't enforced (needs a DB column).
- [ ] **Fill real SMTP / Resend / Groq creds** in production `.env` (ops task; all degrade-not-fail today).
- [ ] **Real payment provider** (Stripe / Paymob) replacing `MockPaymentService` (1-file swap).
- [ ] **Remove unused `leaflet.heat`** dep (`npm uninstall leaflet.heat`).
- [ ] *(optional)* Lock the un-freeze in with a real-model regression test — current suite mocks
      `predict()`, so the frozen-feature bug couldn't be caught by tests; only the REPL check covers it.

## Known limitations (by design, not bugs)

- Country predictions run at the country **centroid** (impact comes from the EM-DAT country tier, which is
  per-country accurate; the lat/lon-driven classifier sees the country centre).
- The 30-day forecast is a **monthly/seasonal projection**, not a true daily forecast (no live weather;
  `day_offset` is a dead model feature, so days within one calendar month share the same risk).
