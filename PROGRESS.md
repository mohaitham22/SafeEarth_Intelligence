# SafeEarth Intelligence — Phase Progress Log

> Tracks what was actually built, session by session. Companion to CLAUDE.md (authoritative session
> log) and ARCHITECTURE.md (system design). This file is for **quick orientation at the start of a
> new session** — scan it before writing any code.
>
> Last updated: 2026-06-06

---

## Current state at end of this phase (audit + bug-fix — 2026-06-06)

- **Backend tests:** 189 / 189 passing (`py -3.12 -m pytest`)
- **Frontend routes:** 17 / 17 prerendered static (clean `npm run build`)
- **DB tables:** 9 — unchanged
- **DB migrations at Alembic head:** `b7c1e9d4a2f0_add_ads_table`
- **Precomputed JSON files:** 9 (`data/generated/`) — unchanged
- **API/contract changes this phase:** None (bug-fix only)

---

## What was built this phase (audit + bug-fix — 2026-06-06)

No new features. This was a pre-release audit pass: default-value audit, magnitude-removal
confirmation, full subagent diff review, test suite run, and one critical bug fixed.

### Audit findings (all items reviewed)

**Default values — all good:**
- Default country: USA (from `data/generated/countries.json` → `"default"`). Realistic. ✅
- Default disaster type: "Flood" on every form (ClassifyCard, PredictionForm, ForecastForm,
  AlertsForecastPanel, HomePremiumForecast). ✅
- Default month: `0` = current month on all single-shot cards via `MonthSelect`. ✅
- Default year: `new Date().getFullYear()` on ClassifyCard + ImpactCard. ✅
- Submit buttons disabled until `CountrySelect` seeds a default location (after API load, the form
  is immediately submittable — no blank required fields). ✅

**Magnitude removal — correct scope:**
- Removed from `PredictRequest` schema, the predict route, and `run_prediction_for_request`. ✅
- `ClassifyRequest.magnitude` is intentionally retained — the classify endpoint can accept a
  Richter value; the ML features `has_magnitude`/`mag_value` are real model inputs used with
  `magnitude=None` on the no-magnitude path. Not dead code. ✅
- No `form.magnitude.*` keys remain in `strings.ts`. ✅
- No magnitude input visible in any frontend form. ✅

**Full diff review (subagent) — all TODO.md items confirmed implemented:**
- Premium Alerts panel (`AlertsForecastPanel`) with region dropdown, Generate, auto-email, PDF. ✅
- Subscriptions: `GET /subscriptions/lookup/{token}` + confirmation modal + real alert dispatch. ✅
- Region limits: subscriber 8 / premium 10 in `core/permissions.py`. ✅
- Location-aware predictions: `_resolve_location_features` unfreezes region/country/frequency. ✅
- CSV exports on all cards + history + subscriptions via `lib/csv.ts`. ✅
- `MonthSelect` shared across all 3 single-shot cards. ✅
- Admin 6-tab panel — all backend endpoints live and tested. ✅
- `dispatch_alerts` routes by frequency and runs the model per region (`_evaluate_subscription`). ✅
- `backend/ml/geo.py` with `continent_from_latlon` used by alert dispatch. ✅
- `leaflet.heat` not imported in `RiskMap.tsx` (package still in `package.json` — minor). ✅

### Bug fixed

**Critical — `NameError: batch_id` in forecast PDF download**
- File: `backend/routers/predictions.py`, `forecast_30d_pdf` function.
- Root cause: `Content-Disposition` header referenced `batch_id` which was never assigned in the
  function body. `days[0].forecast_batch_id` existed but was never extracted.
- Impact: Any premium user clicking "Download PDF" on the 30-day forecast page would get a 500.
  The existing test suite only covers single-prediction PDF; forecast-30d PDF was untested.
- Fix: Added `batch_id = days[0].forecast_batch_id` before the `StreamingResponse` call.

### Minor string fix

- `frontend/lib/strings.ts` key `"subs.add.region.ph"`: changed `"e.g. Cairo, Egypt"` →
  `"e.g. New York, Cairo"` (leftover from before the country-centroid refactor).

### Architectural notes

- `magnitude` in `ClassifyRequest` / `predictor.classify_all_types()` / `predict()` signature is
  **not dead code** — it feeds the `has_magnitude` and `mag_value` model features. The classify
  card doesn't expose a UI input for it now, but the API contract is correct.
- `predictor_service.get_latest_forecast_days` is already the single source for "most recent batch"
  (used by both `forecast_30d_pdf` and `email-forecast`). No inline re-queries elsewhere.
- `leaflet.heat` is unused at runtime (RiskMap switched to `CircleMarker`s). Safe to run
  `npm uninstall leaflet.heat` at any time — it is the only open TODO.md item left.

### What next phase needs to know

- 189/189 tests pass; no known code-level bugs remain.
- The 30-day forecast PDF was broken at runtime (silent in CI); fixed in this session.
- All open TODO.md items are either resolved or explicitly deferred (SMTP/Resend/Groq creds,
  real payment provider, verification-token expiry, `leaflet.heat` uninstall).

---

## What was built this phase (full admin panel — 2026-06-05)

Delivered the complete admin back-end + rebuilt the admin frontend with 6 tabs. No DB migration; no new table.

### Backend

**New files:**
- `backend/schemas/admin.py` — `AdminUserItem`, `AdminUsersResponse`, `PatchUserRequest`, `SiteStatsResponse`, `ModelStatsResponse`, `DispatchPreviewResponse`, and all nested stat schemas.
- `backend/schemas/monthly_dispatch.py` — `MonthlyDispatchRequest` (both-or-neither validator), `MonthlyDispatchResponse`.
- `backend/ml/model_info.py` — v4.2 constants (`MODEL_VERSION`, `MACRO_F1`, `WEIGHTED_F1`, `ACCURACY`, `FEATURE_COUNT`, `ENSEMBLE`, `PER_CLASS_F1`). Single source of truth; the model-stats endpoint reads from here.
- `backend/services/admin_service.py` — `list_users` (paginated + filterable), `update_user` (self-role-change guard), `get_site_stats` (6 category scalar queries), `get_dispatch_preview`.
- `backend/tests/test_admin.py` — 11 tests covering user CRUD, stats, model-stats, and Studio ads.
- `n8n/monthly_digest.json` — importable n8n workflow (cron `0 8 1 * *`).
- `ADMIN_API.md` — full developer reference.

