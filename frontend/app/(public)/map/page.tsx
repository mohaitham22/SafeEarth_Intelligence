// Risk heatmap page — /map (CLAUDE.md Feature 2).
//
// SSR-SAFE: Leaflet imports `window` at module load time, which crashes
// during Next.js server rendering. We load <RiskMap /> through next/dynamic
// with { ssr: false } so the bundle only runs in the browser. The page shell
// itself can stay a Server Component (no hooks).

import dynamic from "next/dynamic"
import Link from "next/link"
import { Nav } from "@/components/Nav"
import { S } from "@/lib/strings"

const RiskMap = dynamic(() => import("@/components/RiskMap"), {
  ssr: false,
  loading: () => (
    <div className="h-[70vh] min-h-[420px] rounded-xl border border-slate-200 bg-slate-50 flex items-center justify-center text-sm text-slate-500">
      {S("map.loading")}
    </div>
  ),
})

export default function MapPage() {
  return (
    <>
      <Nav />
      <main className="max-w-6xl mx-auto px-4 py-8">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-slate-800">
              {S("map.title")}
            </h1>
            <p className="mt-1 text-sm text-slate-500 max-w-2xl">
              {S("map.subtitle")}
            </p>
          </div>
          <Link
            href="/dashboard"
            className="text-sm text-slate-700 underline hover:text-slate-900"
          >
            {S("nav.brand")} →
          </Link>
        </div>

        <div className="mt-6">
          <RiskMap />
        </div>
      </main>
    </>
  )
}
