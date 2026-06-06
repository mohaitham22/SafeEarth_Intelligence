// Mirrors backend/schemas/alert.py

import type { SeverityLevel } from "./common"

export type AlertType   = "weekly_digest" | "high_risk_immediate"
export type AlertStatus = "sent" | "failed" | "pending"

export interface AlertResponse {
  id:              string
  subscription_id: string
  user_id:         string
  alert_type:      AlertType
  disaster_type:   string | null
  severity_level:  SeverityLevel | null
  message_body:    string | null
  sent_at:         string | null
  status:          AlertStatus
}

export interface AlertHistoryResponse {
  items:     AlertResponse[]
  total:     number
  page:      number
  page_size: number
}

// Result of POST /alerts/email-forecast (premium emails itself the forecast peak).
export interface EmailForecastResponse {
  sent:           boolean
  message_id:     string | null
  to:             string
  peak_day:       number
  disaster_type:  string | null
  severity_level: SeverityLevel | string | null
  region_name:    string | null
}
