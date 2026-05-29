// Augments NextAuth v5's Session and JWT with the backend tokens + role.
// Token payload from backend/core/security.py has only {sub, type, exp} —
// the Bearer access_token is what we attach to outbound apiClient calls.

import type { UserRole } from "./common"
import "next-auth"
import "next-auth/jwt"

declare module "next-auth" {
  interface Session {
    accessToken?: string
    error?:       "RefreshAccessTokenError"
    user: {
      id?:    string
      email?: string | null
      name?:  string | null
      role:   UserRole
    }
  }

  interface User {
    id:           string
    email:        string
    name?:        string | null
    accessToken:  string
    refreshToken: string
    role:         UserRole
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    accessToken?:  string
    refreshToken?: string
    accessTokenExpiresAt?: number    // epoch ms
    role?: UserRole
    sub?:  string                    // backend user UUID
    email?: string
    error?: "RefreshAccessTokenError"
  }
}
