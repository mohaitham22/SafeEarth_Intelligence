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
  await signOut({ callbackUrl })
}
