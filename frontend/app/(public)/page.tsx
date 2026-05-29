// Home / public dashboard — Server Component.
// Pulls headline numbers from public /regions/* endpoints (no auth) and
// renders a guest-locked 30-Day Forecast teaser per Feature 10.
// Guests CANNOT trigger a real forecast from this page — the teaser is purely
// visual and the only call to action routes to /register.
// Revalidates every hour (matches the backend Cache-Control: max-age=3600).

import Link from "next/link"
import { S, Sf } from "@/lib/strings"
import { endpoints } from "@/lib/endpoints"
import { Nav } from "@/components/Nav"
import { ForecastTeaser } from "@/components/ForecastTeaser"
import { formatCompactInt } from "@/lib/format"
import type { TrendsData, TimeSeriesData } from "@/types"

export const revalidate = 3600

interface PublicSummary {
  // Total events: sum of continent total_events — covers the full 1900–2021 dataset range.
  // Source: /regions/continent-stats
  totalEvents:      number
  // Total deaths recorded in EM-DAT (non-null by_year entries only; excludes years with missing data).
  // Source: /regions/timeseries by_year
  totalDeaths:      number
  // First year of data (from timeseries.by_decade[type][0].decade) and last year (from by_year).
  // Source: /regions/timeseries
  yearFrom:         number
  yearTo:           number
  // Disaster type with the most events across all trend decades.
  // Source: /regions/trends (argmax of per-type sums)
  topDisasterType:  string
  // Count of distinct disaster type keys from /regions/trends (excludes "decades").
  disasterTypes:    number
  loadFailed:       boolean
}

async function loadPublicSummary(): Promise<PublicSummary> {
  try {
    const [trends, continents, ts] = await Promise.all([
      endpoints.regions.trends(),
      endpoints.regions.continentStats(),
      endpoints.regions.timeseries(),
    ])

    const types = Object.keys(trends).filter((k) => k !== "decades")

    // Total events from continentStats covers the full 1900–2021 range (more complete than
    // trends.json which only spans 1950–2020).
    const totalEvents = Object.values(continents).reduce(
      (sum, c) => sum + c.total_events,
      0,
    )

    // Most common disaster type: sum each type's decade event counts and pick the max.
    let topDisasterType = ""
    let topCount = 0
    for (const t of types) {
      const counts = (trends as TrendsData)[t]
      if (Array.isArray(counts)) {
        const n = counts.reduce((a, b) => a + b, 0)
        if (n > topCount) {
          topCount = n
          topDisasterType = t
        }
      }
    }

    // Total recorded deaths: sum non-null by_year death entries across all disaster types.
    // Excludes years where EM-DAT has no death data (these are genuinely missing, not zero).
    let totalDeaths = 0
    for (const typeData of Object.values((ts as TimeSeriesData).by_year)) {
      for (const entry of typeData) {
        if (entry.deaths !== null) totalDeaths += entry.deaths
      }
    }

    // Year range: first decade from by_decade (= 1900 per EM-DAT history),
    // last year from by_year (= 2021 per train CSV end date).
    let yearFrom = 9999
    let yearTo = 0
    for (const typeData of Object.values((ts as TimeSeriesData).by_decade)) {
      if (typeData.length > 0) yearFrom = Math.min(yearFrom, typeData[0].decade)
    }
    for (const typeData of Object.values((ts as TimeSeriesData).by_year)) {
      if (typeData.length > 0)
        yearTo = Math.max(yearTo, typeData[typeData.length - 1].year)
    }

    return {
      totalEvents,
      totalDeaths,
      yearFrom: yearFrom === 9999 ? 1900 : yearFrom,
      yearTo,
      topDisasterType,
      disasterTypes: types.length,
      loadFailed: false,
    }
  } catch {
    return {
      totalEvents: 0,
      totalDeaths: 0,
      yearFrom: 1900,
      yearTo: 2021,
      topDisasterType: "",
      disasterTypes: 0,
      loadFailed: true,
    }
  }
}

function fmt(n: number): string {
  return new Intl.NumberFormat("en-US").format(n)
}

function fmtYear(from: number, to: number): string {
  return `${from}–${to}`
}

