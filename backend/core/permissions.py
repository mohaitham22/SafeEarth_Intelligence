"""
Central permission layer — the SINGLE source of truth for "what can each role do".

Every role/capability decision in the backend funnels through this module:
  - routers/services call `can(user, Feature.X)` or the `require_*` deps in core/deps.py
    (which themselves are built on `meets_role` / `can` here).
  - subscription limits come from `subscription_limit(role)`.

Roles (DB enum, models/enums.py::UserRole): guest | subscriber | premium | admin.
`free` is an ALIAS for `subscriber` (the registered free tier) — there is no separate
`free` row in the DB. `normalize_role` maps it onto `subscriber` so callers may use either
name interchangeably. Roles are strict supersets: guest ⊂ subscriber ⊂ premium ⊂ admin.

This is the security boundary on the server. The frontend mirror (frontend/lib/permissions.ts)
is UX-only (show/hide) and must never be trusted.
"""
from __future__ import annotations

import enum
from typing import Any


class Feature(str, enum.Enum):
    """Capabilities gated by role. Add new gated actions here, never inline a role check."""
    RUN_PREDICTION       = "run_prediction"        # POST /predictions/predict, /forecast-30d, history
    SUBSCRIBE_REGION     = "subscribe_region"      # POST /subscriptions
    VIEW_ALERT_HISTORY   = "view_alert_history"    # GET /alerts/history
    START_CHECKOUT       = "start_checkout"        # POST /premium/checkout
    RECEIVE_EMAIL_ALERTS = "receive_email_alerts"  # Premium email fan-out
    DOWNLOAD_PDF         = "download_pdf"           # GET /predictions/{id}/pdf, /forecast-30d/pdf
    DISPATCH_ALERTS      = "dispatch_alerts"        # POST /alerts/dispatch (admin path)
    MANAGE_USERS         = "manage_users"          # GET/PATCH /admin/users


# Ordered capability tiers. `free` and `subscriber` deliberately share rank 1 (alias).
ROLE_RANK: dict[str, int] = {
    "guest":      0,
    "free":       1,
    "subscriber": 1,
    "premium":    2,
    "admin":      3,
}

# Minimum role each feature requires. Single place to retune access.
FEATURE_MIN_ROLE: dict[Feature, str] = {
    Feature.RUN_PREDICTION:       "subscriber",
    Feature.SUBSCRIBE_REGION:     "subscriber",
    Feature.VIEW_ALERT_HISTORY:   "subscriber",
    Feature.START_CHECKOUT:       "subscriber",
    Feature.RECEIVE_EMAIL_ALERTS: "premium",
    Feature.DOWNLOAD_PDF:         "premium",
    Feature.DISPATCH_ALERTS:      "admin",
    Feature.MANAGE_USERS:         "admin",
}

# Active-subscription limits per role. This is the ONE place that decides the limit.
# Decision (see PROGRESS.md): subscriber = 8, premium = 10. Admin is internal/unbounded.
_SUBSCRIPTION_LIMITS: dict[str, int] = {
    "guest":      0,
    "subscriber": 8,
    "premium":    10,
    "admin":      1_000_000,
}


def normalize_role(subject: Any) -> str:
    """Coerce a User, UserRole enum, role string, or None into a canonical role string.

    `None` (no authenticated user) → "guest". `free` → "subscriber" (alias).
    """
    if subject is None:
        return "guest"
    # Accept a User object (has .role), or a role enum/string directly.
    role = getattr(subject, "role", subject)
    role = getattr(role, "value", role)  # UserRole enum → its string value
    role_str = str(role)
    return "subscriber" if role_str == "free" else role_str


def meets_role(subject: Any, min_role: str) -> bool:
    """True if subject's role rank is at least `min_role`'s rank."""
    return ROLE_RANK.get(normalize_role(subject), 0) >= ROLE_RANK.get(min_role, 99)


def can(user: Any, feature: Feature) -> bool:
    """The core check: may this user perform this feature? Guest/None allowed for read flows only."""
    return meets_role(user, FEATURE_MIN_ROLE[feature])


def subscription_limit(role: Any) -> int:
    """Max active subscriptions allowed for a role (free/subscriber alias collapse to the same)."""
    return _SUBSCRIPTION_LIMITS.get(normalize_role(role), 0)