**Modified files:**
- `backend/schemas/ad.py` — added `AdAdminItem` (includes `is_active`, `created_at`), `AdCreate`, `AdUpdate`.
- `backend/services/ad_service.py` — added `list_all_ads`, `create_ad`, `update_ad`, `deactivate_ad`, `upload_ad_image` (validates MIME type, saves to `backend/static/ads/`, returns URL).
- `backend/services/alert_service.py` — added `dispatch_monthly_digest` (groups alerts by user for the period, fans out to premium users as BackgroundTasks) + `_send_monthly_digest_background` helper.
- `backend/services/email_service.py` — added `send_monthly_digest_email` (Resend, degrade-not-fail, renders `monthly_digest.html`).
- `backend/templates/emails/monthly_digest.html` — new Jinja2 template: blue header, full alert table (date/region/type/severity/message), CTA button.
- `backend/routers/admin.py` — completely rebuilt: added `GET /admin/users`, `PATCH /admin/users/{id}`, `GET /admin/stats`, `GET /admin/model-stats`, `GET /admin/alerts/dispatch-preview`, `GET/POST/PATCH/DELETE /admin/ads`, `POST /admin/ads/{id}/image`; removed `/admin/stub`.
- `backend/routers/alerts.py` — added `POST /alerts/monthly-dispatch` (reuses `require_dispatch_auth`).
- `backend/main.py` — mounts `StaticFiles` at `/static` for `backend/static/`.
- `backend/tests/test_alerts.py` — +3 monthly-dispatch tests (now 16 in this file).

### Frontend

- `frontend/types/admin.ts` — extended with `SiteStats`, `ModelStats`, `MonthlyDispatch*`, `DispatchPreviewResponse`, `AdAdminItem`, `AdCreate`, `AdUpdate`.
- `frontend/lib/endpoints.ts` — added `admin.stats`, `admin.modelStats`, `admin.dispatchPreview`, `admin.allAds`, `admin.createAd`, `admin.updateAd`, `admin.deleteAd`, `alerts.monthlyDispatch`.
- `frontend/lib/strings.ts` — new `admin.overview.*` (11 keys), `admin.studio.*` (18 keys), `admin.alerts.*` (16 keys); updated tab keys from 5 → 6.
- `frontend/app/(protected)/admin/page.tsx` — full 6-tab rebuild: **Overview** (stat cards from API), **Users** (paginated table + inline role editor), **Studio** (ad CRUD + create form), **Model Stats** (live `/admin/model-stats` + per-class F1 table with bars), **Alerts** (dispatch preview + weekly + monthly digest), **Payments** (ComingSoon).

### Architectural decisions
- `model_info.py` is the single source for ML constants — both `GET /admin/model-stats` and any future training-report pages read from there. No hardcoded values in the router.
- Monthly digest email uses the same `BackgroundTasks` + `AsyncSessionLocal` pattern as `dispatch_critical_alert` (non-blocking, own DB session per recipient).
- `upload_ad_image` derives the public URL from `request.base_url` (not a hardcoded env var), so local dev and production both get the right host.
- Studio uses soft-delete (`is_active=False`) — ads are never hard-deleted, matching the v1 "never hard-delete" rule.

### What next phase needs to know
- `GET /admin/users` and `PATCH /admin/users/{id}` are **live and tested** — admin Users tab no longer shows the "not implemented" banner.
- `backend/static/ads/` is tracked via a `.gitkeep` file; uploaded images live there at runtime (gitignored in `.gitignore`).
- Monthly digest emails still **dev-log** until `RESEND_API_KEY` is set in `.env` (same degrade-not-fail pattern as all other emails).
- Sub limits are still at 8/unlimited — the one constant in `permissions.py` to reconcile.

### Tests added (+14 → 189)
- `test_admin.py`: 11 new tests (user list/filter/patch/self-guard, stats keys, model-stats values, ad create/public/soft-delete).
- `test_alerts.py`: +3 (monthly dispatch requires auth, future month → 400, dispatches to premium users).

---

## What was built this phase (premium "Alerts": subscription-driven forecast + email + PDF — 2026-06-05)

Consolidated the **premium** experience into the dashboard **Alerts** tab. **No DB migration, no new
table.** Role decisions stay in the permission helpers; mostly wires existing machinery (forecast engine,
hardened email pipeline, ReportLab PDF, 10-region limit, checkout) into one premium surface.

### Confirmed product decisions (asked the user)
- **Country source = subscribed regions.** The premium alert forecast is driven by the user's saved region
  subscriptions (a region dropdown over their up-to-10 regions), like the home premium widget — not a free
  country picker. Ties Alerts to subscriptions (req 4).
- **Email trigger = auto on generate.** Generating the alert forecast also sends the premium HTML email
  (one deliberate "Generate" click → one forecast → one email). Orchestrated by the Alerts panel on the
  **frontend** so the shared `forecast-30d` endpoint and the auto-running home widget are NOT affected.

### What it does now
A premium user opens **Alerts** → picks a subscribed region + disaster type → **Generate** → sees a 30-day
alert forecast **with probabilities** (5×6 calendar + per-day detail). The same action emails them the
highest-risk-day summary (premium `premium_alert.html`) and offers a **Download PDF**. Non-premium users see
an **Upgrade** CTA (existing `/pricing` checkout flow) above the unchanged in-app alert-history table.

### Backend (files changed)
- `backend/services/predictor_service.py` — new `get_latest_forecast_days(*, db, user_id)`: the user's most
  recent forecast batch, ordered by `forecast_day_offset` (or `[]`). **Single source** for the "most recent
  batch" query.
- `backend/routers/predictions.py` — `forecast_30d_pdf` refactored to call that helper (behaviour
  unchanged; removes the duplicated inline batch query).
- `backend/services/alert_service.py` — new `email_latest_forecast(*, db, user)`: reads the latest batch
  (404 if none), picks the peak day (max probability), looks up the matching active subscription's
  `unsubscribe_token`, builds the `premium_alert.html` context, sends via `email_service.send_premium_alert_email`
  (degrade-not-fail), writes a `PremiumEmailLog` (`alert_id=None`, `email_type=custom`), commits, returns a summary.
- `backend/schemas/alert.py` — new `EmailForecastResponse(sent, message_id, to, peak_day, disaster_type,
  severity_level, region_name)`.
- `backend/routers/alerts.py` — new `POST /alerts/email-forecast` (`require_premium`) → thin call to the service.
- `backend/tests/test_alerts.py` — +3 (now 16 in this file): email-forecast requires premium (403), no
  forecast → 404, premium + seeded batch → 200 + `PremiumEmailLog` row (`custom`/`sent`) + correct peak day.

