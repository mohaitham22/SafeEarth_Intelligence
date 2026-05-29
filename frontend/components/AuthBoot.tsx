// Client-side bootstrap: wraps the app in NextAuth's SessionProvider AND
// registers the apiClient token getter so every authenticated Axios request
// pulls the current access token from the session. Mounted once in the root
// layout. Never reads the token directly — only via getSession().

"use client"

import { SessionProvider, getSession } from "next-auth/react"
import { useEffect } from "react"
import { setClientTokenGetter } from "@/lib/api"

function TokenBridge() {
  useEffect(() => {
    setClientTokenGetter(async () => {
      const session = await getSession()
      return session?.accessToken ?? null
    })
  }, [])
  return null
}

export function AuthBoot({ children }: { children: React.ReactNode }) {
  return (
    <SessionProvider>
      <TokenBridge />
      {children}
    </SessionProvider>
  )
}
