// Auth-aware middleware (NextAuth v5).
//
// SECURITY MODEL:
//   This file is a UX convenience only. The real authorisation boundary is
//   in the backend (FastAPI Depends(get_current_user / require_admin /
//   require_premium) on every protected route). Even if someone bypasses
//   this middleware (e.g. by editing the build), the backend will still 401
//   /403. Do not move any sensitive logic out of the backend in reliance on
//   these redirects.
//
// RULES:
//   /dashboard, /dashboard/forecast, /alerts, /subscriptions, /admin
//     → require an authenticated session, else redirect to /login?from=<path>.
//   /admin
//     → ALSO require session.user.role === "admin", else redirect to
//       /dashboard. (UX only — backend re-enforces it.)

import { NextResponse } from "next/server"
import { auth } from "@/auth"
import { isAdmin } from "@/lib/permissions"

export default auth((req) => {
  const session  = req.auth
  const pathname = req.nextUrl.pathname
  const search   = req.nextUrl.search

  // Unauthenticated → bounce to /login with the original destination.
  if (!session) {
    const url = new URL("/login", req.url)
    url.searchParams.set("from", pathname + search)
    return NextResponse.redirect(url)
  }

  // Admin-route UX gate: non-admins land on /dashboard instead of seeing a
  // backend 403. Backend Depends(require_admin) is the real boundary.
  if (pathname.startsWith("/admin") && !isAdmin(session.user?.role)) {
    return NextResponse.redirect(new URL("/dashboard", req.url))
  }

  return NextResponse.next()
})

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/alerts/:path*",
    "/subscriptions/:path*",
    "/admin/:path*",
  ],
}