### API created
| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/v1/alerts/email-forecast` | Premium | Email the user their most recent forecast's highest-risk day as the premium HTML alert; logs a `PremiumEmailLog`. 404 if no forecast yet. |

### Frontend (files changed)
- `frontend/components/AlertsForecastPanel.tsx` (new, premium) — region dropdown over subscriptions +
  disaster-type select + **Generate** → `forecast30d` (region_name=country=region, continent derived via
  `lib/geo`) → `ForecastCalendar` + per-day probability/`SeverityBadge`, THEN auto-calls
  `alerts.emailForecast()` (status line: emailed / dev-mode / failed) + **Download PDF**
  (`predictions.forecastPdf` blob). No subscriptions → prompt to add a region. Reuses `ForecastCalendar`,
  `SeverityBadge`, `continentFromLatLon`.
- `frontend/app/(protected)/dashboard/page.tsx` — `AlertsTab` is role-aware (`meetsRole`): premium/admin →
  `AlertsForecastPanel`; subscriber → `AlertsUpgradeCta` (→ `/pricing`); in-app history table stays for all.
- `frontend/lib/endpoints.ts` — `predictions.forecastPdf()` (blob) + `alerts.emailForecast()`.
- `frontend/types/alert.ts` — `EmailForecastResponse`.
- `frontend/lib/strings.ts` — new `alerts.premium.*` / `alerts.email.*` / `alerts.pdf.*` / `alerts.upgrade.*`
  keys (zero hardcoded UI text).

### Req 4 & 5 — verified, no new code
- **10 regions:** already enforced (`core/permissions.py::subscription_limit("premium")==10`,
  `subscription_service.create_subscription`, frontend `subscriptionLimit`); the new region dropdown lists
  all of them. Covered by existing `test_subscriptions.py` premium-limit-10 test.
- **Checkout:** unchanged; the non-premium Alerts CTA links to `/pricing` (existing `CheckoutButton` flow).

### Architectural decisions
- **Auto-email lives on the frontend, not in `forecast-30d`.** Putting auto-email in the shared forecast
  endpoint would spam the auto-running home widget. The Alerts panel calls `forecast30d` then
  `email-forecast` (which re-reads the just-persisted batch) — one email per deliberate Generate click.
- **`email-forecast` reads the latest batch instead of trusting client input.** Mirrors the forecast-PDF
  endpoint; both now share `get_latest_forecast_days`. The email/PDF reference the same batch the user just
  generated.
- **`PremiumEmailLog` written with `alert_id=None`, `email_type=custom`.** This is a user-initiated email,
  not tied to a dispatch `Alert` row (whose `subscription_id` is NOT nullable); `PremiumEmailLog.alert_id`
  IS nullable, so the audit log row is still written.
- **Honest dev-mode status.** When `send_premium_alert_email` returns a `dev-fallback*` sentinel (no Resend
  creds), the UI says "logged, not sent" rather than claiming delivery.

### Anything the next phase needs to know
- `predictor_service.get_latest_forecast_days` is the single source for "most recent forecast batch" — use
  it (forecast PDF + email-forecast already do); don't re-inline the query.
- The premium email path still **dev-logs** to `backend/.email_dev.log` until `RESEND_API_KEY` +
  `RESEND_FROM_EMAIL` are set in `.env` (degrade-not-fail). `email-forecast` returns `sent:true` with a
  `dev-fallback*` `message_id` in that mode — the UI surfaces it as dev-mode.
- The premium Alerts forecast is country-centroid-level like every other prediction form (known limitation).

### Tests added (+3 → 175)
- `test_alerts.py`: `test_email_forecast_requires_premium` (403), `test_email_forecast_no_forecast_returns_404`,
  `test_email_forecast_sends_and_logs` (200 + log row + peak day).

---

## Previous phase (subscriptions: confirm unsubscribe · wire alerts · limits · CSV — 2026-06-05)

Four subscription/alerting fixes. **No DB migration.** Role decisions stay in the permission helpers.

### A. Clear "unsubscribe from <region>?" confirmation (dashboard + email page)
**Was:** the dashboard had a weak inline "Remove?" that didn't name the region; the public
`/unsubscribe?token=` email page **auto-deleted on page load** (silent, and exposed to email-client link
prefetch).
**Fix:**
- Backend: `subscription_service.get_by_token` (read-only) + `SubscriptionLookupResponse` + public
  `GET /subscriptions/lookup/{token}` (404 if unknown; distinct path → no wildcard shadowing).
  `DELETE /subscriptions/{token}` now returns `{"status":"unsubscribed","region_name":...}` (kept the
  `status` key).
- Frontend: [unsubscribe/page.tsx](frontend/app/(public)/unsubscribe/page.tsx) now **looks up first** →
  shows "Are you sure you want to unsubscribe from **{region}**?" with Unsubscribe / Keep buttons (states:
  loading → confirm / already-inactive / success / error). Dashboard `SubscriptionsTab` got a real modal
  (`ConfirmUnsubscribeModal`) naming the region. `endpoints.subscriptions.lookup` added.

### B. Subscriptions wired into the alerting pipeline (run the model per region)
**Was:** `dispatch_critical_alert` needs a `region_name` the dashboard no longer sends (skips), and
`dispatch_alerts` created Alert rows with `disaster_type=None`/`severity=None` — never ran the model. So a
subscribed region produced only empty/generic alerts.
**Fix (decision: by frequency):** `alert_service._evaluate_subscription(sub)` runs
`predictor.classify_all_types` at the subscription's lat/lon (continent via new
[backend/ml/geo.py](backend/ml/geo.py) `continent_from_latlon`) → top disaster type + probability →
`predictor.probability_to_severity` (new public wrapper). **Degrade-not-fail** (returns `None` if models
aren't loaded / on error → generic fallback, so cold starts and tests still work). `dispatch_alerts` now:
routes by frequency (weekly_digest → weekly subs; high_risk_immediate → immediate subs); **weekly digest
always sends** the region's computed risk; **immediate only fires when computed severity ∈ {High,
Critical}**. Alerts now carry a real disaster type + severity + message. `dispatch_critical_alert` is left
as the secondary path (still fires when a prediction carries a matching region_name).

### C. Region limits — subscriber 8 / premium 10 (role layer)
`_SUBSCRIPTION_LIMITS["premium"]` 1_000_000 → **10** in [backend/core/permissions.py](backend/core/permissions.py)
(subscriber stays 8; admin stays unbounded). Frontend [lib/permissions.ts](frontend/lib/permissions.ts)
gained `subscriptionLimit(role)`; `SubscriptionsTab` now reads it instead of the inline `Infinity : 8`.
The `subscription_limit()` helper is the single source — `create_subscription` already enforces it.

### D. "Download data" (CSV) for subscriptions
`SubscriptionsTab` got an "Export CSV" button (reuses `DownloadCsvButton` + `lib/csv.ts`): region_name,
latitude, longitude, alert_frequency, created_at.

### Tests added (+7 → 172)
- `test_subscriptions.py`: lookup returns region/active, lookup 404, DELETE returns region_name, premium
  limit enforced at 10.
- `test_alerts.py`: weekly dispatch carries model-evaluated type+severity; immediate skips Low; immediate
  fires on Critical. (Existing dispatch test stays green via the degrade fallback.)

---

## Previous phase (dashboard predictor fixes — 2026-06-05)

Five prediction-flow fixes. **No retraining, no DB migration, no new generated files.** All inference
paths share one helper so they can't drift.

### A. Location now actually drives predictions (the real "continent does nothing" bug)
**Root cause:** continent *did* feed the model, but `backend/ml/predictor.py` hardcoded three OTHER
trained location features at inference — `region_enc=0`, `country_enc=0`, `historical_freq=629` (global
avg) — even though the bundle already ships `le_region`, `le_country`, and `region_freq_map`. So picking
a different country only nudged lat/lon; region/country/frequency were frozen, making location feel inert.
**Fix:** new `_resolve_location_features(continent, country, region)` resolves all four categorical /
frequency features from the selected country (region via `emdat_lookup.COUNTRY_TO_REGION`, frequency via
`region_freq_map`, unseen values → 0 / global avg). Used by `predict()` and `_build_feature_vector()` (so
`classify_all_types` + `predict_impact` inherit it). `ClassifyRequest` gained an optional `country` (the
only request that lacked it); `run_classify` + the `/classify` route forward it. Verified: same continent,
different country now diverges (US → Wildfire, Japan / Bangladesh → Flood).

### B. Risk Level Classifier vs 30-day Forecast reconciled (not different models)
**Diagnosis:** both already call the same `predictor.predict()` via `run_prediction_for_request`. They
diverged only on the **month** feature (Risk used the user's chosen season; Forecast uses each upcoming
day's calendar month) — and `day_offset` is effectively a dead feature, so within one calendar month every
forecast day is identical (a step function, which looked less "reliable" than the single Risk number).
**Fix (label + reconcile — the request's second branch, since they already share a service):** with the
shared month input defaulting to "Current month", `Risk(current month, day-0) == Forecast day-0` for the
same country/type (verified, exact match). Added clear labels — `card3.reconcileNote` on the Risk card and
`forecast.reconcileNote` on the forecast page — explaining each computes a different thing and how Day 1
lines up. No fabricated daily variation (honest about there being no live weather feed).

### C. Consistent month/season input across all predictors (req 3)
New `frontend/components/MonthSelect.tsx` — one dropdown ("Current month" + Jan–Dec, emits `0` / `1-12`),
now used by all three single-shot cards (Disaster Type / Impact / Risk), replacing three separate
free-text season `<Field>`s and their ad-hoc string parsing. The 30-day forecast derives each day's month
automatically (documented in the reconcile note). Backend `_parse_season` already accepts int month / 0.

### D. Magnitude removed from the Risk Level Classifier (full cleanup, req 4)
The Risk UI already sent `magnitude: null`. Removed the orphaned `form.magnitude.*` strings, dropped
`magnitude` from `PredictRequest` (schema + TS type) and the predict route/call. `predict()` keeps the
param internally (always `has_magnitude=0` on this path); `run_prediction_for_request.magnitude` now
defaults to `None`. `ClassifyRequest.magnitude` is left as an unused optional (out of scope).

### E. "Download data" — client-side CSV export (req 5)
New `frontend/lib/csv.ts` (`toCsv` RFC-4180 quoting + `downloadCsv` Blob with UTF-8 BOM). A "Download CSV"
button on each result — Disaster Type (ranked rows), Impact (metrics row), Risk (full prediction with SHAP
top-3 flattened to columns) — plus "Download 30-day CSV" on the forecast and "Export CSV" on the
Predictions History tab. Entirely client-side; no backend endpoint added.

### Files changed
- Backend: `backend/ml/predictor.py`, `backend/schemas/prediction.py`, `backend/routers/predictions.py`,
  `backend/services/predictor_service.py`
- Frontend (new): `frontend/components/MonthSelect.tsx`, `frontend/lib/csv.ts`
- Frontend (edited): `frontend/app/(protected)/dashboard/page.tsx`,
  `frontend/app/(protected)/dashboard/forecast/page.tsx`, `frontend/types/prediction.ts`,
  `frontend/lib/strings.ts`
- No new tests — changes are covered by the existing mocked suite (165/165 green); the un-freeze and
  Risk↔Forecast reconciliation were validated by a direct-model REPL check.

---

## Previous phase (location picker + type-aware impact — 2026-06-05)

Three real data-logic fixes in the prediction/forecast flow.

### A. Impact now varies by disaster type + is always plausible

**Root cause:** the dashboard "Risk" card (`POST /predictions/predict`) and the 30-day forecast
(`POST /predictions/forecast-30d`) both run `predictor.predict()`, which computed
deaths/injured/affected/damage from the **raw ML regressors only**. Those regressors take the 16
geo/temporal features — `disaster_type` is **not** one of them — so Flood and Earthquake at the same
lat/lon returned identical numbers. (`predict_impact()`, used by the separate `/impact` card, already
blended EM-DAT type-specific medians; `predict()` never got that fix.) Nothing enforced
`deaths ≤ injured ≤ affected` (the cited Egypt-flood case had deaths=2 > injured=1).

**Fix — `backend/ml/predictor.py`:** both inference paths now share one helper.
- `_blend_and_constrain_impact(disaster_type, ml_vals, emdat_stats)` — coverage-weighted blend
  (deaths/affected 70 % EM-DAT, injuries 30 %, damage 35 %) of the location-aware ML regressors with the
  disaster-type-specific EM-DAT medians, then `_apply_plausibility`.
- `_apply_plausibility(...)` — per-type floors (`_IMPACT_RATIOS`: injured/death + affected/death) nudge
  implausible values, then a hard `deaths ≤ injured ≤ affected` ordering clamp is applied last as the
  guarantee. Zeros are preserved (Drought with 0 deaths keeps EM-DAT-driven affected).
- `predict()` reuses the EM-DAT lookup it already ran (medians were being discarded) → blend → constrain.
- `predict_impact()` swapped its inline blend for the same helper. The forecast inherits the fix.

**Verified (REPL, US centroid):** Flood vs Earthquake now differ (e.g. deaths 6/5, affected 3000/221,
damage 70.2M/10.5M); ordering holds for all 8 types incl. Drought (0 deaths → 0 injured, large affected).

### B. Country → fixed lat/lon lookup table (`countries.json`)

**Files changed:**
- `scripts/generate_emdat_stats.py` — embedded `_ISO3_CENTROIDS` (curated ISO3 country centroids) +
  `build_countries()`; joins the CSV `Country` + `ISO` (clean ISO3, 100 % coverage) + `Continent` to
  the centroid table and writes `data/generated/countries.json` (9th generated file, 211 countries
  across 5 continents). `name` is the **exact EM-DAT country string** (so the country-tier impact lookup
  hits — verified every name matches an `emdat_stats.json` `by_country` key); `label` is cleaned for
  display; `default` = `United States of America (the)` (1,087 events — most data-rich).
  *Why not event-median centroids:* only ~2.6k of 16k rows have valid coords and ~half the countries
  lack ≥3 — they'd be jumpy and incomplete.
- `backend/ml/emdat_lookup.py` — `COUNTRIES` global + `get_countries()`; `countries.json` added to
  `load_all()` (now loads 9 files).
- `backend/schemas/regions.py` — `CountryEntry`, `CountryDefault`, `CountriesResponse`.
- `backend/routers/regions.py` — **`GET /regions/countries`** (public, `Cache-Control: max-age=3600`).

### C. Frontend — all prediction forms are now country-only (read-only lat/lon)

Per the confirmed scope, **every** prediction form is country-driven; manual lat/lon entry is gone and
the `/map → /dashboard?lat=&lon=` prefill is dropped.
- New `frontend/components/CountrySelect.tsx` — fetches `/regions/countries` once, renders
  continent → country `<select>`s, emits `{continent, country (EM-DAT name), label, lat, lon}`, shows
  the resolved coordinates read-only. Seeds the parent with `default` on load.
- `frontend/app/(protected)/dashboard/forecast/page.tsx` — `ForecastForm` uses `CountrySelect`; removed
  the lat/lon + free-text country/continent `Field`s.
- `frontend/app/(protected)/dashboard/page.tsx` — `ClassifyCard`, `ImpactCard`, `PredictionForm` all use
  `CountrySelect`; removed the `useSearchParams()` `?lat=&lon=` prefill (and the now-unneeded `Suspense`).
- `frontend/components/RiskMap.tsx` — "Open full result" now links to `/dashboard` (no coord params); the
  inline click-predict popup is unchanged.
- `frontend/types/regions.ts` + `frontend/lib/endpoints.ts` — `CountriesResponse`/`CountryEntry` +
  `endpoints.regions.countries()`.
- `frontend/lib/strings.ts` — new `location.*` keys; removed orphaned `form.country.*` /
  `form.continent.*` / `card1.continent.*` / `card2.continent.*` / `card2.country.*` keys.

### D. Coverage notes (req 6) — kept, reworded

The "Injured/Damage" coverage notes under `PredictionResultCard` are a documented Feature-1 transparency
requirement and genuinely disclose that injuries are recorded for only ~26 % of historical events and
damage ~33 %. **Decision: keep, not remove.** Reworded `result.coverage.injuries` / `result.coverage.damage`
to make the "low-confidence due to sparse historical reporting" meaning explicit.

### Tests added this phase
- `backend/tests/test_impact_plausibility.py` (14 cases) — ordering guarantee across all 8 types, the
  Egypt-flood repair, zeros preserved, Drought affected dwarfs deaths, floors only raise, blend differs
  by type, empty-EM-DAT safety.
- `backend/tests/test_regions.py` — `test_countries_returns_picker_table` (5 continents, default,
  in-range centroids, every `name` ∈ EM-DAT `by_country`, sorted by n_events).
- `scripts/tests/test_generation.py` — `countries.json` structure + entry validity / name-alignment.

---

## Previous phase (v2 foundation + UI polish)

### A. Central permission layer

**Why:** Role checks were scattered across 5+ files with inline `role == "admin"` comparisons. One
change required 5 edits; there was no single source of truth.

**Files created:**
- `backend/core/permissions.py` — `Feature` enum, `ROLE_RANK`, `can(user, feature)`,
  `meets_role`, `subscription_limit(role)`, `normalize_role`. This is the **only place** that
  decides what each role can do.

**Files refactored (behaviour unchanged):**
- `backend/core/deps.py` — `require_admin`, `require_premium`, `require_subscriber` (now shared,
  not duplicated per-router), new `require(Feature.X)` dependency factory
- `backend/routers/predictions.py`, `backend/routers/premium.py` — deleted the two duplicate
  inline `require_subscriber` functions
- `backend/services/alert_service.py` — `role in ("premium","admin")` → `can(user, Feature.RECEIVE_EMAIL_ALERTS)`
- `backend/services/subscription_service.py` — local `MAX_SUBSCRIPTIONS` dict → `permissions.subscription_limit()`

**Frontend mirror (UX only — not a security control):**
- `frontend/lib/permissions.ts` — `can`, `meetsRole`, `isAdmin` used by `Nav.tsx`,
  `middleware.ts`, `CheckoutButton.tsx`, `admin/page.tsx`

**Tests added:** `backend/tests/test_permissions.py` (8 tests, incl. decisive `free == subscriber` assertion)

---

### B. Sign-up + email verification

**What was wrong:** `register_user` had a leftover Phase-6 TODO and a bare `print()`. Emails never
actually sent because creds were empty — AND there was no timeout, no retry, and failures were
silent.

**Files changed:**
- `backend/services/auth_service.py` — removed TODO/print; added `resend_verification(db, email)`
- `backend/schemas/auth.py` — added `ResendVerification`, `MessageResponse`
- `backend/routers/auth.py` — added `POST /auth/resend-verification` (generic 200, never leaks
  whether an account exists)
- `backend/services/email_service.py` — SMTP connection `timeout` (15 s default); 3-attempt
  `_send_with_retry` with exponential backoff; three-state logging (DEV MODE / sent+message-id /
  failed-after-N-retries); Resend domain-verification hint in error log
- `backend/config.py` — added `email_timeout_seconds: int = 15`, `email_max_retries: int = 3`
- `.env.example` — clearer SMTP/Resend guidance (App Password vs account password, domain
  verification requirement)

**Tests added:** 3 resend-verification tests in `test_auth.py`; 3 retry/backoff tests in `test_email_service.py`

---

### C. Home page role-gating + ads data source

**What was wrong:** Home page 30-day forecast section showed the sign-up teaser to everyone
(including logged-in subscribers). "Create free account" hero CTA appeared to logged-in users.

**Architectural decision — "free" means guest on THIS page:** The role model uses `free` as an
alias for `subscriber` (no 5th DB role). For the home page forecast slot, the user confirmed:
"free/guest = not logged in → ADS". Logged-in non-premium → upgrade message. Premium → live
forecast. This is a per-page UX decision, not a role model change.

**Backend files created:**
- `backend/models/ad.py` — `Ad` model (9th DB table): title, body, image_url, link_url,
  cta_label, is_active, sort_order
- `backend/schemas/ad.py` — `AdResponse` (public fields only)
- `backend/services/ad_service.py` — `list_active_ads(db)` ordered by sort_order then newest
- `backend/routers/ads.py` — `GET /ads` (public, `Cache-Control: max-age=300`)
- `alembic/versions/b7c1e9d4a2f0_add_ads_table.py` — migration creates table + seeds 3 placeholder
  ads (→ /pricing, /map, /register)
- `backend/main.py` — registered `ads.router`

**Frontend files created/changed:**
- `frontend/types/ad.ts` — `Ad` interface
- `frontend/components/HomeAds.tsx` — renders ad cards from the `ads` table; falls back to
  `ForecastTeaser` only when zero active ads exist
- `frontend/components/HomePremiumForecast.tsx` — live `POST /predictions/forecast-30d` for the
  user's newest active subscription; disaster-type selector; `continentFromLatLon` for the coord →
  continent mapping the forecast endpoint requires; "Add a region" prompt if no subscriptions
- `frontend/components/HomeForecastSection.tsx` — rewritten 3-way gate using `meetsRole` from
  `lib/permissions`
- `frontend/components/HeroCtas.tsx` — already hid "Create free account" for logged-in users; no
  change needed
- `frontend/lib/geo.ts` — NEW: `continentFromLatLon(lat, lon) → Continent`
- `frontend/lib/endpoints.ts` — added `endpoints.ads.list()`
- `frontend/app/(public)/page.tsx` — `Promise.all([summary, ads])` parallel server-side fetch;
  passes `ads` to `HomeForecastSection`

**Tests added:** `backend/tests/test_ads.py` (3 tests: public access, cache header, sort order)

---

### D. Risk map: exact color scale + click-to-predict

**What was wrong:** The map used `leaflet.heat`, which blends colors by point density — a cluster of
Medium-risk points rendered orange/red at the legend's "High/Critical" color. There was no way to
guarantee "this color = this risk level." The documented "hover to predict" feature never existed in
the code; click just navigated away without running a prediction.

**Architectural decisions:**
1. **Discrete `CircleMarker`s, not a heatmap.** Color is set per-point from a shared scale; no
   blending. This is the only correct way to satisfy "a color always means one risk level."
2. **Click-to-predict, not hover-to-predict.** `POST /predictions/predict` is Subscriber+,
   rate-limited 60/min, and runs ML+RAG — hover would 401 guests and exhaust the limit in seconds.
   Click fires once per deliberate action. Hover shows a tooltip of the precomputed risk from the
   JSON (no network), which is the only feasible "hover shows risk" behaviour.

**Files created:**
- `frontend/lib/riskScale.ts` — `RISK_LEVELS` array (Low 0–30 / Medium 31–55 / High 56–75 /
  Critical 76–100, each with hex color); `getRiskLevel(score)`, `colorForScore(score)`. This is the
  **single source of truth** for marker fill, legend swatches, and the risk-level filter.

**Files changed:**
- `frontend/components/RiskMap.tsx` — completely rewritten: discrete `CircleMarker`s; `Legend`
  maps over `RISK_LEVELS` (color swatch + numeric range); risk-level filter uses `getRiskLevel`;
  click opens a popup that for Subscriber+ runs `endpoints.predictions.predict` once inline
  (shows SeverityBadge + probability + risk score + "Open full result" link); guests get the sign-up
  CTA; each marker has a hover `Tooltip` with precomputed risk (no network)

---

### E. Analytics panel fixes

**What was wrong:**
1. **Trends insight:** always compared 1980 vs 2000 regardless of the From/To filter; "All types"
   always showed Flood message.
2. **Continents tab:** no disaster-type filter; `continent_stats.json` had no per-type breakdown.
3. **Insurance gap:** help text said "share of total damage" but the metric is actually
   `median(insured_i / total_i)` per event — biased toward high-income markets.

**Backend changes:**
- `scripts/generate_emdat_stats.py` — `build_continent_stats()` now outputs
  `events_by_type: {"Flood": N, ...}` per continent; `data/generated/continent_stats.json`
  regenerated (0.7 KB → 1.8 KB)

**Frontend changes:**
- `frontend/types/regions.ts` — `ContinentEntry.events_by_type?: Record<string, number>`
- `frontend/components/analytics/AnalyticsPanels.tsx`:
  - `TrendsTab`: insight now uses `filterFrom`/`filterTo` as comparison points; "All" sums all
    types; template strings use `{d1}`, `{d2}`, `{n1}`, `{n2}` instead of hardcoded decades
  - `ContinentsTab`: added disaster-type filter; when type selected, shows `events_by_type[type]`
    per continent and hides metric dropdown (per-type median deaths/damage not available)
  - `InsuranceTab`: rewritten help text in plain language; added caveat note below chart disclosing
    the data limitation (fewer than 40% of events have both figures; biased toward high-income
    markets)

**Tests added:** `test_generation.py` — assertion that `continent_stats.json` values include
`events_by_type` with consistent internal structure

---

### F. Timeseries page fixes

**What was wrong:**
1. **Insight message:** always read `dec1980.events` / `dec2000.events` regardless of selected
   metric; string templates hardcoded "events in the 1980s"
2. **Tooltip:** Recharts default showed two numbers per hover (actual + trend) with no explanation
   of what distinguished them
3. **No region filter:** `timeseries.json` had only global `by_year` / `by_decade`

**Backend changes:**
- `scripts/generate_emdat_stats.py` — `build_timeseries()` now outputs `by_continent_decade`:
  5 continents × 8 types × 13 decades, same shape as `by_decade`; `data/generated/timeseries.json`
  regenerated (87.1 KB → 171.2 KB)

**Frontend changes:**
- `frontend/types/regions.ts` — `TimeSeriesData.by_continent_decade?` optional field
- `frontend/components/analytics/TimeSeriesPageContent.tsx` — completely rewritten:
  - insight now uses `getMetricVal(decade, metric)` — adapts to Events/Deaths/Affected/Damage;
    title/body templates use `{metric}` label; skips gracefully when no 1980/2000 data
  - custom `ChartTooltip` component with color swatches, value, and one-sentence note explaining
    "Bars = actual EM-DAT figures; Trend line = least-squares fit across all decades"
  - continent dropdown added to `FilterBar`; switches `series` between `by_decade[type]` and
    `by_continent_decade[continent][type]`; insight suffix notes "(Asia only)" when filtered

**Tests added:** `test_generation.py` — assertion for `by_continent_decade` shape (5+ continents,
Flood + Earthquake present, 13-decade arrays)

---

## API surface (new endpoints this phase)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/v1/auth/resend-verification` | Public | Re-generate and resend verification email. Generic 200 — never reveals if account exists. |
| `GET`  | `/api/v1/ads` | Public | Active home-page ads, ordered by sort_order. `Cache-Control: max-age=300`. |
| `GET`  | `/api/v1/regions/countries` | Public | Continent→country picker table with fixed centroids for the prediction forms. `name` = exact EM-DAT country string. `Cache-Control: max-age=3600`. |
| `GET`  | `/api/v1/subscriptions/lookup/{token}` | Public | Read-only `{region_name, is_active}` by unsubscribe token (no side effects) — lets the email page name the region before confirming. 404 if unknown. *(subscriptions phase)* |
| `DELETE` | `/api/v1/subscriptions/{token}` | Public | *(changed)* now also returns `region_name` alongside `status`. *(subscriptions phase)* |

