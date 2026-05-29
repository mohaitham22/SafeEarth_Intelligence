// Central Axios instance — ALL API calls in the app go through this module.
// Per CLAUDE.md: "All API calls through lib/api.ts Axios instance. No fetch()
// calls scattered in components."
//
// Two instances per add-frontend-page.md skill:
//   - `api`        : server-side (no auth headers, used in Server Components)
//   - `apiClient`  : client-side (attaches Bearer token via interceptor)
//
// JWT token sourcing is intentionally abstracted behind `setClientTokenGetter`
// so the NextAuth wiring step (later in Phase 5) has a single place to plug in
// `getSession()`. Until that step runs the interceptor sends no Authorization
// header, which is fine for public endpoints.
//
// Errors: every response error is normalised to `ApiError` so callers see a
// stable shape (`status`, `detail`, `original`) regardless of network/HTTP cause.

import axios, { type AxiosError, type AxiosInstance } from "axios"

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL

if (!BASE_URL) {
  // Surfaced at module init so a missing env var fails fast, not on first call.
  // eslint-disable-next-line no-console
  console.warn("[lib/api] NEXT_PUBLIC_API_BASE_URL is not set")
}

// ---------------------------------------------------------------------------
// Token getter — set once by the auth provider (Prompt 4 will wire NextAuth)
// ---------------------------------------------------------------------------

type TokenGetter = () => Promise<string | null> | string | null

let _getClientToken: TokenGetter = () => null

/** Register the function that resolves the current JWT access token.
 *  Called once by the NextAuth provider component on app boot. */
export function setClientTokenGetter(getter: TokenGetter): void {
  _getClientToken = getter
}

// ---------------------------------------------------------------------------
// Error shape — every rejected request comes back as ApiError
// ---------------------------------------------------------------------------

export interface ApiError {
  status:   number       // HTTP status; 0 = network error
  detail:   string       // FastAPI `detail` field, or a sensible fallback
  original: unknown      // raw AxiosError, for debugging only
}

function normaliseError(err: AxiosError<{ detail?: unknown }>): ApiError {
  const status = err.response?.status ?? 0
  const raw = err.response?.data?.detail
  let detail: string
  if (typeof raw === "string") {
    detail = raw
  } else if (Array.isArray(raw)) {
    // Pydantic 422 returns an array of {loc, msg, type} dicts
    detail = raw
      .map((d: { msg?: string }) => d?.msg ?? "")
      .filter(Boolean)
      .join("; ") || "Validation failed"
  } else if (raw && typeof raw === "object") {
    detail = JSON.stringify(raw)
  } else if (err.message) {
    detail = err.message
  } else {
    detail = "Request failed"
  }
  return { status, detail, original: err }
}

// ---------------------------------------------------------------------------
// Instances
// ---------------------------------------------------------------------------

const commonConfig = {
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
  timeout: 30_000,
}

/** Server-side instance — Server Components only. No auth header. */
export const api: AxiosInstance = axios.create(commonConfig)

/** Client-side instance — Client Components only. Sends Bearer token. */
export const apiClient: AxiosInstance = axios.create(commonConfig)

apiClient.interceptors.request.use(async (config) => {
  const token = await _getClientToken()
  if (token) {
    config.headers = config.headers ?? {}
    ;(config.headers as Record<string, string>).Authorization = `Bearer ${token}`
  }
  return config
})

const errorInterceptor = (err: AxiosError<{ detail?: unknown }>) =>
  Promise.reject(normaliseError(err))

api.interceptors.response.use((r) => r, errorInterceptor)
apiClient.interceptors.response.use((r) => r, errorInterceptor)
