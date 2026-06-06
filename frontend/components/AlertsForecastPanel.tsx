// Premium-only Alerts surface: a 30-day disaster ALERT forecast for one of the
// user's SUBSCRIBED regions, with probabilities. Generating it ALSO emails the
// premium user the highest-risk-day summary (req 2 — auto on generate) and offers
// a downloadable PDF report (req 3). Subscription-driven (req 1 decision).
//
// The forecast endpoint needs country + continent which a subscription doesn't
// store — we pass region_name as country and derive continent from coords
// (lib/geo). Backend EM-DAT lookup falls back region→global, so this is safe and
// mirrors HomePremiumForecast.

"use client"

import { useEffect, useState } from "react"
import { useSession } from "next-auth/react"
import Link from "next/link"

import { S, Sf } from "@/lib/strings"
import { endpoints } from "@/lib/endpoints"
import type { ApiError } from "@/lib/api"
import { continentFromLatLon } from "@/lib/geo"

import { ForecastCalendar } from "@/components/ForecastCalendar"
import { SeverityBadge } from "@/components/SeverityBadge"

import type {
  DisasterType,
  EmailForecastResponse,
  ForecastDay,
  SubscriptionListItem,
} from "@/types"

const DISASTER_TYPES: DisasterType[] = [
  "Flood", "Storm", "Earthquake", "Wildfire",
  "Volcanic activity", "Landslide", "Drought", "Extreme temperature",
]

type EmailState = "idle" | "sending" | "sent" | "failed"

