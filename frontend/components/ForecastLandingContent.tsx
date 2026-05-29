// Client Component for the /forecast public landing page.
//
// Three states driven by session status:
//   loading       → spinner (avoids guest flash while NextAuth resolves)
//   authenticated → spinner + router.replace("/dashboard/forecast")
//   unauthenticated → full guest marketing view (no API calls)

"use client"

import { useEffect } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useSession } from "next-auth/react"

import { S } from "@/lib/strings"
import { ForecastTeaser } from "@/components/ForecastTeaser"

export function ForecastLandingContent() {
  const { status } = useSession()
  const router = useRouter()

  useEffect(() => {
    if (status === "authenticated") {
      router.replace("/dashboard/forecast")
    }
  }, [status, router])

  // Show spinner while session resolves OR while redirect is happening.
  // This prevents any flash of the guest view for logged-in users.
  if (status === "loading" || status === "authenticated") {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <div className="h-8 w-8 rounded-full border-2 border-slate-300 border-t-slate-700 animate-spin mx-auto" />
          <p className="mt-3 text-sm text-slate-500">
            {S("forecast.landing.redirect")}
          </p>
        </div>
      </div>
    )
  }

  // Guest view — full marketing teaser
  return (
    <main className="max-w-6xl mx-auto px-4 py-10">
      {/* Hero */}
      <section>
        <h1 className="text-3xl font-bold text-slate-900">
          {S("forecast.landing.hero.title")}
        </h1>
        <p className="mt-3 text-base text-slate-600 max-w-2xl">
          {S("forecast.landing.hero.subtitle")}
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            href="/register"
            className="inline-flex items-center justify-center rounded-md bg-slate-800 text-white text-sm font-semibold px-5 py-2.5 hover:bg-slate-700"
          >
            {S("forecast.landing.cta.signup")}
          </Link>
          <Link
            href="/pricing"
            className="inline-flex items-center justify-center rounded-md border border-slate-300 bg-white text-slate-700 text-sm font-semibold px-5 py-2.5 hover:bg-slate-50"
          >
            {S("forecast.landing.cta.learn")}
          </Link>
        </div>
      </section>

      {/* Blurred calendar teaser — reuses existing ForecastTeaser (no API calls) */}
      <div className="mt-10">
        <ForecastTeaser />
      </div>

      {/* Feature highlight cards */}
      <section className="mt-10 grid grid-cols-1 sm:grid-cols-3 gap-4">
        <FeatureCard
          accent="bg-blue-100 text-blue-700"
          label="01"
          title={S("forecast.landing.feature1.title")}
          body={S("forecast.landing.feature1.body")}
        />
        <FeatureCard
          accent="bg-violet-100 text-violet-700"
          label="02"
          title={S("forecast.landing.feature2.title")}
          body={S("forecast.landing.feature2.body")}
        />
        <FeatureCard
          accent="bg-emerald-100 text-emerald-700"
          label="03"
          title={S("forecast.landing.feature3.title")}
          body={S("forecast.landing.feature3.body")}
        />
      </section>
    </main>
  )
}

function FeatureCard({
  accent,
  label,
  title,
  body,
}: {
  accent: string
  label: string
  title: string
  body: string
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className={`inline-flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold ${accent}`}>
        {label}
      </div>
      <h3 className="mt-3 text-sm font-semibold text-slate-800">{title}</h3>
      <p className="mt-1.5 text-xs text-slate-500 leading-relaxed">{body}</p>
    </div>
  )
}
