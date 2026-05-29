// Dashboard — /dashboard (Subscriber+ only).
// Tabs: Overview (prediction form + last result), Predictions (history — Phase 6),
//       Alerts / Subscriptions / Admin (placeholders).
// Protected by NextAuth middleware (matcher includes /dashboard/:path*).
// Calls POST /predictions/predict via apiClient — Bearer token auto-injected
// by the AuthBoot bridge wired in Prompt 4.

"use client"

import { Suspense, useState, useEffect, type FormEvent } from "react"
import { useSession } from "next-auth/react"
import { useSearchParams } from "next/navigation"
import { logoutAndRedirect } from "@/lib/logout"

import { S, Sf } from "@/lib/strings"
import { endpoints } from "@/lib/endpoints"
import { apiClient } from "@/lib/api"
import type { ApiError } from "@/lib/api"
import { formatInt, formatUSDFromThousands, formatCompactInt } from "@/lib/format"

import { Nav } from "@/components/Nav"
import { PredictionResultCard } from "@/components/PredictionResultCard"
import { SeverityBadge } from "@/components/SeverityBadge"

import type {
  AlertHistoryResponse,
  AlertResponse,
  ClassifyResult,
  DisasterType,
  ImpactResult,
  PredictionHistoryItem,
  PredictionHistoryResponse,
  PredictionResult,
  PredictRequest,
  SubscriptionCreate,
  SubscriptionListItem,
  TimeSeriesData,
} from "@/types"

const DISASTER_TYPES: DisasterType[] = [
  "Flood",
  "Storm",
  "Earthquake",
  "Wildfire",
  "Volcanic activity",
  "Landslide",
  "Drought",
  "Extreme temperature",
]

type Tab = "overview" | "predictions" | "alerts" | "subscriptions" | "admin"