export function AlertsForecastPanel() {
  const { data: session } = useSession()
  const email = session?.user?.email ?? ""

  const [subs, setSubs]            = useState<SubscriptionListItem[]>([])
  const [subsLoading, setSubsLoad] = useState(true)
  const [subsError, setSubsError]  = useState(false)

  const [regionId, setRegionId]   = useState<string>("")
  const [type, setType]           = useState<DisasterType>("Flood")

  const [days, setDays]           = useState<ForecastDay[]>([])
  const [selectedOffset, setSel]  = useState<number | null>(null)
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState<string | null>(null)

  const [emailState, setEmailState]   = useState<EmailState>("idle")
  const [emailResult, setEmailResult] = useState<EmailForecastResponse | null>(null)

  const [pdfBusy, setPdfBusy]     = useState(false)
  const [pdfError, setPdfError]   = useState<string | null>(null)

  // Load the user's subscriptions once (active only, newest first — backend filters).
  useEffect(() => {
    let alive = true
    endpoints.subscriptions.list()
      .then((s) => {
        if (!alive) return
        setSubs(s)
        if (s.length > 0) setRegionId(s[0].id)
      })
      .catch(() => { if (alive) setSubsError(true) })
      .finally(() => { if (alive) setSubsLoad(false) })
    return () => { alive = false }
  }, [])

  const region = subs.find((s) => s.id === regionId) ?? null

  async function onGenerate() {
    if (!region) return
    setError(null)
    setLoading(true)
    setDays([])
    setEmailState("idle")
    setEmailResult(null)
    setPdfError(null)

    try {
      const out = await endpoints.predictions.forecast30d({
        latitude:      region.latitude,
        longitude:     region.longitude,
        region_name:   region.region_name,
        country:       region.region_name,
        continent:     continentFromLatLon(region.latitude, region.longitude),
        disaster_type: type,
      })
      setDays(out)
      setSel(0)

      // Req 2 — auto email-on-generate. The 30 rows were just persisted, so the
      // backend reads this very batch and emails its highest-risk day.
      setEmailState("sending")
      try {
        const res = await endpoints.alerts.emailForecast()
        setEmailResult(res)
        setEmailState(res.sent ? "sent" : "failed")
      } catch {
        setEmailState("failed")
      }
    } catch (e: unknown) {
      const err = e as ApiError
      if (err?.status === 429)      setError(S("forecast.error.rateLimit"))
      else if (err?.status === 401) setError(S("forecast.error.unauth"))
      else                          setError(err?.detail || S("forecast.error.generic"))
    } finally {
      setLoading(false)
    }
  }

  async function onDownloadPdf() {
    setPdfError(null)
    setPdfBusy(true)
    try {
      const blob = await endpoints.predictions.forecastPdf()
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement("a")
      a.href     = url
      a.download = `safeearth-forecast_${region?.region_name ?? "report"}.pdf`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch {
      setPdfError(S("alerts.pdf.error"))
    } finally {
      setPdfBusy(false)
    }
  }

  const selectedDay =
    selectedOffset !== null
      ? days.find((d) => d.forecast_day_offset === selectedOffset) ?? null
      : null

  // ── States ────────────────────────────────────────────────────────────────
  if (subsLoading) {
    return <Panel><p className="text-sm text-slate-500">{S("alerts.premium.loading")}</p></Panel>
  }
  if (subsError) {
    return <Panel><p className="text-sm text-red-600">{S("forecast.error.generic")}</p></Panel>
  }
  if (subs.length === 0) {
    return (
      <Panel>
        <NoRegionPrompt />
      </Panel>
    )
  }

  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-800">{S("alerts.premium.title")}</h2>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">{S("alerts.premium.subtitle")}</p>
        </div>
      </div>

      {/* Controls */}
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div>
          <label htmlFor="af-region" className="block text-xs font-medium text-slate-700">
            {S("alerts.premium.region")}
          </label>
          <select
            id="af-region"
            value={regionId}
            onChange={(e) => setRegionId(e.target.value)}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-800"
          >
            {subs.map((s) => (
              <option key={s.id} value={s.id}>{s.region_name}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="af-type" className="block text-xs font-medium text-slate-700">
            {S("alerts.premium.type")}
          </label>
          <select
            id="af-type"
            value={type}
            onChange={(e) => setType(e.target.value as DisasterType)}
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-800"
          >
            {DISASTER_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div className="flex items-end">
          <button
            type="button"
            onClick={onGenerate}
            disabled={loading || !region}
            className="w-full rounded-md bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-60"
          >
            {loading ? S("alerts.premium.busy") : S("alerts.premium.generate")}
          </button>
        </div>
      </div>

      <p className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
        {S("alerts.premium.disclaimer")}
      </p>

      {error && (
        <div role="alert" className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
          {error}
        </div>
      )}

      {/* Results */}
      {days.length > 0 && (
        <div className="mt-5 space-y-4">
          <EmailStatusLine state={emailState} result={emailResult} email={email} />

          <div className="rounded-xl border border-slate-200 bg-white p-5">
            <ForecastCalendar days={days} selectedOffset={selectedOffset} onSelect={setSel} />
          </div>

          {selectedDay && (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
              <span className="font-medium text-slate-700">
                {Sf("alerts.premium.day", {
                  n: selectedDay.forecast_day_offset + 1, date: selectedDay.date,
                })}
              </span>
              <SeverityBadge level={selectedDay.severity_level} />
              <span className="tabular-nums text-slate-500">
                {(selectedDay.probability_score * 100).toFixed(1)}%
              </span>
            </div>
          )}

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={onDownloadPdf}
              disabled={pdfBusy}
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" fill="currentColor" aria-hidden="true">
                <path d="M10 3a1 1 0 0 1 1 1v6.586l1.293-1.293a1 1 0 1 1 1.414 1.414l-3 3a1 1 0 0 1-1.414 0l-3-3a1 1 0 1 1 1.414-1.414L9 10.586V4a1 1 0 0 1 1-1Z" />
                <path d="M4 14a1 1 0 0 1 1 1v1h10v-1a1 1 0 1 1 2 0v2a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-2a1 1 0 0 1 1-1Z" />
              </svg>
              {pdfBusy ? S("alerts.pdf.preparing") : S("alerts.pdf.download")}
            </button>
            {pdfError && <span className="text-xs text-red-600">{pdfError}</span>}
          </div>
        </div>
      )}

      {days.length === 0 && !loading && !error && (
        <div className="mt-5 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-400">
          {S("alerts.premium.empty")}
        </div>
      )}
    </Panel>
  )
}

function EmailStatusLine({
  state, result, email,
}: {
  state: EmailState
  result: EmailForecastResponse | null
  email: string
}) {
  if (state === "idle") return null

  if (state === "sending") {
    return <StatusBox tone="info">{S("alerts.email.sending")}</StatusBox>
  }
  if (state === "failed") {
    return <StatusBox tone="error">{S("alerts.email.failed")}</StatusBox>
  }
  // sent — but dev-fallback message ids mean it was logged, not actually delivered.
  if (result && typeof result.message_id === "string" && result.message_id.startsWith("dev-fallback")) {
    return <StatusBox tone="info">{S("alerts.email.dev")}</StatusBox>
  }
  return (
    <StatusBox tone="ok">
      {Sf("alerts.email.sent", {
        email,
        day:      result?.peak_day ?? "",
        severity: result?.severity_level ?? "",
      })}
    </StatusBox>
  )
}

function StatusBox({ tone, children }: { tone: "ok" | "info" | "error"; children: React.ReactNode }) {
  const cls =
    tone === "ok"    ? "border-emerald-200 bg-emerald-50 text-emerald-800" :
    tone === "error" ? "border-red-200 bg-red-50 text-red-700" :
                       "border-slate-200 bg-slate-50 text-slate-600"
  return (
    <div className={`rounded-lg border px-3 py-2 text-xs ${cls}`}>{children}</div>
  )
}

function NoRegionPrompt() {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-6 py-8 text-center">
      <p className="text-sm font-medium text-slate-700">{S("alerts.premium.noRegion.title")}</p>
      <p className="mt-1 text-sm text-slate-500">{S("alerts.premium.noRegion.body")}</p>
      <Link
        href="/dashboard"
        className="mt-4 inline-flex items-center justify-center rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
      >
        {S("alerts.premium.noRegion.cta")}
      </Link>
    </div>
  )
}

function Panel({ children }: { children: React.ReactNode }) {
  return <section className="rounded-xl border border-slate-200 bg-white p-5">{children}</section>
}
