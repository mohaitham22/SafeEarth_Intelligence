"""
Lightweight, dependency-free geo helpers for the backend.

continent_from_latlon: approximate one of the 5 EM-DAT continents from coordinates.
A subscription stores only region_name + lat/lon, but the classifier needs a
`continent` feature. This gives a sensible value for the alert-dispatch risk
evaluation. Intentionally coarse — the classifier's unseen-category encoder
tolerates an imperfect continent. Mirrors frontend/lib/geo.ts so the two agree.
"""
from __future__ import annotations

# One of: "Africa" | "Americas" | "Asia" | "Europe" | "Oceania"


def continent_from_latlon(lat: float, lon: float) -> str:
    # Americas: the western-hemisphere longitudes.
    if -170 <= lon <= -30:
        return "Americas"

    # Oceania: Australia / NZ / Pacific island band.
    if lat <= 0 and 110 <= lon <= 180:
        return "Oceania"

    # Europe: roughly north of the Mediterranean, west of the Urals.
    if lat >= 36 and -25 <= lon <= 60:
        return "Europe"

    # Africa: the Africa box (also covers the Middle East edge acceptably).
    if -38 <= lat < 36 and -20 <= lon <= 52:
        return "Africa"

    # Everything else in the eastern hemisphere → Asia.
    return "Asia"
