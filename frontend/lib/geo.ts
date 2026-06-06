// Lightweight, dependency-free geo helpers.
//
// continentFromLatLon: approximate a continent from coordinates. The 30-day
// forecast endpoint requires a `continent` field (a model feature) but a saved
// region subscription only stores region_name + lat/lon. This gives a sensible
// value for that call. It is intentionally coarse — the classifier's unseen-
// category encoder tolerates an imperfect continent, and EM-DAT lookup falls
// back region→global. Returns one of the 5 EM-DAT continents.

export type Continent = "Africa" | "Americas" | "Asia" | "Europe" | "Oceania"

export function continentFromLatLon(lat: number, lon: number): Continent {
  // Americas: the western hemisphere longitudes.
  if (lon <= -30 && lon >= -170) return "Americas"

  // Oceania: Australia / NZ / Pacific island band.
  if (lat <= 0 && lon >= 110 && lon <= 180) return "Oceania"

  // Europe: roughly north of the Mediterranean, west of the Urals.
  if (lat >= 36 && lon >= -25 && lon <= 60) return "Europe"

  // Africa: the Africa box (also covers the Middle East edge acceptably).
  if (lat >= -38 && lat < 36 && lon >= -20 && lon <= 52) return "Africa"

  // Everything else in the eastern hemisphere → Asia.
  return "Asia"
}
