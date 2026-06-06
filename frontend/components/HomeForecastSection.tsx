// Role-aware home "30-day forecast" section. Decides what each role sees using
// the Phase 1 permission helper (lib/permissions):
//   - Guest / not-logged-in (the "free" bucket): ADS (admin-managed; Studio = Phase 10).
//   - Subscriber (logged-in, below premium): "Upgrade to Premium" prompt (never "sign up").
//   - Premium / Admin: the REAL 30-day forecast for their newest subscription region.
//
// `ads` is fetched server-side by the home page and passed in (guests render it
// without a client round-trip).

"use client"

import Link from "next/link"
import { useSession } from "next-auth/react"
import { S } from "@/lib/strings"
import { meetsRole } from "@/lib/permissions"
import { HomeAds } from "@/components/HomeAds"
import { HomePremiumForecast } from "@/components/HomePremiumForecast"
import type { Ad } from "@/types"

export function HomeForecastSection({ ads }: { ads: Ad[] }) {
  const { data: session, status } = useSession()

  // Not logged in (and the brief loading window) = the "guest + free" bucket → ADS.
  if (status !== "authenticated") return <HomeAds ads={ads} />

  const role = session?.user?.role

  // Premium / Admin → the real 30-day forecast.
  if (meetsRole(role, "premium")) return <HomePremiumForecast />

  // Logged-in subscriber (below premium) → upgrade prompt (NOT "sign up to unlock").
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6">
      <h2 className="text-lg font-semibold text-slate-800">
        {S("home.forecast.upgrade.title")}
      </h2>
      <p className="mt-2 max-w-xl text-sm text-slate-600">
        {S("home.forecast.upgrade.body")}
      </p>
      <Link
        href="/pricing"
        className="mt-4 inline-flex items-center justify-center rounded-md bg-slate-800 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
      >
        {S("home.forecast.upgrade.cta")}
      </Link>
    </section>
  )
}
