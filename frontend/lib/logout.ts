// Combined logout — call backend /auth/logout first (so a future Phase 6
// refresh-token blacklist actually sees the request with the Bearer token
// attached), THEN clear the NextAuth session cookie and redirect.
//
// Backend currently 204s without doing anything; failure is non-fatal — we
// still proceed to clear the local session so the user can't get stuck.

import { signOut } from "next-auth/react"
import { endpoints } from "@/lib/endpoints"

export async function logoutAndRedirect(callbackUrl = "/"): Promise<void> {
  try {
    await endpoints.auth.logout()
  } catch {
    // ignored — local cookie clear must still happen
  }
  // Use redirect:false then hard-navigate so Next.js router cache doesn't
  // keep the stale session alive after the cookie is cleared.
  await signOut({ redirect: false })
  window.location.href = callbackUrl
}
