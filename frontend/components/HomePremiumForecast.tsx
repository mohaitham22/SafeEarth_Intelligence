// Premium-only home widget: the REAL 30-day forecast for the user's chosen
// region (their newest active subscription). Premium with no subscriptions yet
// sees a prompt to subscribe. Rendered only after HomeForecastSection confirms
// the user is premium/admin.
//
// The forecast endpoint needs country + continent, which a subscription doesn't
// store — we pass region_name as country and derive continent from coords
// (see lib/geo). Backend EM-DAT lookup falls back region→global, so this is safe.

"use client"

import { useEffect, useState } from "react"
import Link from "next/link"

import { S, Sf } from "@/lib/strings"
import { endpoints } from "@/lib/endpoints"
import type { ApiError } from "@/lib/api"
import { continentFromLatLon } from "@/lib/geo"
import { ForecastCalendar } from "@/components/ForecastCalendar"
import { SeverityBadge } from "@/components/SeverityBadge"
import type { DisasterType, ForecastDay, SubscriptionListItem } from "@/types"

const DISASTER_TYPES: DisasterType[] = [
  "Flood", "Storm", "Earthquake", "Wildfire",
  "Volcanic activity", "Landslide", "Drought", "Extreme temperature",
]

export function HomePremiumForecast() {
  const [subs, setSubs]             = useState<SubscriptionListItem[]>([])
  const [subsLoading, setSubsLoad]  = useState(true)
  const [subsError, setSubsError]   = useState(false)

  const [type, setType]             = useState<DisasterType>("Flood")
  const [days, setDays]             = useState<ForecastDay[]>([])
  const [fLoading, setFLoading]     = useState(false)
  const [fError, setFError]         = useState<string | null>(null)
  const [selectedOffset, setSelectedOffset] = useState<number | null>(null)

  // Load the user's subscriptions once (newest first, active only — backend filters).
  useEffect(() => {
    let alive = true
    endpoints.subscriptions.list()
      .then((s) => { if (alive) setSubs(s) })
      .catch(() => { if (alive) setSubsError(true) })
      .finally(() => { if (alive) setSubsLoad(false) })
    return () => { alive = false }
  }, [])

  const region = subs.length > 0 ? subs[0] : null

  // Fetch the real 30-day forecast whenever the region or disaster type changes.
  useEffect(() => {
    if (!region) return
    let alive = true
    setFLoading(true)
    setFError(null)
    endpoints.predictions
      .forecast30d({
        latitude:      region.latitude,
        longitude:     region.longitude,
        region_name:   region.region_name,
        country:       region.region_name,
        continent:     continentFromLatLon(region.latitude, region.longitude),
        disaster_type: type,
      })
      .then((d) => {
        if (!alive) return
        setDays(d)
        setSelectedOffset(0)
      })
      .catch((e: unknown) => {
        if (!alive) return
        const err = e as ApiError
        if (err?.status === 429)      setFError(S("forecast.error.rateLimit"))
        else if (err?.status === 401) setFError(S("forecast.error.unauth"))
        else                          setFError(err?.detail || S("forecast.error.generic"))
        setDays([])
      })
      .finally(() => { if (alive) setFLoading(false) })
    return () => { alive = false }
  }, [region?.id, type])

  // Shell -----------------------------------------------------------------
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-800">
            {S("home.forecast.premium.title")}
          </h2>
          {region && (
            <p className="mt-1 text-sm text-slate-600">
              {Sf("home.forecast.premium.region", { region: region.region_name })}
            </p>
          )}
        </div>
        {region && (
          <div>
            <label htmlFor="home-fc-type" className="sr-only">
              {S("form.disasterType.label")}
            </label>
            <select
              id="home-fc-type"
              value={type}
              onChange={(e) => setType(e.target.value as DisasterType)}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-slate-800"
            >
              {DISASTER_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
        )}
      </div>

      <div className="mt-5">
        {subsLoading ? (
          <Placeholder text={S("home.forecast.premium.loading")} />
        ) : subsError ? (
          <Placeholder text={S("forecast.error.generic")} tone="error" />
        ) : !region ? (
          <NoRegionPrompt />
        ) : (
          <ForecastBody
            days={days}
            loading={fLoading}
            error={fError}
            selectedOffset={selectedOffset}
            onSelect={setSelectedOffset}
          />
        )}
      </div>

      <p className="mt-6 text-xs text-slate-400">{S("home.forecast.disclaimer")}</p>
    </section>
  )
}

function ForecastBody({
  days, loading, error, selectedOffset, onSelect,
}: {
  days: ForecastDay[]
  loading: boolean
  error: string | null
  selectedOffset: number | null
  onSelect: (offset: number) => void
}) {
  if (error) return <Placeholder text={error} tone="error" />
  if (loading && days.length === 0) return <Placeholder text={S("forecast.busy")} />
  if (days.length === 0) return <Placeholder text={S("forecast.empty")} />

  const selected =
    selectedOffset !== null
      ? days.find((d) => d.forecast_day_offset === selectedOffset) ?? null
      : null

  return (
    <div className="space-y-4">
      <ForecastCalendar days={days} selectedOffset={selectedOffset} onSelect={onSelect} />

      {selected && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
          <span className="font-medium text-slate-700">
            {Sf("forecast.cardSuffix", {
              n: selected.forecast_day_offset + 1, date: selected.date,
            })}
          </span>
          <SeverityBadge level={selected.severity_level} />
          <span className="tabular-nums text-slate-500">
            {(selected.probability_score * 100).toFixed(1)}%
          </span>
        </div>
      )}

      <Link
        href="/dashboard/forecast"
        className="inline-flex items-center text-sm font-medium text-emerald-700 hover:underline"
      >
        {S("home.forecast.premium.full")} →
      </Link>
    </div>
  )
}

function NoRegionPrompt() {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-6 py-8 text-center">
      <p className="text-sm font-medium text-slate-700">
        {S("home.forecast.premium.noRegion.title")}
      </p>
      <p className="mt-1 text-sm text-slate-500">
        {S("home.forecast.premium.noRegion.body")}
      </p>
      <Link
        href="/dashboard"
        className="mt-4 inline-flex items-center justify-center rounded-md bg-emerald-600 text-white text-sm font-medium px-4 py-2 hover:bg-emerald-700"
      >
        {S("home.forecast.premium.noRegion.cta")}
      </Link>
    </div>
  )
}

function Placeholder({ text, tone }: { text: string; tone?: "error" }) {
  const cls = tone === "error"
    ? "border-red-200 bg-red-50 text-red-700"
    : "border-slate-200 bg-white text-slate-500"
  return (
    <div className={`rounded-xl border ${cls} p-8 text-center text-sm`}>
      {text}
    </div>
  )
}
