// Verify-email page — /verify-email (Client Component).
// Two entry modes:
//   1. ?token=... in the URL (real email-link click — auto-submits)
//   2. Empty — user pastes the token printed to the backend console (dev path)

"use client"

import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Suspense, useEffect, useRef, useState, type FormEvent } from "react"
import { endpoints } from "@/lib/endpoints"
import type { ApiError } from "@/lib/api"
import { S } from "@/lib/strings"
import { Nav } from "@/components/Nav"

// Suspense wrap required by Next.js 14 for useSearchParams() in static builds.
export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailInner />
    </Suspense>
  )
}

function VerifyEmailInner() {
  const params  = useSearchParams()
  const router  = useRouter()
  const initial = params.get("token") ?? ""

  const [token, setToken]     = useState(initial)
  const [loading, setLoading] = useState(false)
  const [done, setDone]       = useState(false)
  const [error, setError]     = useState<string | null>(null)
  const autoTried = useRef(false)

  async function submit(rawToken: string) {
    setError(null)
    if (!rawToken || rawToken.length < 8) {
      setError(S("auth.verify.error.invalid"))
      return
    }
    setLoading(true)
    try {
      await endpoints.auth.verifyEmail({ token: rawToken })
      setDone(true)
    } catch (e: unknown) {
      const err = e as ApiError
      setError(err?.detail ?? S("auth.verify.error.invalid"))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!autoTried.current && initial) {
      autoTried.current = true
      submit(initial)
    }
    // intentional: run once on mount with the URL-provided token
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function onSubmit(e: FormEvent) {
    e.preventDefault()
    submit(token.trim())
  }

  if (done) {
    return (
      <>
        <Nav />
        <main className="max-w-md mx-auto px-4 py-12">
          <h1 className="text-2xl font-bold text-slate-800">
            {S("auth.verify.successTitle")}
          </h1>
          <p className="mt-3 text-sm text-slate-600">{S("auth.verify.successBody")}</p>
          <button
            onClick={() => router.push("/login")}
            className="mt-6 rounded-md bg-slate-800 text-white text-sm font-medium px-4 py-2 hover:bg-slate-700"
          >
            {S("auth.verify.successCta")}
          </button>
        </main>
      </>
    )
  }

  return (
    <>
      <Nav />
      <main className="max-w-md mx-auto px-4 py-12">
        <h1 className="text-2xl font-bold text-slate-800">{S("auth.verify.title")}</h1>
        <p className="mt-2 text-sm text-slate-500">{S("auth.verify.subtitle")}</p>

        <form onSubmit={onSubmit} className="mt-8 space-y-4" noValidate>
          {error && (
            <div
              role="alert"
              className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm"
            >
              {error}
            </div>
          )}

          <div>
            <label htmlFor="token" className="block text-sm font-medium text-slate-700">
              {S("auth.verify.tokenLabel")}
            </label>
            <input
              id="token"
              type="text"
              autoComplete="off"
              required
              value={token}
              onChange={(e) => setToken(e.target.value)}
              className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-slate-800"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-md bg-slate-800 text-white text-sm font-medium px-4 py-2.5 hover:bg-slate-700 disabled:opacity-60"
          >
            {loading ? S("auth.verify.busy") : S("auth.verify.submit")}
          </button>

          <p className="text-xs text-slate-400 text-center">
            <Link href="/login" className="hover:underline">{S("auth.login.submit")}</Link>
          </p>
        </form>
      </main>
    </>
  )
}
