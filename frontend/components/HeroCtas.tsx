// Auth-aware hero call-to-action buttons for the home page.
// Guests see "Create free account"; logged-in users see "Go to dashboard"
// (no "create account" prompt once authenticated). The map CTA is always shown.
// Rendered as a client island inside the Server Component home page.

"use client"

import Link from "next/link"
import { useSession } from "next-auth/react"
import { S } from "@/lib/strings"

export function HeroCtas() {
  const { status } = useSession()
  const isAuthed = status === "authenticated"

  return (
    <div className="mt-8 flex flex-wrap gap-3">
      <Link
        href={isAuthed ? "/dashboard" : "/register"}
        className="inline-flex items-center justify-center rounded-md bg-slate-800 text-white text-sm font-medium px-5 py-2.5 hover:bg-slate-700"
      >
        {isAuthed ? S("home.hero.ctaDashboard") : S("home.hero.ctaPrimary")}
      </Link>
      <Link
        href="/map"
        className="inline-flex items-center justify-center rounded-md border border-slate-300 bg-white text-slate-700 text-sm font-medium px-5 py-2.5 hover:bg-slate-50"
      >
        {S("home.hero.ctaSecondary")}
      </Link>
    </div>
  )
}
