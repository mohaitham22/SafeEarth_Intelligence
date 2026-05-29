// Client Component for the standalone /analytics/timeseries page (Feature 9).
// Receives precomputed TimeSeriesData from the Server Component and renders a
// full-page ComposedChart with filters, slope badge, and flood insight callout.
// Kept separate from AnalyticsPanels so the analytics page tabs are unchanged.

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

// |slope| < 5 % of mean ⇒ Stable  (scales with the metric magnitude)
const SLOPE_NOISE_FLOOR = 0.05
// Decades with fewer than 10 events are greyed out on the events metric
const GREY_THRESHOLD = 10

// ── helpers ───────────────────────────────────────────────────────────────────

type TSMetric = "events" | "deaths" | "affected" | "damage_000usd"

interface RegResult { slope: number; intercept: number }

function linearRegression(ys: number[]): RegResult {
  const n = ys.length
  if (n < 2) return { slope: 0, intercept: ys[0] ?? 0 }
  let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0
  for (let i = 0; i < n; i++) {
    sumX  += i
    sumY  += ys[i]
    sumXY += i * ys[i]
    sumXX += i * i
  }
  const denom = n * sumXX - sumX * sumX
  const slope     = denom === 0 ? 0 : (n * sumXY - sumX * sumY) / denom
  const intercept = (sumY - slope * sumX) / n
  return { slope, intercept }
}

function getMetricVal(r: TimeseriesDecadeEntry, m: TSMetric): number {
  const v = r[m as keyof TimeseriesDecadeEntry]
  return typeof v === "number" ? v : 0
}

// ── component ─────────────────────────────────────────────────────────────────

export function TimeSeriesPageContent({ data }: { data: TimeSeriesData }) {
  const types = Object.keys(data.by_decade ?? {}).sort()

  const [pick,   setPick]   = useState<string>(types.includes("Flood") ? "Flood" : types[0])
  const [metric, setMetric] = useState<TSMetric>("events")

  const series       = data.by_decade[pick] ?? []
  const metricValues = series.map((r) => getMetricVal(r, metric))

  const { slope, intercept } = useMemo(
    () => linearRegression(metricValues),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pick, metric, metricValues.join(",")],
  )

  const meanVal = metricValues.length
    ? metricValues.reduce((a, b) => a + b, 0) / metricValues.length
    : 0

  const rows = series.map((r, i) => ({
    decade: r.decade,
    value:  getMetricVal(r, metric),
    trend:  Math.max(0, intercept + slope * i),
    // grey-out only on the events metric — sparse decades have < 10 events
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
  // Increasing = green, Decreasing = red, Stable = slate  (per Feature 9 spec)
  const slopeBadgeColor =
    slopeLabel === S("analytics.timeseries.slope.increasing")
      ? "bg-green-100 text-green-800 border-green-200"
      : slopeLabel === S("analytics.timeseries.slope.decreasing")
      ? "bg-red-100 text-red-800 border-red-200"
      : "bg-slate-100 text-slate-700 border-slate-200"

  // ── flood insight callout (always visible, from live data) ──
  const floodDecades = data.by_decade["Flood"] ?? []
  const dec1980 = floodDecades.find((r) => r.decade === 1980)
  const dec2000 = floodDecades.find((r) => r.decade === 2000)
  const insightBody =
    dec1980 && dec2000 && dec1980.events > 0 && dec2000.events > 0
      ? Sf("timeseries.insight.body", {
          n80:      dec1980.events,
          n00:      dec2000.events,
          multiple: (dec2000.events / dec1980.events).toFixed(1),
        })
      : ""

  // ── filter options ──
  const typeOptions = types.map((t) => ({ value: t, label: t }))

  const metricOptions = [
    { value: "events",        label: S("filter.metric.events") },
    { value: "deaths",        label: S("filter.metric.deaths") },
    { value: "affected",      label: S("filter.metric.affected") },
    { value: "damage_000usd", label: S("filter.metric.damage") },
  ]

  const yAxisLabel: Record<TSMetric, string> = {
    events:        S("analytics.timeseries.eventsAxis"),
    deaths:        S("filter.metric.deaths"),
    affected:      S("filter.metric.affected"),
    damage_000usd: S("filter.metric.damage"),
  }

  const fmtValue = (v: number) =>
    metric === "damage_000usd" ? formatUSDFromThousands(v) : formatInt(v)

  return (
    <div className="space-y-5">
      {/* Flood insight callout — computed from live data, always visible */}
      {insightBody && (
        <div className="rounded-lg border border-orange-200 bg-orange-50 px-4 py-3">
          <p className="text-sm font-semibold text-slate-800">
            {S("timeseries.insight.title")}
          </p>
          <p className="mt-0.5 text-sm text-slate-700">{insightBody}</p>
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
                options: typeOptions,
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

        {/* Main chart — taller than the tab version for better readability */}
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
              <Tooltip
                contentStyle={{ fontSize: 13 }}
                formatter={(v: number, name: string) => [
                  fmtValue(v),
                  name === "trend"
                    ? S("analytics.timeseries.trendLabel")
                    : S("analytics.timeseries.eventsLabel"),
                ]}
              />
              <Legend wrapperStyle={{ fontSize: 13 }} />

              {/* Reference line — marks the grey-out threshold */}
              {metric === "events" && (
                <ReferenceLine y={GREY_THRESHOLD} stroke="#cbd5e1" strokeDasharray="4 4" />
              )}

              <Bar
                dataKey="value"
                name={S("analytics.timeseries.eventsLabel")}
                radius={[4, 4, 0, 0]}
              >
                {rows.map((r, i) => (
                  <Cell
                    key={i}
                    fill={
                      r.isLow
                        ? "#cbd5e1"
                        : (DISASTER_COLORS[pick] ?? "#0f172a")
                    }
                    fillOpacity={r.isLow ? 0.5 : 1}
                  />
                ))}
              </Bar>

              <Line
                type="monotone"
                dataKey="trend"
                name={S("analytics.timeseries.trendLabel")}
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
