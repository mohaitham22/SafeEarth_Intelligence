# SKILL: EM-DAT Impact Lookup Usage

Read this file completely before writing any code that retrieves impact statistics.
This applies to: predictions, alerts, email content, and any UI displaying deaths/injuries/affected/damage numbers.

---

## The Golden Rule

**Never hardcode impact numbers.**
**Never compute averages from the dataset at runtime.**
**Never query the PostgreSQL database for impact stats.**

Always and only call `resolve_impact_stats()` from `backend/ml/emdat_lookup.py`.
This function handles the 3-tier lookup (country → region → global) automatically.

---

## Critical: Disaster Type Names

The disaster type strings used in emdat_stats.json must match EXACTLY.
These are the only valid values — copy them exactly including capitalisation:

```python
VALID_DISASTER_TYPES = [
    "Flood",
    "Storm",
    "Earthquake",
    "Wildfire",
    "Volcanic activity",   # lowercase 'a' in activity
    "Landslide",
    "Drought",
    "Extreme temperature", # lowercase 't' — NO trailing space
]
```

**NEVER use:**
- `"Extreme temperature "` — trailing space (CSV bug — already stripped in generate script)
- `"Volcanic Activity"` — capital A is wrong
- `"flood"` — lowercase is wrong
- `"Flash Flood"` — use "Flood" only (subtypes map to parent type)

---

## How to Call resolve_impact_stats()

```python
from ml.emdat_lookup import resolve_impact_stats

# Without country (uses global median)
result = resolve_impact_stats(disaster_type="Flood")

# With country (triggers 3-tier lookup)
result = resolve_impact_stats(disaster_type="Flood", country="Egypt")

# Returns always this exact shape:
{
    "median_deaths": 16,
    "median_injuries": 30,
    "median_affected": 11000,
    "median_damage_000usd": 49500,
    "n_events": 5551,
    "deaths_coverage": 0.73,
    "injuries_coverage": 0.26,
    "affected_coverage": 0.73,
    "damage_coverage": 0.33,
    "data_source": "global",      # "country", "region", or "global"
    "country_used": None,         # or "Egypt" if country was provided
}
```

---

## The 3-Tier Logic (Already Implemented — Just Know It)

```
resolve_impact_stats("Flood", country="Egypt")
→
── Tier 1: Does emdat_stats["by_country"]["Egypt"]["Flood"] exist with n_events ≥ 5?
│   YES → return country stats, data_source="country"
│   NO  →
│
── Tier 2: Look up Egypt's EM-DAT region → "Northern Africa"
│          Does emdat_stats["by_region"]["Northern Africa"]["Flood"] exist with n_events ≥ 5?
│   YES → return region stats, data_source="region"
│   NO  →
│
── Tier 3: Return emdat_stats["global"]["Flood"]
           data_source="global"
```

---

## How to Compute Derived Metrics

```python
impact = resolve_impact_stats(disaster_type, country=country)

# Convert damage from thousands USD to full USD
damage_usd = impact["median_damage_000usd"] * 1000

# Uninsured loss
from ml.emdat_lookup import INSURANCE_RATIOS
insurance_ratio = INSURANCE_RATIOS.get(disaster_type, 0.3)
uninsured_loss_usd = int(damage_usd * (1 - insurance_ratio))

# Risk score (0–100 composite)
def compute_risk_score(deaths, affected, damage_usd, probability_score, disaster_type):
    P99 = EMDAT_P99[disaster_type]  # loaded at startup from emdat_stats.json
    norm_deaths   = min(deaths    / P99["deaths"],   1.0)
    norm_affected = min(affected  / P99["affected"], 1.0)
    norm_damage   = min(damage_usd / P99["damage"],  1.0)
    score = (norm_deaths * 0.35 + norm_affected * 0.30 +
             norm_damage * 0.20 + probability_score  * 0.15)
    return round(score * 100, 1)
```

---

## Data Confidence Labels

```python
def get_data_confidence(coverage: float) -> str:
    if coverage >= 0.60:
        return "high"      # show number normally
    elif coverage >= 0.30:
        return "moderate"  # show number with disclaimer
    else:
        return "low"       # do not display this metric at all

# Coverage reference (approximate):
# deaths_coverage:   0.42–0.95  (mostly high)
# injuries_coverage: 0.04–0.34  (mostly moderate/low)
# affected_coverage: 0.30–0.75  (mostly moderate/high)
# damage_coverage:   0.11–0.50  (mostly moderate)
```

