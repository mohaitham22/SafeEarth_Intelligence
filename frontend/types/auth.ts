// Mirrors backend/schemas/auth.py exactly.
import type { UserRole } from "./common"

export interface UserRegisterRequest {
  email: string
  password: string
  full_name?: string | null
}

export interface UserLoginRequest {
  email: string
  password: string
}

export interface User {
  id: string                // UUID
  email: string
  full_name: string | null
  role: UserRole
  is_verified: boolean
  created_at: string        // ISO datetime
}

export interface AuthTokens {
  access_token: string
  refresh_token: string
  token_type: string        // always "bearer"
}

export interface TokenRefreshRequest {
  refresh_token: string
}

export interface VerifyEmailRequest {
  token: string
}
