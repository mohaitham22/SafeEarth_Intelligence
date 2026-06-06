// Mirrors backend/schemas/subscription.py

export type AlertFrequency = "weekly" | "immediate"

export interface SubscriptionCreate {
  region_name:      string
  latitude:         number
  longitude:        number
  alert_frequency?: AlertFrequency
}

export interface SubscriptionResponse {
  id:                string
  user_id:           string
  region_name:       string
  latitude:          number
  longitude:         number
  alert_frequency:   AlertFrequency
  is_active:         boolean
  unsubscribe_token: string
  created_at:        string
}

export interface SubscriptionListItem {
  id:                string
  user_id:           string
  region_name:       string
  latitude:          number
  longitude:         number
  alert_frequency:   AlertFrequency
  is_active:         boolean
  unsubscribe_token: string
  created_at:        string
}

// Public, read-only view by unsubscribe token (GET /subscriptions/lookup/{token}).
export interface SubscriptionLookup {
  region_name: string
  is_active:   boolean
}
