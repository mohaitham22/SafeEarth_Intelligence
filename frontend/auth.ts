// NextAuth v5 configuration.
//
// Strategy: JWT in HttpOnly cookie. The backend's access_token + refresh_token
// live inside that NextAuth JWT, never in localStorage.
//
// Token refresh: the backend access token lasts 30 min (ACCESS_TOKEN_EXPIRE_
// MINUTES). The JWT callback proactively refreshes 60s before expiry by calling
// POST /auth/refresh with the stored refresh_token. On refresh failure we mark
// token.error = "RefreshAccessTokenError" and surface it on the session so the
// app can force a re-login.
//
// Error surfacing: backend distinguishes wrong-credentials (401) from
// unverified-email (400). We throw CredentialsSignin subclasses whose `code`
// is exposed to the client via `result.code` after signIn().
//
// `lib/api.ts` carve-out: this file is the ONLY place that calls fetch()
// outside lib/. Rationale: (1) authorize() runs before any session exists,
// so apiClient's interceptor has no token to attach; (2) the JWT callback
// runs in the Edge runtime when invoked via middleware, where axios's CJS
// deps don't bundle reliably. fetch() is Edge-safe and matches NextAuth v5
// guidance. Do not migrate these calls to lib/endpoints without first
// confirming Edge compatibility end-to-end.

import NextAuth, { CredentialsSignin } from "next-auth"
import Credentials from "next-auth/providers/credentials"
import type { AuthTokens } from "./types/auth"
import type { UserRole } from "./types/common"

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1"
// Refresh the access token 60s before it actually expires.
const REFRESH_SKEW_MS = 60_000
// Matches backend ACCESS_TOKEN_EXPIRE_MINUTES default (30).
const ACCESS_TOKEN_LIFETIME_MS = 30 * 60 * 1000

class UnverifiedEmailError extends CredentialsSignin {
  code = "unverified_email"
}
class InvalidCredentialsError extends CredentialsSignin {
  code = "invalid_credentials"
}
class AuthNetworkError extends CredentialsSignin {
  code = "network_error"
}

interface DecodedAccessToken {
  sub: string
  type: "access"
  exp: number
}

function decodeJwtPayload(token: string): DecodedAccessToken | null {
  try {
    const [, payload] = token.split(".")
    const json = Buffer.from(payload, "base64").toString("utf-8")
    return JSON.parse(json) as DecodedAccessToken
  } catch {
    return null
  }
}

async function refreshAccessToken(refreshToken: string): Promise<string | null> {
  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    if (!res.ok) return null
    const data = (await res.json()) as AuthTokens
    return data.access_token
  } catch {
    return null
  }
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  trustHost: true,
  session: { strategy: "jwt", maxAge: 60 * 60 * 24 * 7 }, // 7 days
  pages:   { signIn: "/login" },

  providers: [
    Credentials({
      // We do not show NextAuth's built-in form; the login page calls signIn()
      // manually, so the `credentials` block is purely informational here.
      credentials: {
        email:    { label: "Email",    type: "email" },
        password: { label: "Password", type: "password" },
      },

      authorize: async (credentials) => {
        const email    = String(credentials?.email ?? "")
        const password = String(credentials?.password ?? "")

        let res: Response
        try {
          res = await fetch(`${API_BASE}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
          })
        } catch {
          throw new AuthNetworkError()
        }

        if (res.status === 401) {
          throw new InvalidCredentialsError()
        }
        if (res.status === 400) {
          // Backend uses 400 specifically for "Email not verified".
          throw new UnverifiedEmailError()
        }
        if (!res.ok) {
          throw new InvalidCredentialsError()
        }

        const tokens = (await res.json()) as AuthTokens
        const decoded = decodeJwtPayload(tokens.access_token)

        // Role is not in the JWT (backend stores it only in DB). Default to
        // "subscriber" — anyone who passes verified-login is at least that.
        // TODO(phase-5b): add GET /auth/me and replace this default.
        const role: UserRole = "subscriber"

        return {
          id:           decoded?.sub ?? "",
          email,
          name:         null,
          accessToken:  tokens.access_token,
          refreshToken: tokens.refresh_token,
          role,
        }
      },
    }),
  ],

  callbacks: {
    async jwt({ token, user }) {
      // First sign-in: copy backend tokens into the JWT.
      if (user) {
        token.accessToken          = user.accessToken
        token.refreshToken         = user.refreshToken
        token.accessTokenExpiresAt = Date.now() + ACCESS_TOKEN_LIFETIME_MS
        token.role                 = user.role
        token.sub                  = user.id
        token.email                = user.email ?? undefined
        return token
      }

      // Subsequent calls: refresh if the access token is near expiry.
      const expiresAt = token.accessTokenExpiresAt ?? 0
      if (expiresAt - REFRESH_SKEW_MS > Date.now()) {
        return token
      }
      if (!token.refreshToken) {
        token.error = "RefreshAccessTokenError"
        return token
      }

      const fresh = await refreshAccessToken(token.refreshToken)
      if (!fresh) {
        token.error = "RefreshAccessTokenError"
        return token
      }
      token.accessToken          = fresh
      token.accessTokenExpiresAt = Date.now() + ACCESS_TOKEN_LIFETIME_MS
      delete token.error
      return token
    },

    async session({ session, token }) {
      session.accessToken = token.accessToken
      session.error       = token.error
      session.user = {
        ...session.user,
        id:    token.sub ?? "",
        email: token.email ?? session.user?.email ?? null,
        role:  token.role ?? "subscriber",
      }
      return session
    },
  },
})
