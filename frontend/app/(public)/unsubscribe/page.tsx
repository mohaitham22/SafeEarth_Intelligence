// Public unsubscribe page — /unsubscribe?token=...
// Linked from the one-click unsubscribe footer in every Premium alert email.
// Calls DELETE /api/v1/subscriptions/{token} (public endpoint, no auth needed).
// Must be Suspense-wrapped (Next.js 14 requires this for useSearchParams()
// in client components rendered as static pages).

"use client"

import { Suspense, useEffect, useState } from "react"
import { useSearchParams } from "next/navigation"
import { Nav } from "@/components/Nav"
import { endpoints } from "@/lib/endpoints"
import { apiClient } from "@/lib/api"
import { S } from "@/lib/strings"

// ── Inner component (reads URL params — must be inside <Suspense>) ──────────

function UnsubscribeInner() {
  const params = useSearchParams()
  const token  = params.get("token")

  const [status, setStatus] = useState<"loading" | "success" | "error">("loading")

  useEffect(() => {
    if (!token) {
      setStatus("error")
      return
    }

    endpoints.subscriptions
      .unsubscribe(token, apiClient)
      .then(() => setStatus("success"))
      .catch(() => setStatus("error"))
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  if (!token) {
    return (
      <div className="max-w-md mx-auto mt-24 rounded-xl border border-amber-200 bg-amber-50 p-8 text-center">
        <p className="text-sm text-amber-800">{S("unsubscribe.noToken")}</p>
        <a
          href="/"
          className="mt-4 inline-block rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          {S("unsubscribe.home")}
        </a>
      </div>
    )
  }

  if (status === "loading") {
    return (
      <div className="max-w-md mx-auto mt-24 rounded-xl border border-slate-200 bg-white p-8 text-center">
        <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-slate-600" />
        <p className="text-sm text-slate-500">{S("unsubscribe.loading")}</p>
      </div>
    )
  }

  if (status === "success") {
    return (
      <div className="max-w-md mx-auto mt-24 rounded-xl border border-emerald-200 bg-emerald-50 p-8 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100">
          <svg
            className="h-6 w-6 text-emerald-600"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        </div>
        <h2 className="text-lg font-semibold text-emerald-800">
          {S("unsubscribe.success.title")}
        </h2>
        <p className="mt-2 text-sm text-emerald-700">
          {S("unsubscribe.success.body")}
        </p>
        <a
          href="/"
          className="mt-6 inline-block w-full rounded-md border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          {S("unsubscribe.home")}
        </a>
      </div>
    )
  }

  // error state
  return (
    <div className="max-w-md mx-auto mt-24 rounded-xl border border-red-200 bg-red-50 p-8 text-center">
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100">
        <svg
          className="h-6 w-6 text-red-600"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </div>
      <h2 className="text-lg font-semibold text-red-800">
        {S("unsubscribe.error.title")}
      </h2>
      <p className="mt-2 text-sm text-red-700">
        {S("unsubscribe.error.body")}
      </p>
      <a
        href="/"
        className="mt-6 inline-block w-full rounded-md border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
      >
        {S("unsubscribe.home")}
      </a>
    </div>
  )
}

// ── Page shell (Suspense required for useSearchParams in static prerender) ──

export default function UnsubscribePage() {
  return (
    <>
      <Nav />
      <main className="min-h-screen bg-slate-50 px-4 py-8">
        <Suspense
          fallback={
            <div className="max-w-md mx-auto mt-24 animate-pulse rounded-xl border border-slate-200 bg-white p-8 h-48" />
          }
        >
          <UnsubscribeInner />
        </Suspense>
      </main>
    </>
  )
}
