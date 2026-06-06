// Client Component for the standalone /analytics/timeseries page (Feature 9).
// Receives precomputed TimeSeriesData from the Server Component and renders a
// full-page ComposedChart with filters, slope badge, and insight callout.

"use client"

import { useMemo, useState } from "react"
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { S, Sf } from "@/lib/strings"
import { formatInt, formatUSDFromThousands } from "@/lib/format"
import { FilterBar } from "@/components/FilterBar"
import type { TimeSeriesData, TimeseriesDecadeEntry } from "@/types"

// ── constants ─────────────────────────────────────────────────────────────────

const DISASTER_COLORS: Record<string, string> = {
  Flood:                 "#2563eb",
  Storm:                 "#7c3aed",
  Earthquake:            "#dc2626",
  Wildfire:              "#ea580c",
  "Volcanic activity":   "#b45309",
  Landslide:             "#65a30d",
  Drought:               "#ca8a04",
  "Extreme temperature": "#0891b2",
}

const SLOPE_NOISE_FLOOR = 0.05
const GREY_THRESHOLD    = 10

// ── helpers ───────────────────────────────────────────────────────────────────

type TSMetric = "events" | "deaths" | "affected" | "damage_000usd"

interface RegResult { slope: number; intercept: number }

function linearRegression(ys: number[]): RegResult {
  const n = ys.length
  if (n < 2) return { slope: 0, intercept: ys[0] ?? 0 }
  let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0
  for (let i = 0; i < n; i++) {
    sumX  += i; sumY  += ys[i]
    sumXY += i * ys[i]; sumXX += i * i
  }
  const denom    = n * sumXX - sumX * sumX
  const slope    = denom === 0 ? 0 : (n * sumXY - sumX * sumY) / denom
  const intercept = (sumY - slope * sumX) / n
  return { slope, intercept }
}

function getMetricVal(r: TimeseriesDecadeEntry, m: TSMetric): number {
  const v = r[m as keyof TimeseriesDecadeEntry]
  return typeof v === "number" ? v : 0
}

// ── custom tooltip ─────────────────────────────────────────────────────────────
// Shows both series with brief labels explaining what each one is. The `any`
// types mirror Recharts' own untyped TooltipProps.

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function ChartTooltip({ active, payload, label, fmtValue }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 shadow text-xs min-w-[180px]">
      <p className="font-semibold text-slate-700 mb-1.5">{label}s</p>
      {payload.map((p: { name: string; value: number; color: string }) => (
        <div key={p.name} className="flex items-center gap-1.5 leading-5">
          <span className="h-2 w-2 shrink-0 rounded-sm" style={{ background: p.color }} />
          <span className="text-slate-500 truncate">{p.name}:</span>
          <span className="ml-auto font-medium tabular-nums text-slate-900 pl-2">
            {fmtValue(p.value)}
          </span>
        </div>
      ))}
      <p className="mt-2 text-[10px] text-slate-400 leading-snug">
        {S("timeseries.tooltip.note")}
      </p>
    </div>
  )
}

// ── component ─────────────────────────────────────────────────────────────────