export default function DashboardPage() {
  const { data: session } = useSession()
  const role = session?.user?.role
  const [tab, setTab] = useState<Tab>("overview")

  return (
    <>
      <Nav />
      <main className="max-w-6xl mx-auto px-4 py-8">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-slate-800">
              {S("dashboard.title")}
            </h1>
            {session?.user?.email && (
              <p className="mt-1 text-sm text-slate-500">
                {Sf("dashboard.greeting", { email: session.user.email })}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={() => logoutAndRedirect("/")}
            className="text-xs text-slate-500 hover:text-slate-800 underline"
          >
            {S("dashboard.overview.signOut")}
          </button>
        </div>

        <Tabs value={tab} onChange={setTab} showAdmin={role === "admin"} />

        <div className="mt-6">
          {/* useSearchParams() inside PredictionForm needs a Suspense parent
              for Next.js 14 static prerender to succeed. */}
          {tab === "overview"      && (
            <Suspense fallback={null}><OverviewTab /></Suspense>
          )}
          {tab === "predictions"   && <PredictionsHistoryTab />}
          {tab === "alerts"        && <AlertsTab />}
          {tab === "subscriptions" && <SubscriptionsTab />}
          {tab === "admin"         && <AdminRedirectTab />}
        </div>
      </main>
    </>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// Tabs

function Tabs({ value, onChange, showAdmin }: { value: Tab; onChange: (t: Tab) => void; showAdmin: boolean }) {
  const items: { id: Tab; label: string }[] = [
    { id: "overview",      label: S("dashboard.tab.overview") },
    { id: "predictions",   label: S("dashboard.tab.predictions") },
    { id: "alerts",        label: S("dashboard.tab.alerts") },
    { id: "subscriptions", label: S("dashboard.tab.subscriptions") },
    ...(showAdmin ? [{ id: "admin" as Tab, label: S("dashboard.tab.admin") }] : []),
  ]
  return (
    <nav className="mt-6 border-b border-slate-200" role="tablist">
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

function ComingSoon({ body }: { body: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-500">
      {body}
    </div>
  )
}

function AdminRedirectTab() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-8 text-center">
      <p className="text-slate-600 mb-4">Open the full admin panel to manage users, view model stats, and dispatch alerts.</p>
      <a
        href="/admin"
        className="inline-block px-5 py-2.5 rounded-lg bg-slate-800 text-white text-sm font-medium hover:bg-slate-700"
      >
        Go to Admin Panel →
      </a>
    </div>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// Overview tab — three ML task cards stacked vertically

function OverviewTab() {
  return (
    <div className="space-y-6">
      <ClassifyCard />
      <ImpactCard />
      <RiskCard />
    </div>
  )
}

// ── Shared sub-components ─────────────────────────────────────────────────

function ModelBadge({ label }: { label: string }) {
  return (
    <span className="shrink-0 text-xs font-mono text-slate-400 bg-slate-100 rounded px-2 py-0.5">
      {label}
    </span>
  )
}

function CardHead({ title, subtitle, badge }: { title: string; subtitle: string; badge: string }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <h2 className="text-lg font-semibold text-slate-800">{title}</h2>
        <p className="mt-1 text-sm text-slate-500">{subtitle}</p>
      </div>
      <ModelBadge label={badge} />
    </div>
  )
}

function MetricBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-slate-50 p-3">
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="mt-1 text-base font-bold text-slate-900 tabular-nums">{value}</dd>
    </div>
  )
}

// ── Card 1 — Disaster Type Predictor ─────────────────────────────────────

function ClassifyCard() {
  const [lat,       setLat]       = useState("30.05")
  const [lon,       setLon]       = useState("31.24")
  const [continent, setContinent] = useState("Africa")
  const [year,      setYear]      = useState(String(new Date().getFullYear()))
  const [season,    setSeason]    = useState("")
  const [result,    setResult]    = useState<ClassifyResult | null>(null)
  const [loading,   setLoading]   = useState(false)
  const [error,     setError]     = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const s = season.trim()
      const r = await endpoints.predictions.classify({
        latitude:  parseFloat(lat),
        longitude: parseFloat(lon),
        continent: continent.trim(),
        year:      parseInt(year, 10),
        season:    s ? (isNaN(Number(s)) ? s : parseInt(s, 10)) : 0,
      })
      setResult(r)
    } catch (e: unknown) {
      const err = e as ApiError
      setError(err?.detail || S("card1.error.generic"))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <CardHead
        title={S("card1.title")}
        subtitle={S("card1.subtitle")}
        badge={S("card1.badge")}
      />
      <div className="mt-4 grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-2">
          <form onSubmit={onSubmit} className="space-y-3 text-sm" noValidate>
            {error && (
              <div role="alert" className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs">
                {error}
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <Field id="c1-lat" label={S("form.lat.label")} value={lat} onChange={setLat} placeholder={S("form.lat.placeholder")} type="number" step="0.0001" />
              <Field id="c1-lon" label={S("form.lon.label")} value={lon} onChange={setLon} placeholder={S("form.lon.placeholder")} type="number" step="0.0001" />
            </div>
            <Field id="c1-continent" label={S("card1.continent.label")} value={continent} onChange={setContinent} placeholder={S("card1.continent.placeholder")} />
            <Field id="c1-year" label={S("card1.year.label")} value={year} onChange={setYear} placeholder={S("card1.year.placeholder")} type="number" />
            <Field id="c1-season" label={S("card1.season.label")} value={season} onChange={setSeason} placeholder={S("card1.season.placeholder")} />
            <button type="submit" disabled={loading} className="w-full rounded-md bg-slate-800 text-white text-sm font-medium px-4 py-2.5 hover:bg-slate-700 disabled:opacity-60">
              {loading ? S("card1.busy") : S("card1.submit")}
            </button>
          </form>
        </div>
        <div className="lg:col-span-3">
          {result ? (
            <div className="rounded-xl border border-slate-200 bg-white p-5 h-full">
              <p className="text-sm font-medium text-slate-700">
                {S("card1.result.top")}:{" "}
                <span className="font-bold text-slate-900">{result.top_type}</span>{" "}
                <span className="text-slate-500">({(result.top_probability * 100).toFixed(1)}%)</span>
              </p>
              <p className="mt-4 text-xs font-medium uppercase tracking-wide text-slate-400">
                {S("card1.result.ranked")}
              </p>
              <ul className="mt-2 space-y-1.5">
                {result.ranked.map((item) => (
                  <li key={item.disaster_type} className="flex items-center gap-2 text-xs">
                    <span className="w-36 text-slate-600 shrink-0 truncate">{item.disaster_type}</span>
                    <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-slate-700 rounded-full"
                        style={{ width: `${(item.probability * 100).toFixed(1)}%` }}
                      />
                    </div>
                    <span className="text-slate-500 w-12 text-right tabular-nums">
                      {(item.probability * 100).toFixed(1)}%
                    </span>
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-slate-300">{result.model_version}</p>
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-400">
              {S("card1.result.ranked")}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

// ── Card 2 — Disaster Impact Prediction ──────────────────────────────────

function ImpactCard() {
  const [lat,       setLat]       = useState("30.05")
  const [lon,       setLon]       = useState("31.24")
  const [continent, setContinent] = useState("Africa")
  const [year,      setYear]      = useState(String(new Date().getFullYear()))
  const [season,    setSeason]    = useState("")
  const [country,   setCountry]   = useState("")
  const [result,    setResult]    = useState<ImpactResult | null>(null)
  const [loading,   setLoading]   = useState(false)
  const [error,     setError]     = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const s = season.trim()
      const r = await endpoints.predictions.impact({
        latitude:  parseFloat(lat),
        longitude: parseFloat(lon),
        continent: continent.trim(),
        year:      parseInt(year, 10),
        season:    s ? (isNaN(Number(s)) ? s : parseInt(s, 10)) : 0,
        country:   country.trim() || undefined,
      })
      setResult(r)
    } catch (e: unknown) {
      const err = e as ApiError
      setError(err?.detail || S("card2.error.generic"))
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <CardHead
        title={S("card2.title")}
        subtitle={S("card2.subtitle")}
        badge={S("card2.badge")}
      />
      <div className="mt-4 grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-2">
          <form onSubmit={onSubmit} className="space-y-3 text-sm" noValidate>
            {error && (
              <div role="alert" className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs">
                {error}
              </div>
            )}
            <div className="grid grid-cols-2 gap-3">
              <Field id="c2-lat" label={S("form.lat.label")} value={lat} onChange={setLat} placeholder={S("form.lat.placeholder")} type="number" step="0.0001" />
              <Field id="c2-lon" label={S("form.lon.label")} value={lon} onChange={setLon} placeholder={S("form.lon.placeholder")} type="number" step="0.0001" />
            </div>
            <Field id="c2-continent" label={S("card2.continent.label")} value={continent} onChange={setContinent} placeholder={S("card2.continent.placeholder")} />
            <div className="grid grid-cols-2 gap-3">
              <Field id="c2-year"    label={S("card2.year.label")}    value={year}    onChange={setYear}    placeholder={S("card2.year.placeholder")} type="number" />
              <Field id="c2-country" label={S("card2.country.label")} value={country} onChange={setCountry} placeholder={S("card2.country.placeholder")} />
            </div>
            <Field id="c2-season" label={S("card2.season.label")} value={season} onChange={setSeason} placeholder={S("card2.season.placeholder")} />
            <button type="submit" disabled={loading} className="w-full rounded-md bg-slate-800 text-white text-sm font-medium px-4 py-2.5 hover:bg-slate-700 disabled:opacity-60">
              {loading ? S("card2.busy") : S("card2.submit")}
            </button>
          </form>
        </div>
        <div className="lg:col-span-3">
          {result ? (
            <div className="rounded-xl border border-slate-200 bg-white p-5 h-full">
              <p className="text-sm font-medium text-slate-700">
                {S("card2.result.type")}:{" "}
                <span className="font-bold text-slate-900">{result.predicted_disaster_type}</span>{" "}
                <span className="text-slate-500">({(result.probability * 100).toFixed(1)}%)</span>
              </p>
              <dl className="mt-4 grid grid-cols-2 sm:grid-cols-3 gap-3">
                <MetricBox label={S("card2.result.events")}   value={formatInt(result.expected_events)} />
                <MetricBox label={S("card2.result.deaths")}   value={formatInt(result.estimated_deaths)} />
                <MetricBox label={S("card2.result.injuries")} value={formatInt(result.estimated_injuries)} />
                <MetricBox label={S("card2.result.affected")} value={formatCompactInt(result.estimated_affected)} />
                <MetricBox label={S("card2.result.damage")}   value={formatUSDFromThousands(result.estimated_damage_usd)} />
                <MetricBox label={S("card2.result.uninsured")} value={formatUSDFromThousands(result.uninsured_loss_usd)} />
              </dl>
              <p className="mt-3 text-xs text-slate-300">{result.data_source} · {result.model_version}</p>
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-400">
              {S("card2.result.type")}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

// ── Card 3 — Risk Level Classifier (full prediction + SHAP + recommendations)

function RiskCard() {
  const [result, setResult]         = useState<PredictionResult | null>(null)
  const [loading, setLoading]       = useState(false)
  const [error, setError]           = useState<string | null>(null)
  const [tsData, setTsData]         = useState<TimeSeriesData | null>(null)

  useEffect(() => {
    endpoints.regions.timeseries(apiClient)
      .then(setTsData)
      .catch(() => { /* non-critical — mini chart simply won't show */ })
  }, [])

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5">
      <CardHead
        title={S("card3.title")}
        subtitle={S("card3.subtitle")}
        badge={S("card3.badge")}
      />
      <div className="mt-4 grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-2">
          <PredictionForm
            loading={loading}
            onSubmit={async (body) => {
              setError(null)
              setLoading(true)
              try {
                const r = await endpoints.predictions.predict(body)
                setResult(r)
              } catch (e: unknown) {
                const err = e as ApiError
                if (err?.status === 401) setError(S("predict.error.unauth"))
                else if (err?.status === 403) setError(S("predict.error.forbidden"))
                else setError(err?.detail || S("predict.error.generic"))
              } finally {
                setLoading(false)
              }
            }}
            error={error}
          />
        </div>
        <div className="lg:col-span-3">
          {loading && !result && (
            <div className="rounded-xl border border-slate-200 bg-white p-10 text-center text-sm text-slate-500">
              {S("form.busy")}
            </div>
          )}
          {result && (
            <PredictionResultCard
              result={result}
              timeseriesData={tsData ?? undefined}
            />
          )}
          {!result && !loading && (
            <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-400">
              {S("result.title")}
            </div>
          )}
        </div>
      </div>
    </section>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// Prediction form

function PredictionForm(props: {
  loading: boolean
  error: string | null
  onSubmit: (body: PredictRequest) => Promise<void>
}) {
  // Pre-fill from /map?lat=...&lon=... when the user clicked a heatmap point.
  // Falls back to the Cairo defaults if no params are present.
  const sp = useSearchParams()
  const latParam = sp.get("lat")
  const lonParam = sp.get("lon")
  const [lat,        setLat]        = useState(latParam ?? "30.05")
  const [lon,        setLon]        = useState(lonParam ?? "31.24")
  const [country,    setCountry]    = useState("Egypt")
  const [continent,  setContinent]  = useState("Africa")
  const [disasterType, setDisasterType] = useState<DisasterType>("Flood")
  const [season,    setSeason]    = useState("")
  const [magnitude, setMagnitude] = useState("")
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

    // season: empty → 0 (current month), digits → int, else string (name)
    let seasonField: PredictRequest["season"] = 0
    const s = season.trim()
    if (s) {
      if (/^\d+$/.test(s)) seasonField = parseInt(s, 10)
      else                 seasonField = s.toLowerCase()
    }

    const body: PredictRequest = {
      latitude:      latNum,
      longitude:     lonNum,
      country:       country.trim(),
      continent:     continent.trim(),
      disaster_type: disasterType,
      season:        seasonField,
      magnitude:     magnitude.trim() ? parseFloat(magnitude) : null,
    }
    await props.onSubmit(body)
  }

  const message = localError ?? props.error

  return (
    <form onSubmit={onSubmit} className="mt-5 space-y-3 text-sm" noValidate>
      {message && (
        <div
          role="alert"
          className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs"
        >
          {message}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <Field
          id="lat"
          label={S("form.lat.label")}
          value={lat}
          onChange={setLat}
          placeholder={S("form.lat.placeholder")}
          type="number"
          step="0.0001"
        />
        <Field
          id="lon"
          label={S("form.lon.label")}
          value={lon}
          onChange={setLon}
          placeholder={S("form.lon.placeholder")}
          type="number"
          step="0.0001"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field
          id="country"
          label={S("form.country.label")}
          value={country}
          onChange={setCountry}
          placeholder={S("form.country.placeholder")}
        />
        <Field
          id="continent"
          label={S("form.continent.label")}
          value={continent}
          onChange={setContinent}
          placeholder={S("form.continent.placeholder")}
        />
      </div>

      <div>
        <label htmlFor="disasterType" className="block text-xs font-medium text-slate-700">
          {S("form.disasterType.label")}
        </label>
        <select
          id="disasterType"
          value={disasterType}
          onChange={(e) => setDisasterType(e.target.value as DisasterType)}
          className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-800"
        >
          {DISASTER_TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>

      <Field
        id="season"
        label={S("form.season.label")}
        value={season}
        onChange={setSeason}
        placeholder={S("form.season.placeholder")}
        help={S("form.season.help")}
      />
      <Field
        id="magnitude"
        label={S("form.magnitude.label")}
        value={magnitude}
        onChange={setMagnitude}
        placeholder={S("form.magnitude.placeholder")}
        type="number"
        step="any"
      />

      <button
        type="submit"
        disabled={props.loading}
        className="w-full rounded-md bg-slate-800 text-white text-sm font-medium px-4 py-2.5 hover:bg-slate-700 disabled:opacity-60"
      >
        {props.loading ? S("form.busy") : S("form.submit")}
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
  help?: string
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
      {props.help && (
        <p className="mt-1 text-[11px] text-slate-400">{props.help}</p>
      )}
    </div>
  )
}

// PredictionResultCard moved to components/PredictionResultCard.tsx.

// ──────────────────────────────────────────────────────────────────────────
// Predictions History Tab

function PredictionsHistoryTab() {
  const [data, setData]     = useState<PredictionHistoryResponse | null>(null)
  const [page, setPage]     = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    endpoints.predictions.history({ page, page_size: 10 })
      .then(setData)
      .catch(() => setError(S("history.error")))
      .finally(() => setLoading(false))
  }, [page])

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 1

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-slate-800">{S("history.title")}</h2>

      {loading && (
        <p className="text-sm text-slate-500">{S("history.loading")}</p>
      )}
      {error && (
        <p className="text-sm text-red-600">{error}</p>
      )}
      {!loading && !error && data && data.items.length === 0 && (
        <p className="text-sm text-slate-500">{S("history.empty")}</p>
      )}
      {!loading && data && data.items.length > 0 && (
        <>
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="min-w-full text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-xs font-medium text-slate-500 uppercase tracking-wide">
                <tr>
                  <th className="px-4 py-3 text-left">{S("history.col.type")}</th>
                  <th className="px-4 py-3 text-left">{S("history.col.severity")}</th>
                  <th className="px-4 py-3 text-right">{S("history.col.prob")}</th>
                  <th className="px-4 py-3 text-right">{S("history.col.risk")}</th>
                  <th className="px-4 py-3 text-left">{S("history.col.location")}</th>
                  <th className="px-4 py-3 text-left">{S("history.col.date")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((item: PredictionHistoryItem) => (
                  <tr key={item.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-medium text-slate-800">{item.disaster_type ?? "—"}</td>
                    <td className="px-4 py-3">
                      {item.severity_level
                        ? <SeverityBadge level={item.severity_level} />
                        : <span className="text-slate-400">—</span>}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                      {item.probability_score != null
                        ? `${(item.probability_score * 100).toFixed(1)}%`
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-slate-700">
                      {item.risk_score != null ? item.risk_score.toFixed(1) : "—"}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {item.latitude != null && item.longitude != null
                        ? `${item.latitude.toFixed(2)}, ${item.longitude.toFixed(2)}`
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-slate-500 whitespace-nowrap">
                      {new Date(item.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between text-sm">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1.5 rounded-md border border-slate-200 text-slate-700 disabled:opacity-40"
              >
                {S("history.prev")}
              </button>
              <span className="text-slate-500">
                {Sf("history.page", { page: String(page), total: String(totalPages) })}
              </span>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-3 py-1.5 rounded-md border border-slate-200 text-slate-700 disabled:opacity-40"
              >
                {S("history.next")}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// Subscriptions Tab

function SubscriptionsTab() {
  const { data: session } = useSession()
  const [subs, setSubs]       = useState<SubscriptionListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)
  const [removing, setRemoving] = useState<string | null>(null)

  // Add form state
  const [region, setRegion]   = useState("")
  const [lat, setLat]         = useState("")
  const [lon, setLon]         = useState("")
  const [freq, setFreq]       = useState<"weekly" | "immediate">("weekly")
  const [addLoading, setAddLoading] = useState(false)
  const [addError, setAddError]     = useState<string | null>(null)

  const isPremium = session?.user?.role === "premium" || session?.user?.role === "admin"
  const limit = isPremium ? 10 : 3

  function loadSubs() {
    setLoading(true)
    endpoints.subscriptions.list()
      .then(setSubs)
      .catch(() => setError("Failed to load subscriptions."))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadSubs() }, [])

  async function onAdd(e: FormEvent) {
    e.preventDefault()
    setAddError(null)
    const latNum = parseFloat(lat)
    const lonNum = parseFloat(lon)
    if (!region.trim()) { setAddError("Region name is required."); return }
    if (isNaN(latNum) || latNum < -90 || latNum > 90) { setAddError(S("form.lat.error")); return }
    if (isNaN(lonNum) || lonNum < -180 || lonNum > 180) { setAddError(S("form.lon.error")); return }
    if (subs.length >= limit) { setAddError(`Limit reached (${limit} active subscriptions for your plan).`); return }

    setAddLoading(true)
    try {
      const body: SubscriptionCreate = { region_name: region.trim(), latitude: latNum, longitude: lonNum, alert_frequency: freq }
      await endpoints.subscriptions.create(body)
      setRegion(""); setLat(""); setLon(""); setFreq("weekly")
      loadSubs()
    } catch (e: unknown) {
      const err = e as ApiError
      setAddError(err?.detail || S("subs.add.error"))
    } finally {
      setAddLoading(false)
    }
  }

  async function onRemove(id: string, token: string) {
    setRemoving(id)
    try {
      await endpoints.subscriptions.unsubscribe(token)
      setSubs((prev) => prev.filter((s) => s.id !== id))
    } finally {
      setRemoving(null)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-slate-800">{S("subs.title")}</h2>
        <p className="mt-1 text-sm text-slate-500">{S("subs.subtitle")}</p>
        <p className="mt-0.5 text-xs text-slate-400">
          {isPremium ? S("subs.limit.premium") : S("subs.limit.free")}
        </p>
      </div>

      {/* Add form */}
      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <h3 className="text-sm font-semibold text-slate-700 mb-3">{S("subs.add.title")}</h3>
        <form onSubmit={onAdd} className="space-y-3 text-sm" noValidate>
          {addError && (
            <div role="alert" className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs">{addError}</div>
          )}
          <Field id="sub-region" label={S("subs.add.region")} value={region} onChange={setRegion} placeholder={S("subs.add.region.ph")} />
          <div className="grid grid-cols-2 gap-3">
            <Field id="sub-lat" label={S("subs.add.lat")} value={lat} onChange={setLat} placeholder={S("form.lat.placeholder")} type="number" step="0.0001" />
            <Field id="sub-lon" label={S("subs.add.lon")} value={lon} onChange={setLon} placeholder={S("form.lon.placeholder")} type="number" step="0.0001" />
          </div>
          <div>
            <label htmlFor="sub-freq" className="block text-xs font-medium text-slate-700">{S("subs.add.freq")}</label>
            <select
              id="sub-freq"
              value={freq}
              onChange={(e) => setFreq(e.target.value as "weekly" | "immediate")}
              className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-800"
            >
              <option value="weekly">{S("subs.add.freq.weekly")}</option>
              <option value="immediate">{S("subs.add.freq.immediate")}</option>
            </select>
          </div>
          <button
            type="submit"
            disabled={addLoading}
            className="rounded-md bg-slate-800 text-white text-sm font-medium px-4 py-2 hover:bg-slate-700 disabled:opacity-60"
          >
            {addLoading ? S("subs.add.busy") : S("subs.add.submit")}
          </button>
        </form>
      </div>

      {/* List */}
      {loading && <p className="text-sm text-slate-500">{S("subs.loading")}</p>}
      {error   && <p className="text-sm text-red-600">{error}</p>}
      {!loading && subs.length === 0 && (
        <p className="text-sm text-slate-500">{S("subs.empty")}</p>
      )}
      {!loading && subs.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="min-w-full text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs font-medium text-slate-500 uppercase tracking-wide">
              <tr>
                <th className="px-4 py-3 text-left">{S("subs.col.region")}</th>
                <th className="px-4 py-3 text-left">{S("subs.col.coords")}</th>
                <th className="px-4 py-3 text-left">{S("subs.col.freq")}</th>
                <th className="px-4 py-3 text-left">{S("subs.col.since")}</th>
                <th className="px-4 py-3 text-left">{S("subs.col.action")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {subs.map((sub) => (
                <tr key={sub.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium text-slate-800">{sub.region_name}</td>
                  <td className="px-4 py-3 text-slate-600 tabular-nums">{sub.latitude.toFixed(2)}, {sub.longitude.toFixed(2)}</td>
                  <td className="px-4 py-3 text-slate-600 capitalize">{sub.alert_frequency}</td>
                  <td className="px-4 py-3 text-slate-500">{new Date(sub.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      disabled={removing === sub.id}
                      onClick={() => onRemove(sub.id, sub.unsubscribe_token)}
                      className="text-xs text-red-600 hover:text-red-800 disabled:opacity-40"
                    >
                      {removing === sub.id ? S("subs.removing") : S("subs.remove")}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// Alerts Tab

function AlertsTab() {
  const [data, setData]       = useState<AlertHistoryResponse | null>(null)
  const [page, setPage]       = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    endpoints.alerts.history({ page, page_size: 10 })
      .then(setData)
      .catch(() => setError(S("alerts.error")))
      .finally(() => setLoading(false))
  }, [page])

  const totalPages = data ? Math.ceil(data.total / data.page_size) : 1

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-slate-800">{S("alerts.title")}</h2>
        <p className="mt-1 text-sm text-slate-500">{S("alerts.subtitle")}</p>
      </div>

      {loading && <p className="text-sm text-slate-500">{S("alerts.loading")}</p>}
      {error   && <p className="text-sm text-red-600">{error}</p>}
      {!loading && !error && data && data.items.length === 0 && (
        <p className="text-sm text-slate-500">{S("alerts.empty")}</p>
      )}
      {!loading && data && data.items.length > 0 && (
        <>
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="min-w-full text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-xs font-medium text-slate-500 uppercase tracking-wide">
                <tr>
                  <th className="px-4 py-3 text-left">{S("alerts.col.type")}</th>
                  <th className="px-4 py-3 text-left">{S("alerts.col.disaster")}</th>
                  <th className="px-4 py-3 text-left">{S("alerts.col.severity")}</th>
                  <th className="px-4 py-3 text-left">{S("alerts.col.message")}</th>
                  <th className="px-4 py-3 text-left">{S("alerts.col.sent")}</th>
                  <th className="px-4 py-3 text-left">{S("alerts.col.status")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((alert: AlertResponse) => (
                  <tr key={alert.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 text-slate-700 whitespace-nowrap">
                      {alert.alert_type === "weekly_digest"
                        ? S("alerts.type.weekly")
                        : S("alerts.type.immediate")}
                    </td>
                    <td className="px-4 py-3 text-slate-700">{alert.disaster_type ?? "—"}</td>
                    <td className="px-4 py-3">
                      {alert.severity_level
                        ? <SeverityBadge level={alert.severity_level} />
                        : <span className="text-slate-400">—</span>}
                    </td>
                    <td className="px-4 py-3 text-slate-600 max-w-xs truncate" title={alert.message_body ?? undefined}>
                      {alert.message_body ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-slate-500 whitespace-nowrap">
                      {alert.sent_at ? new Date(alert.sent_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                        alert.status === "sent"    ? "bg-green-100 text-green-700" :
                        alert.status === "failed"  ? "bg-red-100 text-red-700" :
                                                     "bg-yellow-100 text-yellow-700"
                      }`}>
                        {alert.status === "sent"    ? S("alerts.status.sent") :
                         alert.status === "failed"  ? S("alerts.status.failed") :
                                                      S("alerts.status.pending")}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between text-sm">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1.5 rounded-md border border-slate-200 text-slate-700 disabled:opacity-40"
              >
                {S("history.prev")}
              </button>
              <span className="text-slate-500">
                {Sf("history.page", { page: String(page), total: String(totalPages) })}
              </span>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-3 py-1.5 rounded-md border border-slate-200 text-slate-700 disabled:opacity-40"
              >
                {S("history.next")}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}