---

## Architectural decisions and rationale

| Decision | Rationale |
|----------|-----------|
| `free` is an alias for `subscriber` (no 5th DB role) | Avoids a migration; the registered free tier IS role=subscriber. `normalize_role` in permissions.py maps both to rank 1. |
| Email: Gmail SMTP for verification, Resend for alerts | Keeps the split from Phase 6. Both degrade-not-fail; real sending requires creds in `.env`. |
| Risk map uses discrete markers, not a heatmap | Heatmaps blend by density — color↔level can never be exact. Markers are filled with `colorForScore` from `riskScale.ts`, which is the single source of truth. |
| Click-to-predict (not hover) | `POST /predict` is Subscriber+, rate-limited 60/min, ML+RAG — hover would exhaust rate limit and 401 guests. |
| `ads` table has no FK to any user or entity | Ads are admin-managed content, not user-associated data. Soft-delete via `is_active`. Studio editor deferred to Phase 10. |
| `by_continent_decade` added to `timeseries.json` | Precomputed at build time — zero runtime cost. Follows existing `by_decade` pattern; 5 × 8 × 13 entries ≈ 84 KB addition. |
| Insurance gap metric stays as `median(insured_i/total_i)` | The underlying calculation is valid; only the presentation was misleading. Help text now discloses the data limitation and market-bias caveat. |
| **Impact = blend(ML regressors, EM-DAT type-medians) + plausibility clamp** *(this phase)* | The regressors are disaster-type-blind (16 geo/temporal features only); EM-DAT medians are type-specific. Blending makes Flood ≠ Earthquake at one point. The `deaths ≤ injured ≤ affected` clamp guarantees plausibility; per-type floors keep ratios sane; zeros preserved. One helper `_blend_and_constrain_impact` so `predict()` and `predict_impact()` can't drift. |
| **Country centroids from a curated ISO3 table, not event medians** *(this phase)* | EM-DAT event coords are sparse (~2.6k/16k rows) and half the countries lack ≥3 — medians would be jumpy/incomplete. ISO3 centroids are stable and complete; joined on the CSV's clean 100 %-coverage `ISO` column. `name` stays the exact EM-DAT string so the country-tier impact lookup still hits. |
| **Default country = United States** *(this phase)* | Most EM-DAT events (1,087) → the most trustworthy country-tier impact medians. Req 5 delegated the choice. |
| **All prediction forms country-only; `/map` dashboard prefill dropped** *(this phase)* | User-confirmed scope. Manual lat/lon let users enter nonsense and mistyped country names missed the country tier. The map's inline click-predict popup is unaffected; only its "Open full result" deep-link changed. |
| **Coverage notes kept (not removed)** *(this phase)* | They are a documented Feature-1 transparency requirement that genuinely discloses sparse historical reporting (~26 % injuries, ~33 % damage). Reworded for clarity instead of removing. |
| **Subscription limits: subscriber 8 / premium 10** *(subscriptions phase)* | User decision, set once in `_SUBSCRIPTION_LIMITS` (`backend/core/permissions.py`). Premium was effectively unlimited (1_000_000); now 10. Frontend mirrors via `subscriptionLimit()` (UX only). Admin stays unbounded. |
| **Subscriptions generate alerts by running the model per region** *(subscriptions phase)* | A subscription has only region_name + lat/lon, so the dispatch evaluates each region's own risk via `classify_all_types` rather than depending on another user's prediction matching a region string. By frequency: weekly digest always sends; immediate only on High/Critical. Degrade-not-fail so cold starts / tests still produce a (generic) alert. |
| **Public unsubscribe page looks up before deleting** *(subscriptions phase)* | Auto-deleting on page load was silent and exposed to email-client link prefetch. A read-only `GET /subscriptions/lookup/{token}` lets the page name the region and require a click. DELETE stays the one-click action behind the confirm. |
| **Un-freeze region/country/historical_freq instead of retraining** *(this phase)* | The encoders (`le_region`, `le_country`, `region_freq_map`) already ship in the bundle and were trained with real values; they were just hardcoded to 0/0/avg at inference. Resolving them from the picked country is a pure inference-path fix — no retraining, no migration — and makes location genuinely move predictions. |
| **Reconcile Risk vs Forecast by labelling, not by merging code** *(this phase)* | They already call one shared `predict()`; the only intended difference is the month feature. With "Current month" as the default, day-0 of the forecast == the Risk card. We label each clearly rather than faking daily variation we cannot produce without a live weather feed (`day_offset` is a dead feature). |
| **Shared `MonthSelect` (dropdown), not free-text season** *(this phase)* | Three cards each parsed free-text season differently. One dropdown emitting `0`/`1-12` standardises the month feature and removes a class of input errors. The forecast keeps auto-deriving per-day months by design. |
| **Magnitude removed from the request contract, kept as a model feature** *(this phase)* | The Risk UI never collected magnitude (always sent `null`); removing it from `PredictRequest` cleans the contract. The model still has `has_magnitude`/`dis_mag_value` internally (always 0 on this path) — removing the feature would require retraining. |
| **CSV export is client-side** *(this phase)* | "Download data" needs no server work — the result is already in the browser. `frontend/lib/csv.ts` builds the CSV and triggers a Blob download. Keeps it off the rate-limited API and avoids a new endpoint. PDF (Premium) remains the server-rendered report path. |

