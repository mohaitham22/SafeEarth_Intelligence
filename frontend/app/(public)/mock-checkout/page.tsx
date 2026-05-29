// Mock-checkout page — /mock-checkout?session_id=...&plan=...&amount=...
// MockPaymentService.create_checkout_session() redirects here.
// The user clicks "Confirm" which fires POST /premium/webhook with the
// mock-valid signature, completing the payment flow without real money.
//
// Must be Suspense-wrapped (Next.js 14 requires this for useSearchParams()
// in client components rendered as static pages).

"use client"

import { Suspense, useState } from "react"
import { useSearchParams, useRouter } from "next/navigation"
import { Nav } from "@/components/Nav"
import { endpoints } from "@/lib/endpoints"
import { S } from "@/lib/strings"

// ── Inner component (reads URL params — must be inside <Suspense>) ─────────

function MockCheckoutInner() {
  const params    = useSearchParams()
  const router    = useRouter()
  const sessionId = params.get("session_id")
  const plan      = params.get("plan")
  const amount    = params.get("amount")

  const [busy,  setBusy]  = useState(false)
  const [done,  setDone]  = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!sessionId) {
    return (
      <div className="max-w-md mx-auto mt-24 rounded-xl border border-amber-200 bg-amber-50 p-8 text-center">
        <p className="text-sm text-amber-800">{S("checkout.mock.noSession")}</p>
        <a
          href="/pricing"
          className="mt-4 inline-block rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          {S("checkout.mock.backToPricing")}
        </a>
      </div>
    )
  }

  async function handleConfirm() {
    setBusy(true)
    setError(null)
    try {
      await endpoints.premium.confirmMockWebhook(sessionId!)
      setDone(true)
    } catch {
      setError(S("checkout.mock.error.body"))
      setBusy(false)
    }
  }

  // ── Success state ──────────────────────────────────────────────────────────

  if (done) {
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
          {S("checkout.mock.success.title")}
        </h2>
        <p className="mt-2 text-sm text-emerald-700">
          {S("checkout.mock.success.body")}
        </p>
        <button
          type="button"
          onClick={() => router.push("/dashboard")}
          className="mt-6 w-full rounded-md bg-slate-800 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-700"
        >
          {S("checkout.mock.success.cta")}
        </button>
      </div>
    )
  }

  // ── Confirm state ──────────────────────────────────────────────────────────

  return (
    <div className="max-w-md mx-auto mt-16">
      {/* Warning banner */}
      <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        {S("checkout.mock.subtitle")}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
        <h1 className="text-xl font-bold text-slate-800">
          {S("checkout.mock.title")}
        </h1>

        {/* Order summary */}
        <dl className="mt-6 space-y-3 text-sm">
          {plan && (
            <div className="flex justify-between">
              <dt className="text-slate-500">{S("checkout.mock.plan")}</dt>
              <dd className="font-medium text-slate-800 capitalize">{plan}</dd>
            </div>
          )}
          {amount && (
            <div className="flex justify-between">
              <dt className="text-slate-500">{S("checkout.mock.amount")}</dt>
              <dd className="font-medium text-slate-800">${parseFloat(amount).toFixed(2)}</dd>
            </div>
          )}
          <div className="flex justify-between border-t border-slate-100 pt-3">
            <dt className="text-slate-500">{S("checkout.mock.session")}</dt>
            <dd className="font-mono text-xs text-slate-600 break-all">{sessionId}</dd>
          </div>
        </dl>

        {error && (
          <div className="mt-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <p className="font-medium">{S("checkout.mock.error.title")}</p>
            <p className="mt-1">{error}</p>
          </div>
        )}

        <button
          type="button"
          onClick={handleConfirm}
          disabled={busy}
          className={`mt-6 w-full rounded-md bg-slate-800 px-4 py-2.5 text-sm font-medium text-white transition-opacity ${
            busy ? "cursor-wait opacity-60" : "hover:bg-slate-700"
          }`}
        >
          {busy ? S("checkout.mock.busy") : S("checkout.mock.cta")}
        </button>

        <a
          href="/pricing"
          className="mt-3 block text-center text-xs text-slate-400 hover:text-slate-600"
        >
          {S("checkout.mock.backToPricing")}
        </a>
      </div>
    </div>
  )
}

// ── Page shell (Suspense required for useSearchParams in static prerender) ──

export default function MockCheckoutPage() {
  return (
    <>
      <Nav />
      <main className="min-h-screen bg-slate-50 px-4 py-8">
        <Suspense
          fallback={
            <div className="max-w-md mx-auto mt-16 animate-pulse rounded-xl border border-slate-200 bg-white p-8 h-64" />
          }
        >
          <MockCheckoutInner />
        </Suspense>
      </main>
    </>
  )
}
