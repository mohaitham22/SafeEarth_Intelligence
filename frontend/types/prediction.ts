// Mirrors backend/schemas/prediction.py exactly.
// Source: backend/schemas/prediction.py classes
//   PredictRequest, PredictionResponse, SHAPFeature, ForecastRequest,
//   ForecastDayResponse, PredictionHistoryItem, PredictionHistoryResponse.

import type {
  DataQuality,
  DataSource,
  DisasterType,
  SeverityLevel,
} from "./common"
import type { RecommendationItem } from "./recommendation"

export interface SHAPFeature {
  feature:          string
  contribution_pct: number
}

// Backend contract: `Union[str, int]`. Semantic values are season names
// ("spring"/"summer"/"autumn"/"fall"/"winter"), integer month 1-12, or 0 for
// current month — but the type stays open to match the Pydantic schema.
export type SeasonInput = string | number

export interface PredictRequest {
  latitude:      number
  longitude:     number
  region_name?:  string
  country:       string
  continent:     string
  disaster_type: DisasterType
  season?:       SeasonInput   // default 0 (current month)
  magnitude?:    number | null
}

export interface PredictionResult {
  id:                          string        // UUID
  disaster_type:               string
  probability_score:           number        // 0.0–1.0
  severity_level:              SeverityLevel
  risk_score:                  number        // 0–100 composite
  estimated_deaths:            number
  estimated_injuries:          number
  estimated_affected:          number
  estimated_damage_usd:        number        // stored as thousands USD
  uninsured_loss_usd:          number
  shap_explanation:            SHAPFeature[] // top 3 only
  secondary_disaster_warning:  string | null
  seasonal_peak_months:        number[]      // month numbers 1–12
  data_quality:                DataQuality
  data_source:                 DataSource
  country_used:                string | null
  n_events:                    number
  recommendations:             RecommendationItem[]
  model_version:               string
  created_at:                  string        // ISO datetime
}

export interface ForecastRequest {
  latitude:      number
  longitude:     number
  region_name?:  string
  country:       string
  continent:     string
  disaster_type: DisasterType
  force_refresh?: boolean
}

export interface ForecastDay extends PredictionResult {
  forecast_day_offset: number   // 0–29
  date:                string    // ISO date (YYYY-MM-DD)
}

export interface PredictionHistoryItem {
  id:                string
  disaster_type:     string | null
  severity_level:    SeverityLevel | null
  probability_score: number | null
  risk_score:        number | null
  region_name:       string | null
  latitude:          number | null
  longitude:         number | null
  created_at:        string
}

export interface PredictionHistoryResponse {
  items:     PredictionHistoryItem[]
  total:     number
  page:      number
  page_size: number
}

// ── /predictions/classify ─────────────────────────────────────────────────────

export interface ClassifyRequest {
  latitude:   number
  longitude:  number
  continent:  string
  year:       number
  season?:    SeasonInput
  magnitude?: number | null
}

export interface DisasterProbability {
  disaster_type: string
  probability:   number
}

export interface ClassifyResult {
  ranked:          DisasterProbability[]
  top_type:        string
  top_probability: number
  model_version:   string
}

// ── /predictions/impact ───────────────────────────────────────────────────────

export interface ImpactRequest {
  latitude:     number
  longitude:    number
  continent:    string
  year:         number
  season?:      SeasonInput
  region_name?: string
  country?:     string
}

export interface ImpactResult {
  predicted_disaster_type: string
  probability:             number
  expected_events:         number
  estimated_deaths:        number
  estimated_injuries:      number
  estimated_affected:      number
  estimated_damage_usd:    number   // thousands USD
  uninsured_loss_usd:      number   // thousands USD
  data_source:             string
  model_version:           string
}
