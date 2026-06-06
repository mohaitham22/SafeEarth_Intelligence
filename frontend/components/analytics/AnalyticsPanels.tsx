// Client Component wrapping all four analytics charts.
// Receives precomputed data as props from the Server Component page.
// Recharts requires a Client Component because ResponsiveContainer depends on
// the browser's ResizeObserver.

"use client"

import { useMemo, useState } from "react"
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { S, Sf } from "@/lib/strings"
import { formatInt, formatUSDFromThousands } from "@/lib/format"
import { FilterBar } from "@/components/FilterBar"
import type {
  ContinentStats,
  InsuranceRatios,
  TimeSeriesData,
  TimeseriesDecadeEntry,
  TrendsData,
} from "@/types"

const DISASTER_COLORS: Record<string, string> = {
  Flood:                "#2563eb",
  Storm:                "#7c3aed",
  Earthquake:           "#dc2626",
  Wildfire:             "#ea580c",
  "Volcanic activity":  "#b45309",
  Landslide:            "#65a30d",
  Drought:              "#ca8a04",
  "Extreme temperature":"#0891b2",
}

const TREND_DECADES = [1950, 1960, 1970, 1980, 1990, 2000, 2010, 2020]

type TabId = "trends" | "continents" | "insurance" | "timeseries"

interface Props {
  trends:     TrendsData
  continents: ContinentStats
  insurance:  InsuranceRatios
  timeseries: TimeSeriesData
}

