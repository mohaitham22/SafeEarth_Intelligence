// Frontend mirror of backend/core/permissions.py — UX ONLY.
//
// This decides what to SHOW/HIDE. It is NOT a security control: the backend
// FastAPI Depends() guards are the real boundary and re-check every request.
// Keep ROLE_RANK / FEATURE_MIN_ROLE in sync with backend/core/permissions.py.
//
// `free` is an alias for `subscriber` (the registered free tier) — both rank 1.

import type { UserRole } from "@/types"

// Roles the backend may emit, plus the `free` alias and an explicit guest fallback.
export type Role = UserRole | "free" | "guest"

export type Feature =
  | "run_prediction"
  | "subscribe_region"
  | "view_alert_history"
  | "start_checkout"
  | "receive_email_alerts"
  | "download_pdf"
  | "dispatch_alerts"
  | "manage_users"

const ROLE_RANK: Record<string, number> = {
  guest: 0,
  free: 1,
  subscriber: 1,
  premium: 2,
  admin: 3,
}

const FEATURE_MIN_ROLE: Record<Feature, string> = {
  run_prediction:       "subscriber",
  subscribe_region:     "subscriber",
  view_alert_history:   "subscriber",
  start_checkout:       "subscriber",
  receive_email_alerts: "premium",
  download_pdf:         "premium",
  dispatch_alerts:      "admin",
  manage_users:         "admin",
}

/** Normalise a role-ish value (role string, `free` alias, or null/undefined) to canonical form. */
export function normalizeRole(role: string | null | undefined): string {
  if (!role) return "guest"
  return role === "free" ? "subscriber" : role
}

/** True if `role` ranks at least as high as `minRole`. */
export function meetsRole(role: string | null | undefined, minRole: string): boolean {
  return (ROLE_RANK[normalizeRole(role)] ?? 0) >= (ROLE_RANK[minRole] ?? 99)
}

/** UX gate: should this role see/do `feature`? Mirrors backend `can()`. */
export function can(role: string | null | undefined, feature: Feature): boolean {
  return meetsRole(role, FEATURE_MIN_ROLE[feature])
}

/** Convenience for the admin-area UX gate. */
export function isAdmin(role: string | null | undefined): boolean {
  return meetsRole(role, "admin")
}

// Active-subscription limits per role. Mirrors backend/core/permissions.py
// _SUBSCRIPTION_LIMITS — UX only (the backend enforces the real cap). Decision:
// subscriber 8, premium 10, admin effectively unbounded.
const SUBSCRIPTION_LIMITS: Record<string, number> = {
  guest: 0,
  subscriber: 8,
  premium: 10,
  admin: 1_000_000,
}

/** Max active subscriptions allowed for a role (free → subscriber). */
export function subscriptionLimit(role: string | null | undefined): number {
  return SUBSCRIPTION_LIMITS[normalizeRole(role)] ?? 0
}
