// Reusable prediction result card.
// Used by:
//   - dashboard/page.tsx          (single prediction, passes timeseriesData)
//   - dashboard/forecast/page.tsx (expanded card — no mini chart)
//
// Renders every Feature-1 field. Coverage disclaimers for Injured + Damage
// are NON-OPTIONAL per CLAUDE.md. The forecast variant adds the binding
// Feature-10 disclaimer beneath the card via the `forecastDisclaimer` prop.

"use client"

import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { S, Sf } from "@/lib/strings"
import { formatInt, formatUSDFromThousands } from "@/lib/format"
import { SeverityBadge } from "@/components/SeverityBadge"
import { RecommendationsPanel } from "@/components/RecommendationsPanel"
import type { PredictionResult, TimeSeriesData } from "@/types"

const MONTH_NAMES = [
  "Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec",
]

const GREY_THRESHOLD = 10

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

function MiniHistoricalChart({
  disasterType,
  data,
}: {
  disasterType: string
  data: TimeSeriesData
}) {
  const decades = data.by_decade[disasterType] ?? []
  if (decades.length === 0) return null

  const rows = decades.map((r) => ({
    decade: r.decade,
    events: r.events ?? 0,
    isLow: (r.events ?? 0) < GREY_THRESHOLD,
  }))

  const barColor = DISASTER_COLORS[disasterType] ?? "#0f172a"

  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-700">
        {Sf("result.miniChart.title", { type: disasterType })}
      </h3>
      <div className="mt-2 h-[120px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
            <XAxis
              dataKey="decade"
              tick={{ fontSize: 9, fill: "#94a3b8" }}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              tick={{ fontSize: 9, fill: "#94a3b8" }}
              tickLine={false}
              axisLine={false}
              width={32}
            />
            <Tooltip
              contentStyle={{ fontSize: 11 }}
              formatter={(v: number) => [formatInt(v), "Events"]}
            />
            <Bar dataKey="events" radius={[2, 2, 0, 0]}>
              {rows.map((r, i) => (
                <Cell
                  key={i}
                  fill={r.isLow ? "#cbd5e1" : barColor}
                  fillOpacity={r.isLow ? 0.5 : 1}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

export function PredictionResultCard({
  result,
  forecastDisclaimer = false,
  headerSuffix,
  timeseriesData,
}: {
  result: PredictionResult
  forecastDisclaimer?: boolean
  headerSuffix?: React.ReactNode
  timeseriesData?: TimeSeriesData
}) {
  const dataSourceLine =
    result.data_source === "country"
      ? Sf("result.dataSource.country", { country: result.country_used ?? "—" })
      : result.data_source === "region"
        ? Sf("result.dataSource.region", { n: formatInt(result.n_events) })
        : Sf("result.dataSource.global", { n: formatInt(result.n_events) })

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">
            {result.disaster_type}
            {headerSuffix && (
              <span className="ml-2 text-xs font-normal text-slate-500">
                {headerSuffix}
              </span>
            )}
          </h2>
          <p className="text-xs text-slate-500">
            {dataSourceLine}
            {result.data_quality === "limited" && (
              <span className="ml-1 text-amber-700">
                {S("result.dataQuality.limited")}
              </span>
            )}
          </p>
        </div>
        <SeverityBadge level={result.severity_level} />
      </header>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label={S("result.probability.label")} value={`${(result.probability_score * 100).toFixed(1)}%`} />
        <Stat label={S("result.riskScore.label")}   value={result.risk_score.toFixed(1)} />
        <Stat label={S("result.deaths")}            value={formatInt(result.estimated_deaths)} />
        <Stat label={S("result.affected")}          value={formatInt(result.estimated_affected)} />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="rounded-lg border border-slate-200 p-3">
          <div className="text-xs text-slate-500">{S("result.injuries")}</div>
          <div className="text-lg font-semibold text-slate-900 tabular-nums">
            {formatInt(result.estimated_injuries)}
          </div>
          <p className="mt-1 text-[11px] text-slate-400 leading-snug">
            {S("result.coverage.injuries")}
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 p-3">
          <div className="text-xs text-slate-500">{S("result.damage")}</div>
          <div className="text-lg font-semibold text-slate-900 tabular-nums">
            {formatUSDFromThousands(result.estimated_damage_usd)}
          </div>
          <p className="mt-1 text-[11px] text-slate-400 leading-snug">
            {S("result.coverage.damage")}
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 p-3">
          <div className="text-xs text-slate-500">{S("result.uninsured")}</div>
          <div className="text-lg font-semibold text-slate-900 tabular-nums">
            {formatUSDFromThousands(result.uninsured_loss_usd)}
          </div>
        </div>
      </div>

      {result.shap_explanation.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-slate-700">
            {S("result.shap.title")}
          </h3>
          <ul className="mt-2 space-y-1.5">
            {result.shap_explanation.map((f, i) => (
              <li key={i} className="flex items-center gap-3 text-xs">
                <span className="w-32 shrink-0 text-slate-600 truncate">{f.feature}</span>
                <div className="flex-1 h-2 bg-slate-100 rounded overflow-hidden">
                  <div
                    className="h-full bg-slate-700"
                    style={{ width: `${Math.min(100, f.contribution_pct)}%` }}
                  />
                </div>
                <span className="w-12 text-right tabular-nums text-slate-700">
                  {f.contribution_pct.toFixed(1)}%
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {timeseriesData && (
        <MiniHistoricalChart
          disasterType={result.disaster_type}
          data={timeseriesData}
        />
      )}

      {result.secondary_disaster_warning && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
          <p className="text-xs font-semibold text-amber-900">
            {S("result.secondary.title")}
          </p>
          <p className="mt-1 text-xs text-amber-800">
            {result.secondary_disaster_warning}
          </p>
        </div>
      )}

      {result.seasonal_peak_months.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-slate-700">
            {S("result.seasonal.title")}
          </h3>
          <div className="mt-2 flex gap-1">
            {MONTH_NAMES.map((m, i) => {
              const active = result.seasonal_peak_months.includes(i + 1)
              return (
                <span
                  key={i}
                  className={`text-[10px] w-8 h-8 rounded flex items-center justify-center font-medium ${
                    active
                      ? "bg-orange-500 text-white"
                      : "bg-slate-100 text-slate-400"
                  }`}
                >
                  {m}
                </span>
              )
            })}
          </div>
        </div>
      )}

      <RecommendationsPanel items={result.recommendations} />

      <p className="text-[10px] text-slate-400 tabular-nums">
        {Sf("result.modelVersion", { version: result.model_version })}
      </p>

      {forecastDisclaimer && (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-800">
          {S("forecast.disclaimer")}
        </p>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-lg font-semibold text-slate-900 tabular-nums">{value}</div>
    </div>
  )
}
