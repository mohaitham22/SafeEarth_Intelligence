// Types mirroring backend admin responses.
import type { UserRole } from "./common"
export type { UserRole }

export interface AdminUser {
  id: string
  email: string
  full_name: string | null
  role: UserRole
  is_verified: boolean
  premium_expires_at: string | null
  created_at: string
}

export interface AdminUsersResponse {
  items: AdminUser[]
  total: number
  page: number
  page_size: number
}

export interface DataStatus {
  status: "ok"
  models_loaded: boolean
  rag_loaded: boolean
  disaster_types: string[]
  countries_with_data: number
  regions_with_data: number
  files_present: Record<string, boolean>
}

export interface DispatchResult {
  queued: number
  message: string
}

export interface PatchUserRequest {
  role?: UserRole
  is_verified?: boolean
}

// ── Site Stats ──────────────────────────────────────────────────────────────

export interface UserCountsByRole {
  subscriber: number
  premium: number
  admin: number
}

export interface UserStats {
  total: number
  verified: number
  by_role: UserCountsByRole
}

export interface PredictionStats {
  total: number
  forecasts: number
  last_7_days: number
}

export interface SubscriptionStats {
  active: number
}

export interface AlertStats {
  total_sent: number
  last_7_days: number
}

export interface PaymentStats {
  total_succeeded: number
  revenue_usd: string
}

export interface EmailLogStats {
  total: number
}

export interface SiteStats {
  users: UserStats
  predictions: PredictionStats
  subscriptions: SubscriptionStats
  alerts: AlertStats
  payments: PaymentStats
  email_logs: EmailLogStats
}

// ── Model Stats ─────────────────────────────────────────────────────────────

export interface PerClassF1 {
  type: string
  f1: number
  support: number
}

export interface ModelStats {
  version: string
  macro_f1: number
  weighted_f1: number
  accuracy: number
  feature_count: number
  ensemble: Record<string, number>
  per_class_f1: PerClassF1[]
  models_loaded: boolean
  rag_loaded: boolean
}

// ── Dispatch Preview ────────────────────────────────────────────────────────

export interface DispatchPreviewResponse {
  active_subscriptions: number
  premium_users: number
}

// ── Monthly Dispatch ────────────────────────────────────────────────────────

export interface MonthlyDispatchRequest {
  year?: number
  month?: number
}

export interface MonthlyDispatchResponse {
  dispatched: number
  skipped: number
  period: string
  queued_in_background: boolean
}

// ── Studio: Ads ─────────────────────────────────────────────────────────────

export interface AdAdminItem {
  id: string
  title: string
  body: string | null
  image_url: string | null
  link_url: string | null
  cta_label: string | null
  sort_order: number
  is_active: boolean
  created_at: string
}

export interface AdCreate {
  title: string
  body?: string | null
  image_url?: string | null
  link_url?: string | null
  cta_label?: string | null
  sort_order?: number
  is_active?: boolean
}

export interface AdUpdate {
  title?: string
  body?: string | null
  image_url?: string | null
  link_url?: string | null
  cta_label?: string | null
  sort_order?: number
  is_active?: boolean
}
