// Register page — /register (Client Component).
// Calls POST /auth/register via endpoints.auth.register. The backend creates
// the user and prints the verification token to stdout (Phase 6 will replace
// this with a real email). On 201 we show a "check your inbox" success state
// with a link to /verify-email so dev users can paste the token from logs.

"use client"

import Link from "next/link"
import { useState, type FormEvent } from "react"
import { endpoints } from "@/lib/endpoints"
import type { ApiError } from "@/lib/api"
import { S, Sf } from "@/lib/strings"
import { Nav } from "@/components/Nav"

function isEmail(s: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s)
}

type ErrorKey =
  | "short_password"
  | "password_mismatch"
  | "invalid_email"
  | "taken"
  | "generic"
  | null

function errorMessage(key: ErrorKey): string | null {
  switch (key) {
    case "short_password":    return S("auth.register.error.shortPassword")
    case "password_mismatch": return S("auth.register.error.passwordMismatch")
    case "invalid_email":     return S("auth.register.error.invalidEmail")
    case "taken":             return S("auth.register.error.taken")
    case "generic":           return S("auth.register.error.generic")
    default:                  return null
  }
}

export default function RegisterPage() {
  const [fullName, setFullName] = useState("")
  const [email, setEmail]       = useState("")
  const [password, setPassword] = useState("")
  const [confirm, setConfirm]   = useState("")
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState<ErrorKey>(null)
  const [successEmail, setSuccessEmail] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)

    if (!isEmail(email)) { setError("invalid_email"); return }
    if (password.length < 8) { setError("short_password"); return }
    if (password !== confirm) { setError("password_mismatch"); return }

    setLoading(true)
    try {
      await endpoints.auth.register({
        email,
        password,
        full_name: fullName.trim() || null,
      })
      setSuccessEmail(email)
    } catch (e: unknown) {
      const err = e as ApiError
      if (err?.status === 400 && /already/i.test(err.detail ?? "")) {
        setError("taken")
      } else {
        setError("generic")
      }
    } finally {
      setLoading(false)
    }
  }

  if (successEmail) {
    return (
      <>
        <Nav />
        <main className="max-w-md mx-auto px-4 py-12">
          <h1 className="text-2xl font-bold text-slate-800">
            {S("auth.register.successTitle")}
          </h1>
          <p className="mt-3 text-sm text-slate-600">
            {Sf("auth.register.successBody", { email: successEmail })}
          </p>
          <div className="mt-6 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">
            {S("auth.register.successDev")}
          </div>
          <div className="mt-6 flex gap-2">
            <Link
              href="/verify-email"
              className="rounded-md bg-slate-800 text-white text-sm font-medium px-4 py-2 hover:bg-slate-700"
            >
              {S("auth.register.successGoVerify")}
            </Link>
            <Link
              href="/login"
              className="rounded-md border border-slate-300 text-sm font-medium px-4 py-2 hover:bg-slate-50"
            >
              {S("auth.register.loginLink")}
            </Link>
          </div>
        </main>
      </>
    )
  }

  const errMsg = errorMessage(error)

  return (
    <>
      <Nav />
      <main className="max-w-md mx-auto px-4 py-12">
        <h1 className="text-2xl font-bold text-slate-800">{S("auth.register.title")}</h1>
        <p className="mt-2 text-sm text-slate-500">{S("auth.register.subtitle")}</p>

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
            <label htmlFor="fullName" className="block text-sm font-medium text-slate-700">
              {S("auth.fullName.label")}
            </label>
            <input
              id="fullName"
              type="text"
              autoComplete="name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              placeholder={S("auth.fullName.placeholder")}
              className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-800"
            />
          </div>

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
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={S("auth.password.placeholder")}
              className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-800"
            />
          </div>

          <div>
            <label htmlFor="confirm" className="block text-sm font-medium text-slate-700">
              {S("auth.confirm.label")}
            </label>
            <input
              id="confirm"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-800"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-md bg-slate-800 text-white text-sm font-medium px-4 py-2.5 hover:bg-slate-700 disabled:opacity-60"
          >
            {loading ? S("auth.register.busy") : S("auth.register.submit")}
          </button>

          <p className="text-sm text-slate-500 text-center">
            {S("auth.register.haveAccount")}{" "}
            <Link href="/login" className="text-slate-800 font-medium hover:underline">
              {S("auth.register.loginLink")}
            </Link>
          </p>
        </form>
      </main>
    </>
  )
}
