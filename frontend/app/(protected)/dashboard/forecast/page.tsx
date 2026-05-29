// 30-Day Forecast — /dashboard/forecast (Subscriber+ only, CLAUDE.md Feature 10).
//
// Middleware redirects guests to /login; the inline guest fallback below
// only fires if someone somehow lands here unauthenticated (defence in
// depth). The real Subscriber+ gate is the backend's slowapi + require_subscriber.
//
// Backend rate limit: 5 forecasts per hour. The 24h DB cache means re-running
// the same (lat, lon, type) is free until the cache window expires.

"use client"

import { useMemo, useState, type FormEvent } from "react"
import { useSession } from "next-auth/react"
import Link from "next/link"

import { S, Sf } from "@/lib/strings"
import { endpoints } from "@/lib/endpoints"
import type { ApiError } from "@/lib/api"

import { Nav } from "@/components/Nav"
import { PredictionResultCard } from "@/components/PredictionResultCard"
import { SeverityBadge } from "@/components/SeverityBadge"
import { ForecastCalendar } from "@/components/ForecastCalendar"
import { ForecastLineChart } from "@/components/ForecastLineChart"

import type {
  DisasterType,
  ForecastDay,
  ForecastRequest,
  SeverityLevel,
} from "@/types"

const DISASTER_TYPES: DisasterType[] = [
  "Flood", "Storm", "Earthquake", "Wildfire",
  "Volcanic activity", "Landslide", "Drought", "Extreme temperature",
]

const SEVERITY_RANK: Record<SeverityLevel, number> = {
  Low: 0, Medium: 1, High: 2, Critical: 3,
}