export function TimeSeriesPageContent({ data }: { data: TimeSeriesData }) {
  const types = Object.keys(data.by_decade ?? {}).sort()

  const [pick,            setPick]            = useState<string>(types.includes("Flood") ? "Flood" : types[0])
  const [metric,          setMetric]          = useState<TSMetric>("events")
  const [filterContinent, setFilterContinent] = useState("All")

  // Continent options derived from the JSON (optional field; graceful if absent).
  const continentOptions = useMemo(() => {
    const keys = Object.keys(data.by_continent_decade ?? {}).sort()
    return [
      { value: "All", label: S("filter.all.continents") },
      ...keys.map((c) => ({ value: c, label: c })),
    ]
  }, [data.by_continent_decade])

  const hasContinents = continentOptions.length > 1

  // Series data — global or continent-filtered.
  const series: TimeseriesDecadeEntry[] = useMemo(
    () =>
      filterContinent === "All"
        ? (data.by_decade[pick] ?? [])
        : (data.by_continent_decade?.[filterContinent]?.[pick] ?? []),
    [data, pick, filterContinent],
  )

  const metricValues = series.map((r) => getMetricVal(r, metric))

  const { slope, intercept } = useMemo(
    () => linearRegression(metricValues),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pick, metric, filterContinent, metricValues.join(",")],
  )

  const meanVal = metricValues.length
    ? metricValues.reduce((a, b) => a + b, 0) / metricValues.length
    : 0

  const rows = series.map((r, i) => ({
    decade: r.decade,
    value:  getMetricVal(r, metric),
    trend:  Math.max(0, intercept + slope * i),
    isLow:  metric === "events" && (r.events ?? 0) < GREY_THRESHOLD,
  }))

  // ── slope badge ──
  let slopeLabel: string
  if (meanVal > 0 && Math.abs(slope) / meanVal < SLOPE_NOISE_FLOOR) {
    slopeLabel = S("analytics.timeseries.slope.stable")
  } else if (slope > 0) {
    slopeLabel = S("analytics.timeseries.slope.increasing")
  } else {
    slopeLabel = S("analytics.timeseries.slope.decreasing")
  }
  const slopeBadgeColor =
    slopeLabel === S("analytics.timeseries.slope.increasing")
      ? "bg-green-100 text-green-800 border-green-200"
      : slopeLabel === S("analytics.timeseries.slope.decreasing")
      ? "bg-red-100 text-red-800 border-red-200"
      : "bg-slate-100 text-slate-700 border-slate-200"

  // ── insight callout — metric-aware, compares 1980 vs 2000 ──
  // Uses the selected metric (not hardcoded events). Skips if either decade
  // has no data (common for deaths/damage in sparse decades).
  const metricOptions = [
    { value: "events",        label: S("filter.metric.events") },
    { value: "deaths",        label: S("filter.metric.deaths") },
    { value: "affected",      label: S("filter.metric.affected") },
    { value: "damage_000usd", label: S("filter.metric.damage") },
  ]
  const metricLabel = metricOptions.find((o) => o.value === metric)?.label ?? S("filter.metric.events")

  const dec1980 = series.find((r) => r.decade === 1980)
  const dec2000 = series.find((r) => r.decade === 2000)
  const val1    = dec1980 ? getMetricVal(dec1980, metric) : 0
  const val2    = dec2000 ? getMetricVal(dec2000, metric) : 0

  let insightTitle = ""
  let insightBody  = ""
  if (val1 > 0 && val2 > 0) {
    const ratio = val2 / val1
    const dir   = ratio >= 1.15 ? "up" : ratio <= 0.87 ? "down" : "flat"
    insightTitle = Sf(`timeseries.insight.title.${dir}`, { type: pick, metric: metricLabel })
    insightBody  = Sf(`timeseries.insight.body.${dir}`, {
      type:     pick,
      metric:   metricLabel,
      n1:       val1,
      n2:       val2,
      multiple: ratio.toFixed(1),
    })
  } else if (dec1980 && dec2000) {
    insightBody = Sf("timeseries.insight.none", { type: pick, metric: metricLabel })
  }

  // ── chart helpers ──
  const yAxisLabel: Record<TSMetric, string> = {
    events:        S("analytics.timeseries.eventsAxis"),
    deaths:        S("filter.metric.deaths"),
    affected:      S("filter.metric.affected"),
    damage_000usd: S("filter.metric.damage"),
  }

  const fmtValue = (v: number) =>
    metric === "damage_000usd" ? formatUSDFromThousands(v) : formatInt(v)

  const recordedLabel = Sf("analytics.timeseries.recordedLabel", { metric: metricLabel })
  const trendLabel    = S("analytics.timeseries.trendLabel.short")

  // Continent context note shown in insight area when a specific continent is selected.
  const contextNote = filterContinent !== "All"
    ? ` (${filterContinent} only)`
    : ""

  return (
    <div className="space-y-5">
      {/* Insight callout */}
      {insightBody && (
        <div className="rounded-lg border border-orange-200 bg-orange-50 px-4 py-3">
          {insightTitle && (
            <p className="text-sm font-semibold text-slate-800">{insightTitle}{contextNote}</p>
          )}
          <p className={insightTitle ? "mt-0.5 text-sm text-slate-700" : "text-sm text-slate-700"}>
            {insightBody}
          </p>
        </div>
      )}

      {/* Chart card */}
      <section className="rounded-xl border border-slate-200 bg-white p-6">
        <h2 className="text-lg font-semibold text-slate-800">
          {S("analytics.timeseries.title")}
        </h2>
        <p className="mt-1 text-xs text-slate-500 max-w-2xl">
          {S("analytics.timeseries.help")}
        </p>

        {/* Filters + slope badge */}
        <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
          <FilterBar
            filters={[
              {
                id:      "ts-page-type",
                label:   S("filter.label.disasterType"),
                options: types.map((t) => ({ value: t, label: t })),
                value:   pick,
                onChange: setPick,
              },
              {
                id:      "ts-page-metric",
                label:   S("filter.label.metric"),
                options: metricOptions,
                value:   metric,
                onChange: (v) => setMetric(v as TSMetric),
              },
              ...(hasContinents ? [{
                id:      "ts-page-continent",
                label:   S("filter.label.continent"),
                options: continentOptions,
                value:   filterContinent,
                onChange: setFilterContinent,
              }] : []),
            ]}
          />

          {/* Slope badge — right-aligned */}
          <div className="flex items-center gap-2 self-end pb-1">
            <span
              className={`inline-flex items-center rounded-full border px-3 py-1 text-sm font-semibold ${slopeBadgeColor}`}
            >
              {slopeLabel}
            </span>
            <span className="text-[11px] text-slate-500 tabular-nums">
              {Sf("analytics.timeseries.slope.full", { slope: slope.toFixed(1) })}
            </span>
          </div>
        </div>

        {/* Main chart */}
        <div className="mt-5 h-[540px]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} margin={{ top: 8, right: 24, bottom: 8, left: 16 }}>
              <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
              <XAxis dataKey="decade" tick={{ fontSize: 12, fill: "#475569" }} />
              <YAxis
                tick={{ fontSize: 12, fill: "#475569" }}
                tickFormatter={
                  metric === "damage_000usd" ? formatUSDFromThousands : formatInt
                }
                label={{
                  value:    yAxisLabel[metric],
                  angle:    -90,
                  position: "insideLeft",
                  style:    { fontSize: 12, fill: "#64748b" },
                }}
              />
              {/* Custom tooltip explains both series to non-expert readers */}
              <Tooltip content={(props) => <ChartTooltip {...props} fmtValue={fmtValue} />} />
              <Legend wrapperStyle={{ fontSize: 13 }} />

              {metric === "events" && (
                <ReferenceLine y={GREY_THRESHOLD} stroke="#cbd5e1" strokeDasharray="4 4" />
              )}

              <Bar
                dataKey="value"
                name={recordedLabel}
                radius={[4, 4, 0, 0]}
              >
                {rows.map((r, i) => (
                  <Cell
                    key={i}
                    fill={r.isLow ? "#cbd5e1" : (DISASTER_COLORS[pick] ?? "#0f172a")}
                    fillOpacity={r.isLow ? 0.5 : 1}
                  />
                ))}
              </Bar>

              <Line
                type="monotone"
                dataKey="trend"
                name={trendLabel}
                stroke="#0f172a"
                strokeWidth={2}
                dot={false}
              />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        {metric === "events" && (
          <p className="mt-2 text-[11px] text-slate-400">
            {S("analytics.timeseries.greyNote")}
          </p>
        )}
      </section>
    </div>
  )
}
