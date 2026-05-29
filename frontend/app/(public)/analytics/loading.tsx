// Skeleton shown by Next.js while the Server Component on page.tsx awaits its
// four /regions/* fetches. Renders only once per revalidate window (24h),
// then the actual page is cached.

import { Nav } from "@/components/Nav"

export default function AnalyticsLoading() {
  return (
    <>
      <Nav />
      <main className="max-w-6xl mx-auto px-4 py-8">
        <div className="h-7 w-72 bg-slate-200 rounded animate-pulse" />
        <div className="mt-2 h-4 w-96 bg-slate-100 rounded animate-pulse" />
        <div className="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-4">
          {[0, 1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-72 rounded-xl border border-slate-200 bg-slate-50 animate-pulse"
            />
          ))}
        </div>
      </main>
    </>
  )
}
