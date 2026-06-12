// Global analytics — /analytics (CLAUDE.md Feature 2).
// Server Component: fetches the three public /regions/* endpoints in parallel
// at request time. Next.js then caches the rendered HTML for `revalidate`
// seconds (24h here — matches backend Cache-Control: max-age=3600 ≤ 24h).
// All four endpoints are served from in-memory precomputed JSON, so this
// page never touches the database at runtime.

import { Nav } from "@/components/Nav"
import { S } from "@/lib/strings"
import { endpoints } from "@/lib/endpoints"
import { AnalyticsPanels } from "@/components/analytics/AnalyticsPanels"
import type {
  ContinentStats,
  InsuranceRatios,
  TrendsData,
} from "@/types"

export const revalidate = 86400

interface Bundle {
  trends:     TrendsData
  continents: ContinentStats
  insurance:  InsuranceRatios
}

async function loadBundle(): Promise<{ bundle: Bundle | null; error: string | null }> {
  try {
    const [trends, continents, insurance] = await Promise.all([
      endpoints.regions.trends(),
      endpoints.regions.continentStats(),
      endpoints.regions.insuranceGap(),
    ])
    return { bundle: { trends, continents, insurance }, error: null }
  } catch {
    return { bundle: null, error: S("error.publicData.body") }
  }
}

export default async function AnalyticsPage() {
  const { bundle, error } = await loadBundle()

  return (
    <>
      <Nav />
      <main className="max-w-6xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-slate-800">{S("analytics.title")}</h1>
        <p className="mt-1 text-sm text-slate-500 max-w-3xl">{S("analytics.subtitle")}</p>

        {bundle ? (
          <div className="mt-6">
            <AnalyticsPanels
              trends={bundle.trends}
              continents={bundle.continents}
              insurance={bundle.insurance}
            />
          </div>
        ) : (
          <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            <p className="font-medium">{S("error.publicData.title")}</p>
            <p className="mt-1 text-xs">{error}</p>
          </div>
        )}
      </main>
    </>
  )
}
