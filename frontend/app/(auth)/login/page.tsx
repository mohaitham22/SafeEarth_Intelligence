// Login page — /login (Client Component).
// Calls signIn("credentials") from NextAuth v5. Authorize() in /auth.ts
// throws CredentialsSignin subclasses whose `code` we read off the result to
// distinguish "wrong password" (401) from "unverified email" (400) per
// CLAUDE.md auth rules.

"use client"

import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { Suspense, useState, type FormEvent } from "react"
import { signIn } from "next-auth/react"
import { S } from "@/lib/strings"
import { Nav } from "@/components/Nav"

type ErrorKey = "invalid" | "unverified" | "network" | "generic" | null

function errorMessage(key: ErrorKey): string | null {
  switch (key) {
    case "invalid":    return S("auth.error.invalid")
    case "unverified": return S("auth.error.unverified")
    case "network":    return S("auth.error.network")
    case "generic":    return S("auth.error.generic")
    default:           return null
  }
}

function mapErrorCode(code: string | undefined | null): ErrorKey {
  switch (code) {
    case "unverified_email":    return "unverified"
    case "invalid_credentials": return "invalid"
    case "network_error":       return "network"
    default:                    return "generic"
  }
}

// useSearchParams() needs a Suspense boundary in Next.js 14 static prerender.
// Splitting the inner component out and wrapping it in <Suspense> satisfies
// that without losing the URL-driven `?from=` redirect target.
export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginInner />
    </Suspense>
  )
}

function LoginInner() {
  const router      = useRouter()
  const params      = useSearchParams()
  const redirectTo  = params.get("from") || "/dashboard"

  const [email, setEmail]       = useState("")
  const [password, setPassword] = useState("")
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState<ErrorKey>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)

    if (!email.includes("@") || email.length < 5) {
      setError("invalid")
      return
    }
    if (password.length < 1) {
      setError("invalid")
      return
    }

    setLoading(true)
    const result = await signIn("credentials", {
      email,
      password,
      redirect: false,
    })
    setLoading(false)

    if (!result) {
      setError("generic")
      return
    }
    if (result.error) {
      const codeField = (result as { code?: string }).code
      setError(mapErrorCode(codeField ?? result.error))
      return
    }
    router.push(redirectTo)
    router.refresh()
  }

  const errMsg = errorMessage(error)

  return (
    <>
      <Nav />
      <main className="max-w-md mx-auto px-4 py-12">
        <h1 className="text-2xl font-bold text-slate-800">{S("auth.login.title")}</h1>
        <p className="mt-2 text-sm text-slate-500">{S("auth.login.subtitle")}</p>

        <form onSubmit={onSubmit} className="mt-8 space-y-4" noValidate>
          {errMsg && (
            <div
              role="alert"
              className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm"
            >
              {errMsg}
            </div>
          )}

          <div>
            <label htmlFor="email" className="block text-sm font-medium text-slate-700">
              {S("auth.email.label")}
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={S("auth.email.placeholder")}
              className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-800"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-slate-700">
              {S("auth.password.label")}
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-800"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-md bg-slate-800 text-white text-sm font-medium px-4 py-2.5 hover:bg-slate-700 disabled:opacity-60"
          >
            {loading ? S("auth.login.busy") : S("auth.login.submit")}
          </button>

          <p className="text-sm text-slate-500 text-center">
            {S("auth.login.noAccount")}{" "}
            <Link href="/register" className="text-slate-800 font-medium hover:underline">
              {S("auth.login.signupLink")}
            </Link>
          </p>
        </form>
      </main>
    </>
  )
}
