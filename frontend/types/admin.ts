// Types mirroring backend admin responses.
import type { UserRole } from "./common"
export type { UserRole }

export interface AdminUser {
  id: string
  email: string
  full_name: string | null
  role: UserRole
  is_verified: boolean
  premium_expires_at: string | null
  created_at: string
}

export interface AdminUsersResponse {
  items: AdminUser[]
  total: number
  page: number
  page_size: number
}

export interface DataStatus {
  status: "ok"
  models_loaded: boolean
  rag_loaded: boolean
  disaster_types: string[]
  countries_with_data: number
  regions_with_data: number
  files_present: Record<string, boolean>
}

export interface DispatchResult {
  queued: number
  message: string
}

export interface PatchUserRequest {
  role?: UserRole
  is_verified?: boolean
}