---

## What the next phase needs to know

### Immediate unresolved items (flagged, not blocking)

0. **Country centroids are country-level, not city-level** *(this phase)* — a prediction for a country
   runs at its geographic centroid. The *impact* numbers come from the EM-DAT country tier (so they are
   accurate per country), but the lat/lon-driven classifier sees the centre of the country. This is the
   intended trade-off of "pick a country, not a point"; if city-level precision is ever wanted, extend
   `countries.json` with sub-national entries or restore an optional map-point path.

1. **Subscription limits** — ✅ resolved: subscriber 8 / premium 10 (user decision), set in
   `backend/core/permissions.py::_SUBSCRIPTION_LIMITS`. (CLAUDE.md's "3 free / 10 premium" spec line is
   now stale for the free tier.)

2. **Verification token expiry** — the template says "valid for 24 hours" but expiry is not
   enforced. Enforcing it requires a DB column (e.g. `verification_token_expires_at` on `users`).
   Low priority until email actually sends in production.

3. **Admin CRUD endpoints** — `GET /admin/users` and `PATCH /admin/users/{id}` are not built.
   The frontend `/admin` page handles the 404 gracefully (shows a "not yet implemented" banner).

4. **Email creds empty in `.env`** — both SMTP verification and Resend alerts fall back to
   `.email_dev.log`. Fill `SMTP_USER` + `SMTP_PASSWORD` (16-char Gmail App Password) and
   `RESEND_API_KEY` + verified `RESEND_FROM_EMAIL` to enable real sending.

