// Shared top navigation — auth-aware Client Component.
//
// Guest:        Map · Analytics · Time Series · Forecast · Pricing · Log In · Sign Up
// Subscriber:   Map · Analytics · Time Series · Forecast · Pricing · Dashboard · [Admin] · Role badge · Log out
//
// Mounted on every page (public + auth + protected). useSession() is fine in
// public pages because AuthBoot wraps the root layout with SessionProvider —
// the hook resolves to null on guest pages, no errors.

"use client"

import Link from "next/link"
import { useSession } from "next-auth/react"
import { S } from "@/lib/strings"
import { RoleBadge } from "@/components/RoleBadge"
import { logoutAndRedirect } from "@/lib/logout"
import { isAdmin } from "@/lib/permissions"

function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="px-3 py-1.5 rounded-md text-sm text-slate-600 hover:bg-slate-100"
    >
      {children}
    </Link>
  )
}

export function Nav() {
  const { data: session, status } = useSession()
  const role = session?.user?.role
  const isAuthed = status === "authenticated"

  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between gap-3">
        <Link href="/" className="font-bold text-slate-800 tracking-tight">
          {S("nav.brand")}
        </Link>

        <nav className="flex items-center gap-1 text-sm">
          <NavLink href="/map">{S("nav.map")}</NavLink>
          <NavLink href="/analytics">{S("nav.analytics")}</NavLink>
          <NavLink href="/analytics/timeseries">{S("nav.timeseries")}</NavLink>
          <NavLink href="/forecast">{S("nav.forecast")}</NavLink>
          <NavLink href="/pricing">{S("nav.pricing")}</NavLink>

          <span className="mx-1 h-6 w-px bg-slate-200" aria-hidden />

          {/* While the session is still resolving, render nothing on the right
              side to avoid a layout flash from guest → authed nav. */}
          {status === "loading" ? (
            <span className="h-7 w-24 rounded-md bg-slate-100 animate-pulse" />
          ) : isAuthed ? (
            <>
              <NavLink href="/dashboard">{S("nav.dashboard")}</NavLink>
              {isAdmin(role) && (
                <NavLink href="/admin">{S("nav.admin")}</NavLink>
              )}
              {role && (
                <span className="mx-1">
                  <RoleBadge role={role} />
                </span>
              )}
              <button
                type="button"
                onClick={() => logoutAndRedirect("/")}
                className="px-3 py-1.5 rounded-md text-sm text-slate-700 hover:bg-slate-100"
              >
                {S("nav.logout")}
              </button>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className="px-3 py-1.5 rounded-md text-sm text-slate-700 hover:bg-slate-100"
              >
                {S("nav.login")}
              </Link>
              <Link
                href="/register"
                className="px-3 py-1.5 rounded-md text-sm bg-slate-800 text-white hover:bg-slate-700"
              >
                {S("nav.register")}
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  )
}