export function AnalyticsPanels(props: Props) {
  const [tab, setTab] = useState<TabId>("trends")

  return (
    <div>
      <Tabs value={tab} onChange={setTab} />
      <div className="mt-6">
        {tab === "trends"     && <TrendsTab data={props.trends} />}
        {tab === "continents" && <ContinentsTab data={props.continents} />}
        {tab === "insurance"  && <InsuranceTab data={props.insurance} />}
        {tab === "timeseries" && <TimeSeriesTab data={props.timeseries} />}
      </div>
    </div>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// Tabs

function Tabs({ value, onChange }: { value: TabId; onChange: (t: TabId) => void }) {
  const items: { id: TabId; label: string }[] = [
    { id: "trends",     label: S("analytics.tab.trends") },
    { id: "continents", label: S("analytics.tab.continents") },
    { id: "insurance",  label: S("analytics.tab.insurance") },
    { id: "timeseries", label: S("analytics.tab.timeseries") },
  ]
  return (
    <nav className="border-b border-slate-200" role="tablist">
      <ul className="flex flex-wrap gap-1">
        {items.map((it) => {
          const active = value === it.id
          return (
            <li key={it.id}>
              <button
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => onChange(it.id)}
                className={`px-3 py-2 text-sm border-b-2 -mb-px ${
                  active
                    ? "border-slate-800 text-slate-900 font-medium"
                    : "border-transparent text-slate-500 hover:text-slate-700"
                }`}
              >
                {it.label}
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// 1. Trends tab — LineChart, one line per disaster type
//    Filters: Disaster Type (All | specific), From Decade, To Decade

function TrendsTab({ data }: { data: TrendsData }) {
  const decades = (data.decades ?? TREND_DECADES) as number[]
  const types   = Object.keys(data).filter((k) => k !== "decades").sort()

  const [filterType, setFilterType] = useState("All")
  const [filterFrom, setFilterFrom] = useState(String(decades[0] ?? 1950))
  const [filterTo,   setFilterTo]   = useState(String(decades[decades.length - 1] ?? 2020))

  const fromNum = Number(filterFrom)
  const toNum   = Number(filterTo)

  // Rows include all types so recharts data shape stays stable; which <Line>
  // elements are rendered controls what's visible.
  const rows = useMemo(
    () =>
      decades
        .filter((d) => d >= fromNum && d <= toNum)
        .map((d) => {
          const i   = decades.indexOf(d)
          const row: Record<string, number> = { decade: d }
          for (const t of types) {
            const arr = (data as TrendsData)[t]
            if (Array.isArray(arr) && typeof arr[i] === "number") row[t] = arr[i]
          }
          return row
        }),
    [data, decades, types, fromNum, toNum],
  )

  const visibleTypes = filterType === "All" ? types : types.filter((t) => t === filterType)

  // Live insight — compares the two endpoints of the selected date range.
  // "All" sums across every type; specific type uses that type's data.
  // Skipped when the two endpoints are the same decade or either value is 0.
  const decadeA = Number(filterFrom)
  const decadeB = Number(filterTo)
  const idxA    = decades.indexOf(decadeA)
  const idxB    = decades.indexOf(decadeB)

  let insightTitle = ""
  let insightBody  = ""
  if (idxA !== -1 && idxB !== -1 && idxA !== idxB) {
    let n1: number
    let n2: number
    const isAll = filterType === "All"

    if (isAll) {
      // Sum all types at each endpoint.
      n1 = types.reduce((s, t) => {
        const arr = (data as TrendsData)[t]
        return s + (Array.isArray(arr) && typeof arr[idxA] === "number" ? arr[idxA] : 0)
      }, 0)
      n2 = types.reduce((s, t) => {
        const arr = (data as TrendsData)[t]
        return s + (Array.isArray(arr) && typeof arr[idxB] === "number" ? arr[idxB] : 0)
      }, 0)
    } else {
      const arr = (data as TrendsData)[filterType] as number[] | undefined
      n1 = Array.isArray(arr) && typeof arr[idxA] === "number" ? arr[idxA] : 0
      n2 = Array.isArray(arr) && typeof arr[idxB] === "number" ? arr[idxB] : 0
    }

    if (n1 > 0 && n2 > 0) {
      const ratio = n2 / n1
      const dir   = ratio >= 1.15 ? "up" : ratio <= 0.87 ? "down" : "flat"
      const pfx   = isAll ? "analytics.trends.insightTitle.all" : "analytics.trends.insightTitle"
      const bpfx  = isAll ? "analytics.trends.insightBody.all"  : "analytics.trends.insightBody"
      insightTitle = isAll
        ? S(`${pfx}.${dir}`)
        : Sf(`${pfx}.${dir}`, { type: filterType })
      insightBody = Sf(`${bpfx}.${dir}`, {
        type:     filterType,
        n1,
        n2,
        d1:       decadeA,
        d2:       decadeB,
        multiple: ratio.toFixed(1),
      })
    }
  }

  const typeOptions = [
    { value: "All", label: S("filter.all.types") },
    ...types.map((t) => ({ value: t, label: t })),
  ]
  const fromOptions = decades.map((d) => ({ value: String(d), label: String(d) }))
  const toOptions   = decades.map((d) => ({ value: String(d), label: String(d) }))

  return (
    <ChartCard
      title={S("analytics.trends.title")}
      help={S("analytics.trends.help")}
    >
      <div className="mt-3">
        <FilterBar
          filters={[
            {
              id: "tr-type", label: S("filter.label.disasterType"),
              options: typeOptions, value: filterType, onChange: setFilterType,
            },
            {
              id: "tr-from", label: S("filter.label.fromDecade"),
              options: fromOptions, value: filterFrom,
              onChange: (v) => {
                setFilterFrom(v)
                if (Number(v) > toNum) setFilterTo(v)
              },
            },
            {
              id: "tr-to", label: S("filter.label.toDecade"),
              options: toOptions, value: filterTo,
              onChange: (v) => {
                setFilterTo(v)
                if (Number(v) < fromNum) setFilterFrom(v)
              },
            },
          ]}
        />
      </div>
      {insightBody && (
        <Insight title={insightTitle} body={insightBody} tone="orange" />
      )}
      <div className="h-[380px] mt-4">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
            <XAxis dataKey="decade" tick={{ fontSize: 11, fill: "#475569" }} />
            <YAxis tick={{ fontSize: 11, fill: "#475569" }} />
            <Tooltip contentStyle={{ fontSize: 12 }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {visibleTypes.map((t) => (
              <Line
                key={t}
                type="monotone"
                dataKey={t}
                stroke={DISASTER_COLORS[t] ?? "#64748b"}
                strokeWidth={2}
                dot={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// 2. Continents tab — BarChart
//    Filters: Disaster Type (All | specific) + Metric (Events | Deaths | Damage).
//    When a specific type is selected the metric dropdown is hidden — we only have
//    per-type event counts in events_by_type, not per-type median deaths/damage.

type ContMetric = "total_events" | "median_deaths" | "median_damage_000usd"

function ContinentsTab({ data }: { data: ContinentStats }) {
  const [metric,     setMetric]     = useState<ContMetric>("total_events")
  const [filterType, setFilterType] = useState("All")

  const metricOptions = [
    { value: "total_events",         label: S("filter.metric.events") },
    { value: "median_deaths",        label: S("filter.metric.deaths") },
    { value: "median_damage_000usd", label: S("filter.metric.damage") },
  ]

  // Collect all disaster types that appear in at least one continent's events_by_type.
  const allTypes = useMemo(() => {
    const seen = new Set<string>()
    for (const v of Object.values(data)) {
      if (v.events_by_type) Object.keys(v.events_by_type).forEach((t) => seen.add(t))
    }
    return [...seen].sort()
  }, [data])

  const typeOptions = [
    { value: "All", label: S("filter.all.types") },
    ...allTypes.map((t) => ({ value: t, label: t })),
  ]

  const isTypeFiltered = filterType !== "All"

  const rows = useMemo(
    () => {
      return Object.entries(data)
        .map(([continent, v]) => {
          const value = isTypeFiltered
            ? ((v.events_by_type?.[filterType] ?? 0) as number)
            : ((v[metric] ?? 0) as number)
          return { continent, value, top_disaster: v.top_disaster }
        })
        .sort((a, b) => b.value - a.value)
    },
    [data, metric, filterType, isTypeFiltered],
  )

  const effectiveMetric = isTypeFiltered ? "total_events" : metric
  const yLabel = isTypeFiltered
    ? Sf("analytics.continents.typeEvents", { type: filterType })
    : effectiveMetric === "total_events"
    ? S("analytics.continents.yLabel")
    : effectiveMetric === "median_deaths"
    ? S("filter.metric.deaths")
    : S("filter.metric.damage")

  const fmtValue = (v: number) =>
    (!isTypeFiltered && metric === "median_damage_000usd") ? formatUSDFromThousands(v) : formatInt(v)

  return (
    <ChartCard
      title={S("analytics.continents.title")}
      help={S("analytics.continents.help")}
    >
      <div className="mt-3">
        <FilterBar
          filters={[
            {
              id: "ct-type", label: S("filter.label.disasterType"),
              options: typeOptions, value: filterType, onChange: setFilterType,
            },
            ...(isTypeFiltered ? [] : [{
              id: "ct-metric", label: S("filter.label.metric"),
              options: metricOptions, value: metric,
              onChange: (v: string) => setMetric(v as ContMetric),
            }]),
          ]}
        />
      </div>
      <div className="h-[380px] mt-4">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
            <XAxis dataKey="continent" tick={{ fontSize: 11, fill: "#475569" }} />
            <YAxis
              tick={{ fontSize: 11, fill: "#475569" }}
              tickFormatter={(!isTypeFiltered && metric === "median_damage_000usd") ? formatUSDFromThousands : formatInt}
              label={{
                value: yLabel,
                angle: -90,
                position: "insideLeft",
                style: { fontSize: 11, fill: "#64748b" },
              }}
            />
            <Tooltip
              contentStyle={{ fontSize: 12 }}
              formatter={(value: number, _name, p) => [
                fmtValue(value),
                `${p.payload.continent} — ${yLabel}`,
              ]}
              labelFormatter={(label, payload) => {
                const top = payload?.[0]?.payload?.top_disaster
                return top ? `${label}  ·  top: ${top}` : String(label)
              }}
            />
            <Bar dataKey="value" fill="#0f172a" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// 3. Insurance gap tab — BarChart, one bar per type
//    Filter: Sort direction (Low→High | High→Low)

function InsuranceTab({ data }: { data: InsuranceRatios }) {
  const [sort, setSort] = useState<"asc" | "desc">("asc")

  const sortOptions = [
    { value: "asc",  label: S("filter.sort.lowHigh") },
    { value: "desc", label: S("filter.sort.highLow") },
  ]

  const rows = useMemo(
    () => {
      const mapped = Object.entries(data).map(([t, ratio]) => ({
        disaster:  t,
        ratio_pct: +(ratio * 100).toFixed(1),
      }))
      return sort === "asc"
        ? mapped.sort((a, b) => a.ratio_pct - b.ratio_pct)
        : mapped.sort((a, b) => b.ratio_pct - a.ratio_pct)
    },
    [data, sort],
  )

  const eq = data["Earthquake"]
  const fl = data["Flood"]
  const insightBody =
    typeof eq === "number" && typeof fl === "number"
      ? Sf("analytics.insurance.insightBody", {
          eq: Math.round(eq * 100),
          fl: Math.round(fl * 100),
        })
      : ""

  return (
    <ChartCard
      title={S("analytics.insurance.title")}
      help={S("analytics.insurance.help")}
    >
      <div className="mt-3">
        <FilterBar
          filters={[
            {
              id: "ins-sort", label: S("filter.label.sort"),
              options: sortOptions, value: sort,
              onChange: (v) => setSort(v as "asc" | "desc"),
            },
          ]}
        />
      </div>
      {insightBody && (
        <Insight
          title={S("analytics.insurance.insightTitle")}
          body={insightBody}
          tone="blue"
        />
      )}
      <div className="h-[380px] mt-4">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 32, left: 0 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
            <XAxis
              dataKey="disaster"
              tick={{ fontSize: 10, fill: "#475569" }}
              interval={0}
              angle={-25}
              textAnchor="end"
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#475569" }}
              tickFormatter={(v) => `${v}%`}
              domain={[0, 100]}
            />
            <Tooltip
              contentStyle={{ fontSize: 12 }}
              formatter={(value: number) => [`${value}%`, S("analytics.insurance.yLabel")]}
            />
            <Bar dataKey="ratio_pct" radius={[6, 6, 0, 0]}>
              {rows.map((r, i) => (
                <Cell
                  key={i}
                  fill={DISASTER_COLORS[r.disaster] ?? "#475569"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-2 text-[11px] text-slate-400">
        {S("analytics.insurance.caveat")}
      </p>
    </ChartCard>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// 4. Time series tab — ComposedChart per disaster type, linear regression
//    Filters: Disaster Type (existing), Metric (Events | Deaths | Affected | Damage)

const SLOPE_NOISE_FLOOR = 0.05 // |slope| < 5% of mean ⇒ "Stable"
const GREY_THRESHOLD    = 10

interface RegResult { slope: number; intercept: number }
function linearRegression(ys: number[]): RegResult {
  const n   = ys.length
  if (n < 2) return { slope: 0, intercept: ys[0] ?? 0 }
  let sumX = 0, sumY = 0, sumXY = 0, sumXX = 0
  for (let i = 0; i < n; i++) {
    sumX  += i
    sumY  += ys[i]
    sumXY += i * ys[i]
    sumXX += i * i
  }
  const denom = n * sumXX - sumX * sumX
  const slope = denom === 0 ? 0 : (n * sumXY - sumX * sumY) / denom
  const intercept = (sumY - slope * sumX) / n
  return { slope, intercept }
}

type TSMetric = "events" | "deaths" | "affected" | "damage_000usd"

function getMetricVal(r: TimeseriesDecadeEntry, m: TSMetric): number {
  const v = r[m as keyof TimeseriesDecadeEntry]
  return typeof v === "number" ? v : 0
}

function TimeSeriesTab({ data }: { data: TimeSeriesData }) {
  const types = Object.keys(data.by_decade ?? {}).sort()
  const [pick,   setPick]   = useState<string>(types.includes("Flood") ? "Flood" : types[0])
  const [metric, setMetric] = useState<TSMetric>("events")

  const series = data.by_decade[pick] ?? []

  const metricValues = series.map((r) => getMetricVal(r, metric))
  const { slope, intercept } = useMemo(() => linearRegression(metricValues), [metricValues])
  const meanVal = metricValues.length
    ? metricValues.reduce((a, b) => a + b, 0) / metricValues.length
    : 0

  const rows = series.map((r, i) => ({
    decade: r.decade,
    value:  getMetricVal(r, metric),
    trend:  Math.max(0, intercept + slope * i),
    // grey-out only applies to the events metric (< 10 events = unreliable decade)
    isLow:  metric === "events" && (r.events ?? 0) < GREY_THRESHOLD,
  }))

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
      ? "bg-orange-100 text-orange-800 border-orange-200"
      : slopeLabel === S("analytics.timeseries.slope.decreasing")
        ? "bg-green-100 text-green-800 border-green-200"
        : "bg-slate-100 text-slate-700 border-slate-200"

  const typeOptions   = types.map((t) => ({ value: t, label: t }))
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

  const metricLabel   = metricOptions.find((o) => o.value === metric)?.label ?? S("filter.metric.events")
  const recordedLabel = Sf("analytics.timeseries.recordedLabel", { metric: metricLabel })

  return (
    <ChartCard
      title={S("analytics.timeseries.title")}
      help={S("analytics.timeseries.help")}
    >
      <div className="mt-3 space-y-2">
        <FilterBar
          filters={[
            {
              id: "ts-type", label: S("filter.label.disasterType"),
              options: typeOptions, value: pick, onChange: setPick,
            },
            {
              id: "ts-metric", label: S("filter.label.metric"),
              options: metricOptions, value: metric,
              onChange: (v) => setMetric(v as TSMetric),
            },
          ]}
        />
        <div className="flex items-center justify-end gap-2">
          <span
            className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${slopeBadgeColor}`}
          >
            {slopeLabel}
          </span>
          <span className="text-[11px] text-slate-500 tabular-nums">
            {Sf("analytics.timeseries.slope.full", { slope: slope.toFixed(1) })}
          </span>
        </div>
      </div>

      <div className="h-[380px] mt-4">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
            <XAxis dataKey="decade" tick={{ fontSize: 11, fill: "#475569" }} />
            <YAxis
              tick={{ fontSize: 11, fill: "#475569" }}
              tickFormatter={metric === "damage_000usd" ? formatUSDFromThousands : formatInt}
              label={{
                value: yAxisLabel[metric],
                angle: -90,
                position: "insideLeft",
                style: { fontSize: 11, fill: "#64748b" },
              }}
            />
            <Tooltip
              contentStyle={{ fontSize: 12 }}
              formatter={(v: number, name: string) => [fmtValue(v), name]}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
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
    </ChartCard>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// Shared atoms

function ChartCard({
  title,
  help,
  children,
}: {
  title: string
  help: string
  children: React.ReactNode
}) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <h2 className="text-lg font-semibold text-slate-800">{title}</h2>
      <p className="mt-1 text-xs text-slate-500 max-w-2xl">{help}</p>
      {children}
    </section>
  )
}

function Insight({
  title,
  body,
  tone,
}: {
  title: string
  body: string
  tone: "orange" | "blue"
}) {
  const toneClass =
    tone === "orange"
      ? "border-orange-200 bg-orange-50"
      : "border-blue-200 bg-blue-50"
  return (
    <div className={`mt-3 rounded-lg border ${toneClass} px-3 py-2`}>
      <p className="text-xs font-semibold text-slate-800">{title}</p>
      <p className="text-xs text-slate-700">{body}</p>
    </div>
  )
}
