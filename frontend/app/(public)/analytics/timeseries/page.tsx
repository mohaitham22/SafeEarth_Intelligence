// /analytics/timeseries — Feature 9 standalone Time Series page.
// Server Component: fetches /regions/timeseries (precomputed JSON, no DB).
// Rendered HTML is cached for revalidate seconds (24h) — same as analytics page.

import { Nav } from "@/components/Nav"
import { S } from "@/lib/strings"
import { endpoints } from "@/lib/endpoints"
import { TimeSeriesPageContent } from "@/components/analytics/TimeSeriesPageContent"
import type { TimeSeriesData } from "@/types"

export const revalidate = 86400

async function loadData(): Promise<{ data: TimeSeriesData | null; error: string | null }> {
  try {
    const data = await endpoints.regions.timeseries()
    return { data, error: null }
  } catch {
    return { data: null, error: S("error.publicData.body") }
  }
}

export default async function TimeSeriesPage() {
  const { data, error } = await loadData()

  return (
    <>
      <Nav />
      <main className="max-w-6xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-slate-800">
          {S("timeseries.page.title")}
        </h1>
        <p className="mt-1 text-sm text-slate-500 max-w-3xl">
          {S("timeseries.page.subtitle")}
        </p>

        <div className="mt-6">
          {data ? (
            <TimeSeriesPageContent data={data} />
          ) : (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              <p className="font-medium">{S("error.publicData.title")}</p>
              <p className="mt-1 text-xs">{error}</p>
            </div>
          )}
        </div>
      </main>
    </>
  )
}
