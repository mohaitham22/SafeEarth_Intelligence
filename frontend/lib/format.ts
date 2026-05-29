// Number / currency formatting helpers — must follow emdat-lookup.md exactly.
// `damage_usd` is stored as THOUSANDS USD on the backend response — multiply
// by 1000 before formatting.

export function formatInt(n: number): string {
  if (!Number.isFinite(n)) return "—"
  return new Intl.NumberFormat("en-US").format(Math.round(n))
}

export function formatCompactInt(n: number): string {
  if (!Number.isFinite(n)) return "—"
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000)     return `${(n / 1_000).toFixed(1)}K`
  return String(Math.round(n))
}

/** Backend stores damage as thousands USD. Pass that raw value here. */
export function formatUSDFromThousands(thousands: number): string {
  if (!Number.isFinite(thousands)) return "—"
  const full = thousands * 1000
  if (full >= 1_000_000_000) return `$${(full / 1_000_000_000).toFixed(1)}B`
  if (full >= 1_000_000)     return `$${(full / 1_000_000).toFixed(1)}M`
  if (full >= 1_000)         return `$${(full / 1_000).toFixed(0)}K`
  return `$${full}`
}

export function formatPct(v: number, fractionDigits = 1): string {
  if (!Number.isFinite(v)) return "—"
  return `${(v * 100).toFixed(fractionDigits)}%`
}
