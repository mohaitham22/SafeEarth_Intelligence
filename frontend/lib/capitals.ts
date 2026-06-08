// Curated country + capital-city picker for the 30-day alert forecast.
//
// The forecast endpoint is coordinate-driven: it needs the capital city's
// lat/lon, the EM-DAT `country` name (so the country-tier impact lookup hits),
// and the `continent`. Each row bundles all of that, so selecting ANY capital
// returns a fully working forecast — not just a label with no data.
//
// `country` is the EXACT EM-DAT country string (see the by_country keys in
// data/generated/emdat_stats.json) — that is why some carry official forms like
// "(the)" or "(Islamic Republic of)". If a name ever fails to match, the backend
// EM-DAT lookup falls back region -> global, so the forecast still runs. To add a
// location, append one {country, capital, continent, lat, lon} row below.

export interface CapitalLocation {
  country:   string   // exact EM-DAT country name (country-tier impact lookup)
  capital:   string   // capital city — shown in the dropdown
  continent: string   // Africa | Americas | Asia | Europe | Oceania
  lat:       number   // capital-city latitude
  lon:       number   // capital-city longitude
}

// ~46 capitals spread across all five continents. Kept alphabetical within each
// continent block for easy scanning / extension.
export const CAPITALS: CapitalLocation[] = [
  // ── Africa ────────────────────────────────────────────────────────────────
  { country: "Algeria",                                continent: "Africa",   capital: "Algiers",      lat: 36.75,  lon: 3.04 },
  { country: "Congo (the Democratic Republic of the)", continent: "Africa",   capital: "Kinshasa",     lat: -4.32,  lon: 15.31 },
  { country: "Egypt",                                  continent: "Africa",   capital: "Cairo",        lat: 30.04,  lon: 31.24 },
  { country: "Ethiopia",                               continent: "Africa",   capital: "Addis Ababa",  lat: 9.03,   lon: 38.74 },
  { country: "Ghana",                                  continent: "Africa",   capital: "Accra",        lat: 5.60,   lon: -0.19 },
  { country: "Kenya",                                  continent: "Africa",   capital: "Nairobi",      lat: -1.29,  lon: 36.82 },
  { country: "Morocco",                                continent: "Africa",   capital: "Rabat",        lat: 34.02,  lon: -6.83 },
  { country: "Nigeria",                                continent: "Africa",   capital: "Abuja",        lat: 9.08,   lon: 7.40 },
  { country: "South Africa",                           continent: "Africa",   capital: "Pretoria",     lat: -25.75, lon: 28.19 },
  { country: "Tanzania, United Republic of",           continent: "Africa",   capital: "Dodoma",       lat: -6.16,  lon: 35.75 },

  // ── Americas ──────────────────────────────────────────────────────────────
  { country: "Argentina",                              continent: "Americas", capital: "Buenos Aires", lat: -34.61, lon: -58.38 },
  { country: "Brazil",                                 continent: "Americas", capital: "Brasília",     lat: -15.79, lon: -47.88 },
  { country: "Canada",                                 continent: "Americas", capital: "Ottawa",       lat: 45.42,  lon: -75.70 },
  { country: "Chile",                                  continent: "Americas", capital: "Santiago",     lat: -33.45, lon: -70.67 },
  { country: "Colombia",                               continent: "Americas", capital: "Bogotá",       lat: 4.71,   lon: -74.07 },
  { country: "Cuba",                                   continent: "Americas", capital: "Havana",       lat: 23.11,  lon: -82.37 },
  { country: "Haiti",                                  continent: "Americas", capital: "Port-au-Prince",lat: 18.59, lon: -72.31 },
  { country: "Mexico",                                 continent: "Americas", capital: "Mexico City",  lat: 19.43,  lon: -99.13 },
  { country: "Peru",                                   continent: "Americas", capital: "Lima",         lat: -12.05, lon: -77.04 },
  { country: "United States of America (the)",         continent: "Americas", capital: "Washington, D.C.", lat: 38.90, lon: -77.04 },

  // ── Asia ──────────────────────────────────────────────────────────────────
  { country: "Bangladesh",                             continent: "Asia",     capital: "Dhaka",        lat: 23.81,  lon: 90.41 },
  { country: "China",                                  continent: "Asia",     capital: "Beijing",      lat: 39.90,  lon: 116.41 },
  { country: "India",                                  continent: "Asia",     capital: "New Delhi",    lat: 28.61,  lon: 77.21 },
  { country: "Indonesia",                              continent: "Asia",     capital: "Jakarta",      lat: -6.21,  lon: 106.85 },
  { country: "Iran (Islamic Republic of)",             continent: "Asia",     capital: "Tehran",       lat: 35.69,  lon: 51.39 },
  { country: "Japan",                                  continent: "Asia",     capital: "Tokyo",        lat: 35.68,  lon: 139.69 },
  { country: "Nepal",                                  continent: "Asia",     capital: "Kathmandu",    lat: 27.72,  lon: 85.32 },
  { country: "Pakistan",                               continent: "Asia",     capital: "Islamabad",    lat: 33.69,  lon: 73.05 },
  { country: "Philippines (the)",                      continent: "Asia",     capital: "Manila",       lat: 14.60,  lon: 120.98 },
  { country: "Thailand",                               continent: "Asia",     capital: "Bangkok",      lat: 13.76,  lon: 100.50 },
  { country: "Turkey",                                 continent: "Asia",     capital: "Ankara",       lat: 39.93,  lon: 32.86 },
  { country: "Viet Nam",                               continent: "Asia",     capital: "Hanoi",        lat: 21.03,  lon: 105.85 },

  // ── Europe ────────────────────────────────────────────────────────────────
  { country: "France",                                 continent: "Europe",   capital: "Paris",        lat: 48.85,  lon: 2.35 },
  { country: "Germany",                                continent: "Europe",   capital: "Berlin",       lat: 52.52,  lon: 13.41 },
  { country: "Greece",                                 continent: "Europe",   capital: "Athens",       lat: 37.98,  lon: 23.73 },
  { country: "Italy",                                  continent: "Europe",   capital: "Rome",         lat: 41.90,  lon: 12.50 },
  { country: "Portugal",                               continent: "Europe",   capital: "Lisbon",       lat: 38.72,  lon: -9.14 },
  { country: "Romania",                                continent: "Europe",   capital: "Bucharest",    lat: 44.43,  lon: 26.10 },
  { country: "Russian Federation (the)",               continent: "Europe",   capital: "Moscow",       lat: 55.76,  lon: 37.62 },
  { country: "Spain",                                  continent: "Europe",   capital: "Madrid",       lat: 40.42,  lon: -3.70 },
  { country: "Ukraine",                                continent: "Europe",   capital: "Kyiv",         lat: 50.45,  lon: 30.52 },
  { country: "United Kingdom of Great Britain and Northern Ireland (the)", continent: "Europe", capital: "London", lat: 51.51, lon: -0.13 },

  // ── Oceania ───────────────────────────────────────────────────────────────
  { country: "Australia",                              continent: "Oceania",  capital: "Canberra",     lat: -35.28, lon: 149.13 },
  { country: "Fiji",                                   continent: "Oceania",  capital: "Suva",         lat: -18.14, lon: 178.44 },
  { country: "New Zealand",                            continent: "Oceania",  capital: "Wellington",   lat: -41.29, lon: 174.78 },
  { country: "Papua New Guinea",                       continent: "Oceania",  capital: "Port Moresby", lat: -9.44,  lon: 147.18 },
]

/** Stable key for a capital row (used as the <select> option value). */
export function capitalKey(c: CapitalLocation): string {
  return `${c.country}__${c.capital}`
}

/** Human label for the dropdown, e.g. "Cairo, Egypt". */
export function capitalLabel(c: CapitalLocation): string {
  return `${c.capital}, ${c.country}`
}
