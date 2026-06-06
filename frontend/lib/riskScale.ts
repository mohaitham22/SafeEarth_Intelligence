// Single source of truth for the map's risk-score → color scale.
//
// A color on the map ALWAYS means one risk level. The same RISK_LEVELS array
// drives the marker fill, the legend, and the risk-level filter, so they can
// never drift apart. Bands match the backend composite risk score (0–100) and
// reuse the SeverityBadge palette (green / yellow / orange / red).
//
// NOTE: this is the 0–100 *risk score* scale (RiskMap). It is intentionally
// separate from the 0–1 *probability* severity bands used by predictions —
// same four names/colors, different numeric thresholds.

import type { SeverityLevel } from "@/types"

export interface RiskLevel {
  level: SeverityLevel
  min:   number   // inclusive
  max:   number   // inclusive
  color: string   // hex, used for marker fill + legend swatch
}

// Ordered low → high. Contiguous, covering 0–100.
export const RISK_LEVELS: RiskLevel[] = [
  { level: "Low",      min: 0,  max: 30,  color: "#16a34a" },
  { level: "Medium",   min: 31, max: 55,  color: "#facc15" },
  { level: "High",     min: 56, max: 75,  color: "#f97316" },
  { level: "Critical", min: 76, max: 100, color: "#dc2626" },
]

/** Risk score (0–100) → risk level name. */
export function getRiskLevel(score: number): SeverityLevel {
  // Walk high → low so boundaries (31, 56, 76) resolve to the upper band.
  for (let i = RISK_LEVELS.length - 1; i >= 0; i--) {
    if (score >= RISK_LEVELS[i].min) return RISK_LEVELS[i].level
  }
  return "Low"
}

/** Risk score (0–100) → the exact legend color for its band. */
export function colorForScore(score: number): string {
  const band = RISK_LEVELS.find((b) => b.level === getRiskLevel(score))
  return band ? band.color : RISK_LEVELS[0].color
}