---

## Frontend: How to Display Impact Numbers

```tsx
// 1. Always show data_source badge
const sourceLabel = {
  country: "Based on historical events in this country",
  region:  "Based on regional historical average",
  global:  "Based on global historical average",
}[result.data_source]

// 2. Per-metric confidence display
function MetricDisplay({ value, confidence, label, unit }) {
  if (confidence === "low") return null  // never render low-confidence metrics

  return (
    <div>
      <span>{formatNumber(value)} {unit}</span>
      <span className="label">{label}</span>
      {confidence === "moderate" && (
        <span className="disclaimer text-xs text-slate-400">
          Estimate based on limited records — treat with caution
        </span>
      )}
    </div>
  )
}

// 3. Format large numbers
function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n/1_000_000).toFixed(1)}M`
  if (n >= 1_000)     return `${(n/1_000).toFixed(1)}K`
  return n.toString()
}

// 4. Format currency (damage stored as thousands USD)
function formatUSD(thousands: number): string {
  const full = thousands * 1000
  if (full >= 1_000_000_000) return `$${(full/1_000_000_000).toFixed(1)}B`
  if (full >= 1_000_000)     return `$${(full/1_000_000).toFixed(1)}M`
  return `$${(full/1_000).toFixed(0)}K`
}
```

---

## Secondary Disaster Warnings

```python
from ml.emdat_lookup import SECONDARY_DISASTERS

def get_secondary_warning(disaster_type: str) -> str | None:
    associations = SECONDARY_DISASTERS.get(disaster_type, [])
    if not associations:
        return None
    top = associations[0]  # sorted by count descending
    return (
        f"{disaster_type}s historically trigger {top['type'].lower()}s "
        f"({top['count']:,} recorded co-occurrences in EM-DAT data)"
    )
# "Earthquakes historically trigger landslides (1,217 recorded co-occurrences)"
```

---

## Seasonal Peak Months

```python
from ml.emdat_lookup import SEASONAL_PEAKS

def get_seasonal_peaks(disaster_type: str) -> list[int]:
    return SEASONAL_PEAKS.get(disaster_type, [])
# Returns month numbers: "Flood" → [7, 8, 9], "Earthquake" → []
```

Frontend 12-month strip:
```tsx
const MONTHS = ["J","F","M","A","M","J","J","A","S","O","N","D"]

function SeasonalStrip({ peakMonths }: { peakMonths: number[] }) {
  return (
    <div className="flex gap-1">
      {MONTHS.map((m, i) => (
        <div key={i}
          className={`w-6 h-6 text-xs flex items-center justify-center rounded
            ${peakMonths.includes(i+1) ? "bg-orange-500 text-white" : "bg-gray-100 text-gray-400"}`}>
          {m}
        </div>
      ))}
    </div>
  )
}
```

---

## emdat_lookup.py — Load at Module Level (startup only)

```python
# backend/ml/emdat_lookup.py
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data" / "generated"

with open(DATA_DIR / "emdat_stats.json") as f:
    EMDAT_STATS = json.load(f)

with open(DATA_DIR / "secondary_disasters.json") as f:
    SECONDARY_DISASTERS = json.load(f)

with open(DATA_DIR / "seasonal_peaks.json") as f:
    SEASONAL_PEAKS = json.load(f)

with open(DATA_DIR / "insurance_ratios.json") as f:
    INSURANCE_RATIOS = json.load(f)

with open(DATA_DIR / "trends.json") as f:
    TRENDS = json.load(f)

with open(DATA_DIR / "continent_stats.json") as f:
    CONTINENT_STATS = json.load(f)
```

**Never load these inside a function. Never reload per request.**

---

## Checklist Before Using Impact Data Anywhere

- [ ] Called resolve_impact_stats() — not a manual groupby or hardcoded number
- [ ] Disaster type string matches exactly one of the 8 VALID_DISASTER_TYPES
- [ ] disaster_type.strip() called before any lookup or comparison
- [ ] data_source field included in API response
- [ ] n_events field included in API response
- [ ] data_confidence computed per metric and included in response
- [ ] Low-confidence metrics not displayed in UI
- [ ] Moderate-confidence metrics shown with disclaimer in UI
- [ ] damage values multiplied by 1000 before formatting (stored as thousands)
- [ ] Secondary disaster warning checked and included if applicable
- [ ] Seasonal peak months fetched and included in response