export default function ForecastPage() {
  const { status } = useSession()

  if (status === "unauthenticated") return <GuestFallback />

  return (
    <>
      <Nav />
      <main className="max-w-6xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-slate-800">{S("forecast.title")}</h1>
        <p className="mt-1 text-sm text-slate-500 max-w-2xl">{S("forecast.subtitle")}</p>
        <ForecastShell />
      </main>
    </>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// Guest fallback (defence in depth — middleware should have redirected)

function GuestFallback() {
  return (
    <>
      <Nav />
      <main className="max-w-2xl mx-auto px-4 py-16 text-center">
        <h1 className="text-2xl font-bold text-slate-800">
          {S("forecast.guestTitle")}
        </h1>
        <p className="mt-2 text-sm text-slate-500">{S("forecast.guestBody")}</p>
        <Link
          href="/register"
          className="mt-6 inline-flex items-center rounded-md bg-slate-800 text-white text-sm font-medium px-5 py-2.5 hover:bg-slate-700"
        >
          {S("forecast.guestCta")}
        </Link>
      </main>
    </>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// Main shell — form + result panels

function ForecastShell() {
  const [days, setDays]       = useState<ForecastDay[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)
  const [selectedOffset, setSelectedOffset] = useState<number | null>(null)
  const [pickedType, setPickedType] = useState<string>("Flood")

  const summary = useMemo(() => buildSummary(days), [days])

  async function runForecast(body: ForecastRequest) {
    setError(null)
    setLoading(true)
    try {
      const out = await endpoints.predictions.forecast30d(body)
      setDays(out)
      setSelectedOffset(0)
      setPickedType(body.disaster_type)
    } catch (e: unknown) {
      const err = e as ApiError
      if (err?.status === 401)      setError(S("forecast.error.unauth"))
      else if (err?.status === 429) setError(S("forecast.error.rateLimit"))
      else                          setError(err?.detail || S("forecast.error.generic"))
    } finally {
      setLoading(false)
    }
  }

  const selectedDay =
    selectedOffset !== null
      ? days.find((d) => d.forecast_day_offset === selectedOffset) ?? null
      : null

  return (
    <div className="mt-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Form column */}
      <section className="lg:col-span-1 rounded-xl border border-slate-200 bg-white p-5">
        <h2 className="text-lg font-semibold text-slate-800">{S("forecast.form.title")}</h2>
        <p className="mt-1 text-xs text-slate-500">{S("forecast.form.help")}</p>
        <ForecastForm
          error={error}
          loading={loading}
          onSubmit={runForecast}
        />
      </section>

      {/* Results column */}
      <section className="lg:col-span-2 space-y-6">
        {/* Disclaimer always visible */}
        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          {S("forecast.disclaimer")}
        </p>

        {loading && days.length === 0 && (
          <div className="rounded-xl border border-slate-200 bg-white p-10 text-center text-sm text-slate-500">
            {S("forecast.busy")}
          </div>
        )}

        {days.length > 0 && summary && (
          <RiskSummaryBanner summary={summary} />
        )}

        {days.length > 0 && (
          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <ForecastCalendar
              days={days}
              selectedOffset={selectedOffset}
              onSelect={setSelectedOffset}
            />
          </div>
        )}

        {days.length > 0 && (
          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <ForecastLineChart days={days} disasterType={pickedType} />
          </div>
        )}

        {selectedDay && (
          <PredictionResultCard
            result={selectedDay}
            forecastDisclaimer
            headerSuffix={Sf("forecast.cardSuffix", {
              n:    selectedDay.forecast_day_offset + 1,
              date: selectedDay.date,
            })}
          />
        )}

        {days.length === 0 && !loading && !error && (
          <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-400">
            {S("forecast.empty")}
          </div>
        )}
      </section>
    </div>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// Form

function ForecastForm(props: {
  loading: boolean
  error: string | null
  onSubmit: (body: ForecastRequest) => Promise<void>
}) {
  const [lat,        setLat]        = useState("30.05")
  const [lon,        setLon]        = useState("31.24")
  const [country,    setCountry]    = useState("Egypt")
  const [continent,  setContinent]  = useState("Africa")
  const [type,       setType]       = useState<DisasterType>("Flood")
  const [localError, setLocalError] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setLocalError(null)
    const latNum = parseFloat(lat)
    const lonNum = parseFloat(lon)
    if (Number.isNaN(latNum) || latNum < -90 || latNum > 90) {
      setLocalError(S("form.lat.error")); return
    }
    if (Number.isNaN(lonNum) || lonNum < -180 || lonNum > 180) {
      setLocalError(S("form.lon.error")); return
    }
    if (!country.trim() || !continent.trim()) {
      setLocalError(S("form.required")); return
    }
    await props.onSubmit({
      latitude:      latNum,
      longitude:     lonNum,
      country:       country.trim(),
      continent:     continent.trim(),
      disaster_type: type,
    })
  }

  const message = localError ?? props.error

  return (
    <form onSubmit={onSubmit} className="mt-5 space-y-3 text-sm" noValidate>
      {message && (
        <div role="alert" className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs">
          {message}
        </div>
      )}
      <div className="grid grid-cols-2 gap-3">
        <Field id="f-lat" label={S("form.lat.label")} value={lat} onChange={setLat}
               placeholder={S("form.lat.placeholder")} type="number" step="0.0001" />
        <Field id="f-lon" label={S("form.lon.label")} value={lon} onChange={setLon}
               placeholder={S("form.lon.placeholder")} type="number" step="0.0001" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field id="f-country"   label={S("form.country.label")}   value={country}
               onChange={setCountry}   placeholder={S("form.country.placeholder")} />
        <Field id="f-continent" label={S("form.continent.label")} value={continent}
               onChange={setContinent} placeholder={S("form.continent.placeholder")} />
      </div>
      <div>
        <label htmlFor="f-type" className="block text-xs font-medium text-slate-700">
          {S("form.disasterType.label")}
        </label>
        <select
          id="f-type"
          value={type}
          onChange={(e) => setType(e.target.value as DisasterType)}
          className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-800"
        >
          {DISASTER_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
      </div>
      <button
        type="submit"
        disabled={props.loading}
        className="w-full rounded-md bg-slate-800 text-white text-sm font-medium px-4 py-2.5 hover:bg-slate-700 disabled:opacity-60"
      >
        {props.loading ? S("forecast.busy") : S("forecast.submit")}
      </button>
    </form>
  )
}

function Field(props: {
  id: string
  label: string
  value: string
  onChange: (s: string) => void
  placeholder?: string
  type?: string
  step?: string
}) {
  return (
    <div>
      <label htmlFor={props.id} className="block text-xs font-medium text-slate-700">
        {props.label}
      </label>
      <input
        id={props.id}
        type={props.type ?? "text"}
        step={props.step}
        value={props.value}
        onChange={(e) => props.onChange(e.target.value)}
        placeholder={props.placeholder}
        className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-800"
      />
    </div>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// Risk Summary Banner

interface ForecastSummary {
  highestDayOffset: number
  highestDate:      string
  highestSeverity:  SeverityLevel
  highestProb:      number
  topType:          string
  peakStart:        number | null
  peakEnd:          number | null
}

function buildSummary(days: ForecastDay[]): ForecastSummary | null {
  if (days.length === 0) return null

  // Highest-risk day = max probability_score (severity is a function of prob).
  let topIdx = 0
  for (let i = 1; i < days.length; i++) {
    if (days[i].probability_score > days[topIdx].probability_score) topIdx = i
  }
  const top = days[topIdx]

  // Most likely disaster: since the backend forecasts a single type per
  // request, this is just the type that was forecasted. In a future multi-
  // type forecast, this becomes the mode across days.
  const topType = top.disaster_type

  // Peak risk window: longest run of consecutive days with severity >= High.
  let bestStart: number | null = null
  let bestEnd:   number | null = null
  let curStart:  number | null = null
  for (let i = 0; i < days.length; i++) {
    const isHigh = SEVERITY_RANK[days[i].severity_level] >= SEVERITY_RANK.High
    if (isHigh) {
      if (curStart === null) curStart = i
      if (
        bestStart === null ||
        (i - curStart) > (bestEnd! - bestStart)
      ) {
        bestStart = curStart
        bestEnd   = i
      }
    } else {
      curStart = null
    }
  }

  return {
    highestDayOffset: top.forecast_day_offset + 1,
    highestDate:      top.date,
    highestSeverity:  top.severity_level,
    highestProb:      top.probability_score,
    topType,
    peakStart: bestStart === null ? null : days[bestStart].forecast_day_offset + 1,
    peakEnd:   bestEnd   === null ? null : days[bestEnd].forecast_day_offset + 1,
  }
}

function RiskSummaryBanner({ summary }: { summary: ForecastSummary }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">
        {S("forecast.summary.title")}
      </h2>
      <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="rounded-lg border border-slate-200 p-3">
          <div className="text-xs text-slate-500">{S("forecast.summary.highest")}</div>
          <div className="mt-1 flex items-center gap-2">
            <span className="text-lg font-semibold text-slate-900">
              {Sf("forecast.summary.dayShort", { n: summary.highestDayOffset })}
            </span>
            <SeverityBadge level={summary.highestSeverity} />
          </div>
          <div className="text-xs text-slate-500 tabular-nums">
            {summary.highestDate} - {(summary.highestProb * 100).toFixed(1)}%
          </div>
        </div>
        <div className="rounded-lg border border-slate-200 p-3">
          <div className="text-xs text-slate-500">{S("forecast.summary.likely")}</div>
          <div className="mt-1 text-lg font-semibold text-slate-900">
            {summary.topType}
          </div>
        </div>
        <div className="rounded-lg border border-slate-200 p-3">
          <div className="text-xs text-slate-500">{S("forecast.summary.peakWindow")}</div>
          <div className="mt-1 text-lg font-semibold text-slate-900">
            {summary.peakStart === null || summary.peakEnd === null
              ? <span className="text-sm font-normal text-slate-500">
                  {S("forecast.summary.peakNone")}
                </span>
              : Sf("forecast.summary.dayRange", {
                  from: summary.peakStart,
                  to:   summary.peakEnd,
                })}
          </div>
        </div>
      </div>
    </div>
  )
}