5. **`leaflet.heat` in `package.json`** — unused dep (map now uses `CircleMarker`); harmless but
   can be removed with `npm uninstall leaflet.heat`.

### Key invariants the next developer must respect

- **`backend/core/permissions.py` is the only place for role decisions** — including subscription limits
  (`_SUBSCRIPTION_LIMITS` / `subscription_limit()`). Do not add inline `role == "..."` checks or hardcode
  limits in routers, services, or the frontend (`subscriptionLimit()` mirrors it for UX only).

- **`alert_service._evaluate_subscription` is degrade-not-fail.** It returns `None` when the model isn't
  loaded or anything errors, and `dispatch_alerts` falls back to a generic alert. Never let a model error
  abort a dispatch. Weekly digest always sends; `high_risk_immediate` only fires on High/Critical.

- **`frontend/lib/riskScale.ts` is the only place for the risk color scale.** Marker fill, legend,
  and filter must all read from it — never hardcode hex values.

- **`frontend/lib/permissions.ts` is UX only.** The backend `Depends()` guards are the real
  security boundary. The frontend mirror is for show/hide decisions only.

- **`data/generated/*.json` are precomputed.** Re-run `py -3.12 scripts/generate_emdat_stats.py`
  after any change to `generate_emdat_stats.py`. Do not hand-edit the JSON files.

