// Mirrors backend/schemas/premium.py 1:1 — do not add fields that don't exist there.

export interface CheckoutRequest {
  plan_name: "monthly" | "yearly"
}

export interface CheckoutResponse {
  checkout_url: string
  session_id:   string
  plan_name:    string
}

export interface WebhookResponse {
  received: boolean
}
