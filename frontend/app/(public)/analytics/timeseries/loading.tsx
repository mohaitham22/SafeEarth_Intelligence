// Skeleton shown by Next.js while the Server Component on page.tsx awaits
// /regions/timeseries. Renders once per revalidate window (24h).

import { Nav } from "@/components/Nav"

export default function TimeSeriesLoading() {
  return (
    <>
      <Nav />
      <main className="max-w-6xl mx-auto px-4 py-8">
        {/* Page heading skeleton */}
        <div className="h-7 w-72 bg-slate-200 rounded animate-pulse" />
        <div className="mt-2 h-4 w-[480px] bg-slate-100 rounded animate-pulse" />

        <div className="mt-6 space-y-5">
          {/* Insight callout skeleton */}
          <div className="h-16 w-full rounded-lg border border-orange-100 bg-orange-50 animate-pulse" />

          {/* Chart card skeleton */}
          <div className="rounded-xl border border-slate-200 bg-white p-6">
            <div className="h-5 w-64 bg-slate-200 rounded animate-pulse" />
            <div className="mt-2 h-3 w-96 bg-slate-100 rounded animate-pulse" />

            {/* Filter bar skeleton */}
            <div className="mt-4 flex gap-4">
              <div className="h-12 w-44 bg-slate-100 rounded-lg animate-pulse" />
              <div className="h-12 w-36 bg-slate-100 rounded-lg animate-pulse" />
            </div>

            {/* Chart area skeleton */}
            <div className="mt-5 h-[540px] bg-slate-50 rounded-lg animate-pulse" />
          </div>
        </div>
      </main>
    </>
  )
}
