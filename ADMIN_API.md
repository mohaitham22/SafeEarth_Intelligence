# SafeEarth Intelligence — Admin API Reference

Base URL: `https://api.safeearth.tech/api/v1`  
All responses are JSON. Protected routes require an Authorization header or a dispatch secret.

---

## Authentication

Two auth methods are accepted, depending on the endpoint class:

| Endpoint class | Method 1 (machine / n8n) | Method 2 (browser / curl) |
|----------------|--------------------------|--------------------------|
| `/admin/*` CRUD | — | `Authorization: Bearer <admin_access_token>` |
| `/alerts/dispatch` (weekly) | `X-Dispatch-Secret: <secret>` | `Authorization: Bearer <admin_access_token>` |
| `/alerts/monthly-dispatch` | `X-Dispatch-Secret: <secret>` | `Authorization: Bearer <admin_access_token>` |

**Getting an admin JWT:**  
`POST /api/v1/auth/login` with an admin-role user's credentials → `access_token` in the response.

**Dispatch secret:**  
Generate once: `python -c "import secrets; print(secrets.token_hex(32))"`. Set as `ALERT_DISPATCH_SECRET` in both the FastAPI `.env` / Render env vars and n8n's `$env.ALERT_DISPATCH_SECRET`.

---

## Endpoints

### Health
`GET /health` — public, no auth

```json
{ "status": "ok", "timestamp": "2026-06-05T08:00:00Z", "models_loaded": true, "rag_loaded": true }
```

---

### User Management

#### List users
`GET /admin/users` — requires Admin JWT

Query params:

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `page` | int | 1 | Page number |
| `page_size` | int | 20 | Items per page (max 100) |
| `role` | string | — | Filter by role: `subscriber`, `premium`, `admin` |
| `is_verified` | bool | — | Filter by email-verified status |
| `search` | string | — | Substring match on email or full_name |

**Response 200:**
```json
{
  "items": [
    {
      "id": "uuid",
      "email": "user@example.com",
      "full_name": "Alice",
      "role": "subscriber",
      "is_verified": true,
      "premium_expires_at": null,
      "created_at": "2026-05-01T10:00:00Z"
    }
  ],
  "total": 45,
  "page": 1,
  "page_size": 20
}
```

#### Update user
`PATCH /admin/users/{user_id}` — requires Admin JWT

**Request body** (all fields optional):
```json
{ "role": "premium", "is_verified": true }
```

**Response 200:** Updated `AdminUserItem` object.

**Errors:**
- `403` — attempting to change your own role
- `404` — user not found

---

### Site Statistics

`GET /admin/stats` — requires Admin JWT

**Response 200:**
```json
{
  "users": {
    "total": 45,
    "verified": 38,
    "by_role": { "subscriber": 30, "premium": 12, "admin": 3 }
  },
  "predictions": { "total": 820, "forecasts": 210, "last_7_days": 34 },
  "subscriptions": { "active": 67 },
  "alerts": { "total_sent": 1240, "last_7_days": 88 },
  "payments": { "total_succeeded": 28, "revenue_usd": "284.00" },
  "email_logs": { "total": 95 }
}
```

---

### ML Model Stats

`GET /admin/model-stats` — requires Admin JWT

Returns the v4.2 model constants plus live pipeline state from `app.state`:

**Response 200:**
```json
{
  "version": "v4.2",
  "macro_f1": 0.7052,
  "weighted_f1": 0.7587,
  "accuracy": 0.7467,
  "feature_count": 16,
  "ensemble": { "XGBoost": 0.60, "CatBoost": 0.40 },
  "per_class_f1": [
    { "type": "Earthquake",          "f1": 0.976, "support": 1137 },
    { "type": "Flood",               "f1": 0.778, "support": 5272 },
    { "type": "Storm",               "f1": 0.771, "support": 4005 },
    { "type": "Extreme temperature", "f1": 0.749, "support": 584  },
    { "type": "Volcanic activity",   "f1": 0.668, "support": 222  },
    { "type": "Wildfire",            "f1": 0.628, "support": 452  },
    { "type": "Drought",             "f1": 0.589, "support": 685  },
    { "type": "Landslide",           "f1": 0.482, "support": 713  }
  ],
  "models_loaded": true,
  "rag_loaded": true
}
```

Source of truth: `backend/ml/model_info.py`. To update after retraining, edit that file only.

---

### Alert Dispatch Preview (dry-run)

`GET /admin/alerts/dispatch-preview` — requires Admin JWT

Returns counts with no side effects.

**Response 200:**
```json
{ "active_subscriptions": 12, "premium_users": 4 }
```

---

### Weekly Alert Dispatch

`POST /api/v1/alerts/dispatch` — Admin JWT or X-Dispatch-Secret

**Request body:**
```json
{ "alert_type": "weekly_digest" }
```

**Response 200:**
```json
{ "queued": 7, "message": "Alert dispatch queued for 7 subscription(s)." }
```

Fan-out behaviour:
- Subscriber (free): in-app `Alert` row only.
- Premium/Admin: in-app `Alert` + Resend HTML email + `PremiumEmailLog` row.