export default async function HomePage() {
  const summary = await loadPublicSummary()

  return (
    <>
      <Nav />

      <main>
        {/* Hero ------------------------------------------------------- */}
        <section className="border-b border-slate-200 bg-white">
          <div className="max-w-6xl mx-auto px-4 py-16">
            <p className="text-xs font-semibold tracking-wider uppercase text-slate-500">
              {S("home.hero.eyebrow")}
            </p>
            <h1 className="mt-3 text-4xl sm:text-5xl font-bold text-slate-900 max-w-3xl leading-tight">
              {S("home.hero.title")}
            </h1>
            <p className="mt-4 text-lg text-slate-600 max-w-2xl">
              {S("home.hero.subtitle")}
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                href="/register"
                className="inline-flex items-center justify-center rounded-md bg-slate-800 text-white text-sm font-medium px-5 py-2.5 hover:bg-slate-700"
              >
                {S("home.hero.ctaPrimary")}
              </Link>
              <Link
                href="/map"
                className="inline-flex items-center justify-center rounded-md border border-slate-300 bg-white text-slate-700 text-sm font-medium px-5 py-2.5 hover:bg-slate-50"
              >
                {S("home.hero.ctaSecondary")}
              </Link>
            </div>
          </div>
        </section>

        {/* Summary stats from /regions/* ------------------------------ */}
        <section className="max-w-6xl mx-auto px-4 py-12">
          <h2 className="text-xl font-semibold text-slate-800">
            {S("home.summary.title")}
          </h2>

          {summary.loadFailed ? (
            <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              <p className="font-medium">{S("error.publicData.title")}</p>
              <p className="mt-1 text-xs">{S("error.publicData.body")}</p>
            </div>
          ) : (
            <>
              <div className="mt-6 grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
                {/* continentStats sum: full 1900–2021 range, 14,476 events */}
                <StatCard
                  value={fmt(summary.totalEvents)}
                  label={S("home.summary.totalEvents")}
                />
                {/* timeseries by_year sum of non-null deaths across all types */}
                <StatCard
                  value={formatCompactInt(summary.totalDeaths)}
                  label={S("home.summary.totalDeaths")}
                />
                {/* by_decade first decade → by_year last year */}
                <StatCard
                  value={fmtYear(summary.yearFrom, summary.yearTo)}
                  label={S("home.summary.coverage")}
                />
                {/* argmax of per-type sums from trends.json */}
                <StatCard
                  value={summary.topDisasterType}
                  label={S("home.summary.topType")}
                />
                {/* count of disaster-type keys from trends.json */}
                <StatCard
                  value={String(summary.disasterTypes)}
                  label={S("home.summary.typeCount")}
                />
              </div>
              <p className="mt-3 text-xs text-slate-400">
                {S("home.summary.note")}
              </p>
            </>
          )}
        </section>

        {/* Insight cards ----------------------------------------------- */}
        <section className="max-w-6xl mx-auto px-4 pb-12 grid grid-cols-1 md:grid-cols-2 gap-4">
          <InsightCard
            title={S("home.trends.title")}
            body={S("home.trends.insight")}
            href="/analytics"
            cta={S("home.trends.cta")}
            tone="orange"
          />
          <InsightCard
            title={S("home.insurance.title")}
            body={S("home.insurance.insight")}
            href="/analytics"
            cta={S("home.insurance.cta")}
            tone="blue"
          />
        </section>

        {/* 30-Day Forecast teaser ------------------------------------- */}
        <section className="max-w-6xl mx-auto px-4 pb-12">
          <ForecastTeaser />
        </section>

        {/* Features grid ---------------------------------------------- */}
        <section className="border-t border-slate-200 bg-white">
          <div className="max-w-6xl mx-auto px-4 py-12">
            <h2 className="text-xl font-semibold text-slate-800">
              {S("home.features.title")}
            </h2>
            <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
              <FeatureCard
                href="/map"
                title={S("home.features.map.title")}
                body={S("home.features.map.body")}
              />
              <FeatureCard
                href="/analytics"
                title={S("home.features.analytics.title")}
                body={S("home.features.analytics.body")}
              />
              <FeatureCard
                href="/pricing"
                title={S("home.features.pricing.title")}
                body={S("home.features.pricing.body")}
              />
            </div>
          </div>
        </section>

        {/* Footer ----------------------------------------------------- */}
        <footer className="border-t border-slate-200 bg-white">
          <div className="max-w-6xl mx-auto px-4 py-8 text-xs text-slate-500">
            <p>
              {Sf("home.footer.tagline", {})} {S("app.title")}.
            </p>
          </div>
        </footer>
      </main>
    </>
  )
}

// ---------- small UI atoms (file-local, no styles outside Tailwind) -----

function StatCard({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="text-3xl font-bold text-slate-900 tabular-nums">{value}</div>
      <div className="mt-1 text-sm text-slate-500">{label}</div>
    </div>
  )
}

function InsightCard(props: {
  title: string
  body: string
  href: string
  cta: string
  tone: "orange" | "blue"
}) {
  const toneClass =
    props.tone === "orange"
      ? "border-orange-200 bg-orange-50"
      : "border-blue-200 bg-blue-50"
  return (
    <div className={`rounded-xl border ${toneClass} p-5`}>
      <h3 className="font-semibold text-slate-800">{props.title}</h3>
      <p className="mt-2 text-sm text-slate-700">{props.body}</p>
      <Link
        href={props.href}
        className="mt-4 inline-flex items-center text-sm font-medium text-slate-800 hover:underline"
      >
        {props.cta} →
      </Link>
    </div>
  )
}

function FeatureCard(props: { href: string; title: string; body: string }) {
  return (
    <Link
      href={props.href}
      className="block rounded-xl border border-slate-200 bg-white p-5 hover:border-slate-300 hover:shadow-sm transition"
    >
      <h3 className="font-semibold text-slate-800">{props.title}</h3>
      <p className="mt-2 text-sm text-slate-600">{props.body}</p>
    </Link>
  )
}
