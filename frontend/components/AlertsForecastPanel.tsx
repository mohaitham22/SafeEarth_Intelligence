// Premium-only Alerts surface: a 30-day disaster ALERT forecast for ANY country
// the project supports, with probabilities. Generating it ALSO emails the premium
// user the highest-risk-day summary (req 2 — auto on generate) and offers a
// downloadable PDF report (req 3).
//
// Location is driven by the shared CountrySelect (continent -> country -> fixed
// centroid, backed by GET /regions/countries — the same 211-country source every
// other prediction form uses). `country` carries the exact EM-DAT name so the
// country-tier impact lookup hits; lat/lon come from the selected country.

"use client"

import { useState } from "react"
import { useSession } from "next-auth/react"

import { S, Sf } from "@/lib/strings"
import { endpoints } from "@/lib/endpoints"
import type { ApiError } from "@/lib/api"

import { CountrySelect, type LocationValue } from "@/components/CountrySelect"
import { ForecastCalendar } from "@/components/ForecastCalendar"
import { SeverityBadge } from "@/components/SeverityBadge"

import type {
  DisasterType,
  EmailForecastResponse,
  ForecastDay,
} from "@/types"

const DISASTER_TYPES: DisasterType[] = [
  "Flood", "Storm", "Earthquake", "Wildfire",
  "Volcanic activity", "Landslide", "Drought", "Extreme temperature",
]

type EmailState = "idle" | "sending" | "sent" | "failed"

export function AlertsForecastPanel() {
  const { data: session } = useSession()
  const email = session?.user?.email ?? ""

  // CountrySelect seeds `loc` with the default country once /regions/countries
  // loads, so this starts null for one render then becomes the default (USA).
  const [loc, setLoc]   = useState<LocationValue | null>(null)
  const [type, setType] = useState<DisasterType>("Flood")

  const [days, setDays]           = useState<ForecastDay[]>([])
  const [selectedOffset, setSel]  = useState<number | null>(null)
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState<string | null>(null)

  const [emailState, setEmailState]   = useState<EmailState>("idle")
  const [emailResult, setEmailResult] = useState<EmailForecastResponse | null>(null)

  const [pdfBusy, setPdfBusy]     = useState(false)
  const [pdfError, setPdfError]   = useState<string | null>(null)

  async function onGenerate() {
    if (!loc) return
    setError(null)
    setLoading(true)
    setDays([])
    setEmailState("idle")
    setEmailResult(null)
    setPdfError(null)

    try {
      const out = await endpoints.predictions.forecast30d({
        latitude:      loc.lat,
        longitude:     loc.lon,
        region_name:   loc.label,    // country display name — used by the email/PDF
        country:       loc.country,  // exact EM-DAT name — drives the impact lookup
        continent:     loc.continent,
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
      a.download = `safeearth-forecast_${loc?.label ?? "report"}.pdf`
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

  return (
    <Panel>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-800">{S("alerts.premium.title")}</h2>
          <p className="mt-1 max-w-2xl text-sm text-slate-500">{S("alerts.premium.subtitle")}</p>
        </div>
      </div>

      {/* Controls: location picker (continent -> country) + disaster type + generate */}
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <span className="block text-xs font-medium text-slate-700">
            {S("alerts.premium.region")}
          </span>
          <div className="mt-1">
            <CountrySelect value={loc} onChange={setLoc} idPrefix="af" />
          </div>
        </div>

        <div className="flex flex-col gap-3">
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
          <button
            type="button"
            onClick={onGenerate}
            disabled={loading || !loc}
            className="mt-auto w-full rounded-md bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-60"
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

function Panel({ children }: { children: React.ReactNode }) {
  return <section className="rounded-xl border border-slate-200 bg-white p-5">{children}</section>
}