---

### Monthly Digest Dispatch

`POST /api/v1/alerts/monthly-dispatch` — Admin JWT or X-Dispatch-Secret

Sends one digest email per premium user who had ≥1 alert in the specified calendar month. Each email is dispatched as a `BackgroundTask` (response returns immediately).

**Request body** (all fields optional — defaults to previous calendar month):
```json
{ "year": 2026, "month": 5 }
```

| Field | Type | Constraint | Default |
|-------|------|-----------|---------|
| `year` | int | 2000–2100 | Previous month's year |
| `month` | int | 1–12 | Previous month's number |

Both `year` and `month` must be provided together or omitted together.

**Response 200:**
```json
{
  "dispatched": 3,
  "skipped": 1,
  "period": "2026-05",
  "queued_in_background": true
}
```

| Field | Description |
|-------|-------------|
| `dispatched` | Premium users who had ≥1 alert that month and received a digest |
| `skipped` | Premium users who had zero alerts that month |
| `period` | `"YYYY-MM"` string for the covered calendar month |
| `queued_in_background` | Always `true` — emails are non-blocking |

**Errors:**
- `400` — `year`/`month` is in the future or invalid (both-or-neither validation)
- `401` — missing or invalid auth

**Email content:** Full alert table for the month — date · region · disaster type · severity badge · message snippet. Template: `backend/templates/emails/monthly_digest.html`.

---

### Studio — Ads CRUD

All Studio endpoints require Admin JWT.

#### List all ads (including inactive)
`GET /admin/ads`

**Response 200:** `AdAdminItem[]`

```json
[
  {
    "id": "uuid",
    "title": "SafeEarth Premium",
    "body": "Get email alerts and 30-day forecasts.",
    "image_url": "https://api.safeearth.tech/static/ads/uuid_banner.png",
    "link_url": "/pricing",
    "cta_label": "Upgrade Now",
    "sort_order": 1,
    "is_active": true,
    "created_at": "2026-06-01T00:00:00Z"
  }
]
```

#### Create ad
`POST /admin/ads`

**Request body:**
```json
{
  "title": "Ad Title",
  "body": "Optional description.",
  "link_url": "/pricing",
  "cta_label": "Learn More",
  "sort_order": 0,
  "is_active": true
}
```

**Response 201:** Created `AdAdminItem`.

#### Update ad
`PATCH /admin/ads/{ad_id}`

**Request body** (all fields optional):
```json
{ "title": "New Title", "is_active": false }
```

**Response 200:** Updated `AdAdminItem`.

#### Upload ad image
`POST /admin/ads/{ad_id}/image` — multipart/form-data

Field name: `upload`. Accepted MIME types: `image/jpeg`, `image/png`, `image/webp`, `image/gif`.

Saved to `backend/static/ads/{ad_id}_{original_filename}`.  
Sets `image_url` to `{API_BASE_URL}/static/ads/{filename}`.

**Response 200:** Updated `AdAdminItem` with new `image_url`.

**Errors:**
- `415` — unsupported content type

#### Deactivate ad (soft delete)
`DELETE /admin/ads/{ad_id}`

Sets `is_active=False`. Record is never hard-deleted.

**Response 200:**
```json
{ "deleted": true }
```

---

## n8n Integration

### Weekly dispatch — `n8n/weekly_dispatch.json`
- Schedule: `0 8 * * 1` (every Monday 08:00 UTC)
- HTTP POST to `POST /api/v1/alerts/dispatch`
- Header: `X-Dispatch-Secret: ={{ $env.ALERT_DISPATCH_SECRET }}`
- Body: `{ "alert_type": "weekly_digest" }`

### Monthly digest — `n8n/monthly_digest.json`
- Schedule: `0 8 1 * *` (1st of each month, 08:00 UTC)
- HTTP POST to `POST /api/v1/alerts/monthly-dispatch`
- Header: `X-Dispatch-Secret: ={{ $env.ALERT_DISPATCH_SECRET }}`
- Body: `{ "year": {{ $now.minus(1, "month").year }}, "month": {{ $now.minus(1, "month").month }} }`

**Setup steps for both workflows:**
1. Generate: `python -c "import secrets; print(secrets.token_hex(32))"`
2. Set `ALERT_DISPATCH_SECRET=<value>` in FastAPI `.env` / Render env vars.
3. Start n8n with the same value: `$env:ALERT_DISPATCH_SECRET = "<value>"; npx n8n`
4. Import the JSON via **Workflows → Import from File**.
5. Click **Execute Node** on the HTTP Request node to do a manual test.
6. Toggle **Active** to enable the cron schedule.

---

## Error Reference

| Status | Meaning |
|--------|---------|
| 400 | Bad request (e.g., future month in monthly-dispatch, invalid plan name) |
| 401 | Missing or invalid auth token / dispatch secret |
| 403 | Authenticated but insufficient role (e.g., subscriber hitting /admin) or self-role-change attempt |
| 404 | Resource not found |
| 415 | Unsupported media type (image upload) |
| 422 | Pydantic validation error (check `detail` array) |
| 429 | Rate limit exceeded (slowapi) |
