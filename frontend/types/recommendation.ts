// Mirrors backend/schemas/recommendation.py exactly.
import type { DisasterType, SeverityLevel } from "./common"

export type RecommendationCategory =
  | "evacuation"
  | "kit"
  | "shelter"
  | "medical"
  | "contact"

export interface RecommendationItem {
  category: RecommendationCategory
  title:    string
  body:     string
}

export interface RecommendationQuery {
  disaster_type: DisasterType
  severity:      SeverityLevel
  region_name:   string
}

export interface RecommendationResponse {
  items: RecommendationItem[]
  personalisation_notice: string | null
}
