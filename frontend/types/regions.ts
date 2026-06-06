// Mirrors backend/schemas/regions.py + observed live shapes from /regions/*.

// /regions/stats — RegionStatsResponse
export interface RegionStats {
  median_deaths:        number | null
  median_injuries:      number | null
  median_affected:      number | null
  median_damage_000usd: number | null
  n_events:             number
  deaths_coverage:      number
  injuries_coverage:    number
  affected_coverage:    number
  damage_coverage:      number
  data_source:          "country" | "region" | "global"
  country_used:         string | null
}

// /regions/countries — continent→country picker with fixed centroids.
// `name` is the exact EM-DAT country string (sent back on predictions so the
// country-tier impact lookup hits); `label` is the cleaned display string.
export interface CountryEntry {
  name:     string
  label:    string
  iso:      string
  lat:      number
  lon:      number
  n_events: number
}
export interface CountryDefault {
  continent: string
  name:      string
  label:     string
  lat:       number
  lon:       number
}
export interface CountriesResponse {
  default:    CountryDefault
  continents: Record<string, CountryEntry[]>
}

// /regions/risk-map — list of historical events with valid in-range lat/lon
// and a composite risk score in [0, 100]. Mirrors backend RiskMapPoint.
export interface RiskMapPoint {
  lat:           number
  lon:           number
  risk_score:    number
  disaster_type: string
}

// /regions/trends — {decades: number[], "<DisasterType>": number[]}
// Confirmed live: {"decades":[1950..2020], "Flood":[81,155,...], ...}
export interface TrendsData {
  decades: number[]
  // disaster-type keys: counts per decade — same length as `decades`
  [disasterType: string]: number[]
}

// /regions/continent-stats — {continent: ContinentEntry}
export interface ContinentEntry {
  total_events:         number
  top_disaster:         string
  median_deaths:        number | null
  median_damage_000usd: number | null
  events_by_type?:      Record<string, number>  // per-type event counts (added Phase 5 polish)
}
export type ContinentStats = Record<string, ContinentEntry>

// /regions/insurance-gap — {disaster_type: ratio}
export type InsuranceRatios = Record<string, number>

// /regions/seasonal-peaks — {disaster_type: month_numbers}
export type SeasonalPeaks = Record<string, number[]>

// /regions/secondary-disasters — {disaster_type: SecondaryDisasterEntry[]}
export interface SecondaryDisasterEntry {
  type:  string
  count: number
}
export type SecondaryDisasters = Record<string, SecondaryDisasterEntry[]>

// /regions/timeseries — TimeseriesResponse
export interface TimeseriesYearEntry {
  year:           number
  events:         number
  deaths:         number | null
  affected:       number | null
  damage_000usd:  number | null
}
export interface TimeseriesDecadeEntry {
  decade:         number
  events:         number
  deaths:         number | null
  affected:       number | null
  damage_000usd:  number | null
}
export interface TimeSeriesData {
  by_year:               Record<string, TimeseriesYearEntry[]>
  by_decade:             Record<string, TimeseriesDecadeEntry[]>
  by_continent_decade?:  Record<string, Record<string, TimeseriesDecadeEntry[]>>
}
