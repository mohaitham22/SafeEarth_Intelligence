// Guest-only locked forecast teaser. Pure decoration — DOES NOT call
// /predictions/forecast-30d. The grid is a static 30-cell skeleton with a
// blurred overlay; the only interactive element is the "Create free account"
// CTA that routes to /register. Once a user signs in and reaches
// /dashboard/forecast, that page calls the real endpoint (Subscriber+, 5/hour).

import Link from "next/link"
import { S } from "@/lib/strings"

// 5 columns x 6 rows = 30 cells. Severity is faked so the gradient hints at
// what the real product looks like without implying data on a guest view.
const TEASER_TONES = [
  // 30 tailwind background classes (cycled). Severity → tone mapping.
  "bg-green-200",  "bg-green-300",  "bg-yellow-200", "bg-yellow-300", "bg-orange-200",
  "bg-green-200",  "bg-yellow-200", "bg-yellow-300", "bg-orange-200", "bg-orange-300",
  "bg-yellow-200", "bg-yellow-300", "bg-orange-300", "bg-orange-400", "bg-red-300",
  "bg-yellow-300", "bg-orange-300", "bg-orange-400", "bg-red-300",    "bg-red-400",
  "bg-orange-300", "bg-orange-400", "bg-red-300",    "bg-red-400",    "bg-red-500",
  "bg-orange-200", "bg-orange-300", "bg-orange-400", "bg-red-400",    "bg-red-500",
]

export function ForecastTeaser() {
  return (
    <section className="relative rounded-2xl border border-slate-200 bg-white p-6 overflow-hidden">
      <h2 className="text-lg font-semibold text-slate-800">
        {S("home.forecast.title")}
      </h2>
      <p className="mt-2 text-sm text-slate-600 max-w-xl">
        {S("home.forecast.body")}
      </p>

      <div className="mt-6 relative">
        {/* Locked grid — visually blurred. No interactivity. */}
        <div
          aria-hidden
          className="grid grid-cols-5 gap-2 select-none pointer-events-none filter blur-[2px] opacity-80"
        >
          {TEASER_TONES.map((tone, i) => (
            <div
              key={i}
              className={`aspect-square rounded-md ${tone}`}
            />
          ))}
        </div>

        {/* Overlay with CTA */}
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
          <div className="rounded-xl bg-white/90 backdrop-blur-sm border border-slate-200 px-6 py-5 shadow-sm">
            <p className="text-sm font-semibold text-slate-800">
              {S("home.forecast.locked")}
            </p>
            <Link
              href="/register"
              className="mt-3 inline-flex items-center justify-center rounded-md bg-slate-800 text-white text-sm font-medium px-4 py-2 hover:bg-slate-700"
            >
              {S("home.forecast.cta")}
            </Link>
          </div>
        </div>
      </div>

      <p className="mt-6 text-xs text-slate-400">
        {S("home.forecast.disclaimer")}
      </p>
    </section>
  )
}