- **`ads` table Studio editor is Phase 10.** Until then, seed new ads directly via a migration or
  SQL; the frontend reads whatever is in the DB.

- **Insurance gap metric is `median(insured_i / total_i)`, not total-insured / total-damage.**
  If this is ever recalculated, preserve the caveat note in `strings.ts` and the plain-language
  help text.

- **`_blend_and_constrain_impact` in `backend/ml/predictor.py` is the only place impact numbers are
  produced.** Both `predict()` and `predict_impact()` call it. Do not re-add a raw-regressor impact
  path — that reintroduces the type-blind bug. The `deaths ≤ injured ≤ affected` clamp is the last step
  and must stay last.

- **`_resolve_location_features` in `backend/ml/predictor.py` is the only place region_enc / country_enc /
  historical_freq are produced for inference.** Both `predict()` and `_build_feature_vector()` call it. Do
  NOT re-hardcode these to `0 / 0 / avg` — that reintroduces the "location does nothing" bug. The selected
  `country` (exact EM-DAT name) is what drives region (via `COUNTRY_TO_REGION`) and frequency (via
  `region_freq_map`), so every prediction form must keep sending `country`.

- **Risk Level Classifier and 30-day Forecast share `predict()` and must stay reconciled.** They are the
  same model; the only intended difference is the month feature. `Risk(current month, day-0)` must equal
  `Forecast day-0` for the same country/type. If you change month/season handling, keep that identity and
  update `card3.reconcileNote` / `forecast.reconcileNote`.

