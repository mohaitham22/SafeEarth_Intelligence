// Shared literal unions used across multiple endpoint type files.
// Mirror the Pydantic Literals in backend/schemas/*.py exactly — if EM-DAT
// taxonomy or severity buckets change, update both ends together.

export type DisasterType =
  | "Flood"
  | "Storm"
  | "Earthquake"
  | "Wildfire"
  | "Volcanic activity"
  | "Landslide"
  | "Drought"
  | "Extreme temperature"

export type SeverityLevel = "Low" | "Medium" | "High" | "Critical"

export type DataSource = "country" | "region" | "global"

export type DataQuality = "full" | "limited"

export type UserRole = "guest" | "subscriber" | "premium" | "admin"
