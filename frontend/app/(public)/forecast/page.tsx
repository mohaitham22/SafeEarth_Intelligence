// /forecast — public landing page for the 30-Day Forecast feature.
//
// GUESTS:       Full marketing teaser — blurred calendar, feature highlights, CTAs.
//               Zero API calls; no prediction data shown.
// AUTHENTICATED: Client child detects session and immediately redirects to
//               /dashboard/forecast (the real tool). Spinner shown while
//               session resolves so there is zero flash of guest content.

import { Suspense } from "react"
import { Nav } from "@/components/Nav"
import { ForecastLandingContent } from "@/components/ForecastLandingContent"

export default function ForecastLandingPage() {
  return (
    <>
      <Nav />
      <Suspense fallback={
        <div className="flex items-center justify-center min-h-[60vh]">
          <span className="h-6 w-40 rounded-md bg-slate-100 animate-pulse" />
        </div>
      }>
        <ForecastLandingContent />
      </Suspense>
    </>
  )
}