- **`frontend/components/MonthSelect.tsx` is the only month/season input for the single-shot cards.** It
  emits `0` (current month) or `1-12`. Don't reintroduce free-text season inputs.

- **`countries.json` is generated, name-aligned to EM-DAT.** Each `name` is the exact EM-DAT country
  string (matches `emdat_stats.json` `by_country`). If you add countries, add their ISO3 centroid to
  `_ISO3_CENTROIDS` in `generate_emdat_stats.py` and re-run it — don't hand-edit the JSON. Countries
  without a centroid are intentionally dropped from the picker.

- **All prediction forms use `frontend/components/CountrySelect.tsx`.** Don't reintroduce free-text
  country/continent or manual lat/lon inputs on prediction forms (Subscriptions still uses manual
  lat/lon — that's a different, in-scope-out form). `country` sent to the backend must be the EM-DAT
  `name`, not the display `label`.

---

## TODO.md cross-reference

> A formal `TODO.md` now exists at the repo root (created this phase). The table below mirrors it.

| Item | Status |
|------|--------|
| Premium Alerts = 30-day forecast w/ probabilities for a subscribed region | ✅ Done — `AlertsForecastPanel.tsx` + role-aware `AlertsTab` |
| Send premium HTML email alerts (reuse email pipeline) | ✅ Done — `POST /alerts/email-forecast` (auto on generate) |
| Download PDF reports from Alerts | ✅ Done — `predictions.forecastPdf()` → `GET /predictions/forecast-30d/pdf` |
| Subscribe up to 10 regions (role layer) | ✅ Verified — `subscription_limit("premium")==10` |
| Upgrade via checkout flow (surfaced in Alerts) | ✅ Verified — non-premium CTA → `/pricing` |
| Location features actually drive predictions (un-freeze region/country/historical_freq) | ✅ Done — `_resolve_location_features` in `predictor.py` |
| `ClassifyRequest` gains `country` so the Disaster Type Predictor is location-aware | ✅ Done |
| Risk Level Classifier vs 30-day Forecast diagnosed + reconciled | ✅ Done — shared `predict()`, day-0 == Risk(current month), labelled |
| Consistent month/season input across all single-shot predictors | ✅ Done — `MonthSelect.tsx` |
| Remove Magnitude field from the Risk Level Classifier (full cleanup) | ✅ Done — dropped from `PredictRequest` + strings + form |
| "Download data" (CSV) for dashboard predictions + forecast + history | ✅ Done — `lib/csv.ts` + buttons |
| Country→fixed lat/lon lookup table | ✅ Done — `countries.json` + `_ISO3_CENTROIDS` + `GET /regions/countries` |
| Cascading continent→country selects (replace free-text) | ✅ Done — `frontend/components/CountrySelect.tsx` |
| Disable manual lat/lon; auto-fill from country | ✅ Done — all prediction forms read-only coords |
| Impact estimates vary by disaster type | ✅ Done — `_blend_and_constrain_impact` in `predictor.py` |
| Plausibility: deaths ≤ injured ≤ affected + sane ratios | ✅ Done — `_apply_plausibility` (+ `_IMPACT_RATIOS`) |
| Default country = most trustworthy | ✅ Done — United States (most EM-DAT events) |
| Decide on Injured/Damage coverage notes | ✅ Done — kept + reworded for clarity |
| Central permission layer (`can`, `Feature`, `ROLE_RANK`) | ✅ Done — `backend/core/permissions.py` |
| Email hardening (timeout, retry, observable logging) | ✅ Done — `backend/services/email_service.py` |
| `POST /auth/resend-verification` | ✅ Done |
| Home page role-gating (hide CTA for logged-in, forecast by role) | ✅ Done |
| Ads data source + `GET /ads` + seed | ✅ Done |
| Risk map: exact color scale + single source of truth | ✅ Done — `frontend/lib/riskScale.ts` |
| Click-to-predict on map (replace non-functional hover) | ✅ Done |
| Analytics trends insight: dynamic per type + date range | ✅ Done |
| Analytics continents tab: disaster-type filter | ✅ Done — `events_by_type` in JSON + component |
| Analytics insurance gap: plain language + math caveat | ✅ Done |
| Timeseries page: insight reflects selected metric | ✅ Done |
| Timeseries page: annotated tooltip | ✅ Done |
| Timeseries page: region/continent filter | ✅ Done — `by_continent_decade` in JSON + component |
| Admin CRUD endpoints (`GET/PATCH /admin/users`) | ❌ Not started |
| Subscription limit reconciliation (8 vs 3 free, unlimited vs 10 premium) | ❌ Deferred |
| Verification token expiry enforcement | ❌ Deferred (needs DB column) |
| Studio editor for ads (Phase 10) | ❌ Planned for Phase 10 |
| Fill real SMTP/Resend creds in production `.env` | ❌ Ops task — not a code change |
| Real payment provider (Stripe/Paymob) replacing MockPaymentService | ❌ Phase 9+ |
