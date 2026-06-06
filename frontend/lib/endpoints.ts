// Typed endpoint wrappers — one function per backend route.
// Pages and components MUST go through these — never write raw URLs.
//
// Each wrapper accepts an Axios instance (defaults to `api` for server-side
// calls). Pass `apiClient` from a Client Component if the endpoint requires
// the user's JWT (predictions, history, etc.).

import { api, apiClient } from "./api"
import type { AxiosInstance } from "axios"

import type {
  Ad,
  AdAdminItem,
  AdCreate,
  AdUpdate,
  AdminUser,
  AdminUsersResponse,
  DataStatus,
  DispatchPreviewResponse,
  DispatchResult,
  ModelStats,
  MonthlyDispatchRequest,
  MonthlyDispatchResponse,
  PatchUserRequest,
  SiteStats,
  AlertHistoryResponse,
  EmailForecastResponse,
  AuthTokens,
  CheckoutRequest,
  CheckoutResponse,
  ClassifyRequest,
  ClassifyResult,
  CountriesResponse,
  ForecastDay,
  ForecastRequest,
  ImpactRequest,
  ImpactResult,
  PredictRequest,
  PredictionHistoryResponse,
  PredictionResult,
  RecommendationQuery,
  RecommendationResponse,
  RiskMapPoint,
  SubscriptionCreate,
  SubscriptionListItem,
  SubscriptionLookup,
  SubscriptionResponse,
  TokenRefreshRequest,
  TrendsData,
  ContinentStats,
  InsuranceRatios,
  SeasonalPeaks,
  SecondaryDisasters,
  TimeSeriesData,
  RegionStats,
  User,
  UserLoginRequest,
  UserRegisterRequest,
  VerifyEmailRequest,
  WebhookResponse,
} from "@/types"

type AxiosClient = AxiosInstance

// ---------------------------------------------------------------------------
// /auth
// ---------------------------------------------------------------------------
export const auth = {
  register: (body: UserRegisterRequest, client: AxiosClient = api) =>
    client.post<User>("/auth/register", body).then((r) => r.data),

  login: (body: UserLoginRequest, client: AxiosClient = api) =>
    client.post<AuthTokens>("/auth/login", body).then((r) => r.data),

  refresh: (body: TokenRefreshRequest, client: AxiosClient = api) =>
    client.post<AuthTokens>("/auth/refresh", body).then((r) => r.data),

  verifyEmail: (body: VerifyEmailRequest, client: AxiosClient = api) =>
    client.post<{ ok: true }>("/auth/verify-email", body).then((r) => r.data),

  logout: (client: AxiosClient = apiClient) =>
    client.post<void>("/auth/logout").then((r) => r.data),
}

// ---------------------------------------------------------------------------
// /predictions  (all Subscriber+ — must use apiClient with token attached)
// ---------------------------------------------------------------------------
export const predictions = {
  predict: (body: PredictRequest, client: AxiosClient = apiClient) =>
    client.post<PredictionResult>("/predictions/predict", body).then((r) => r.data),

  forecast30d: (body: ForecastRequest, client: AxiosClient = apiClient) =>
    client.post<ForecastDay[]>("/predictions/forecast-30d", body).then((r) => r.data),

  classify: (body: ClassifyRequest, client: AxiosClient = apiClient) =>
    client.post<ClassifyResult>("/predictions/classify", body).then((r) => r.data),

  impact: (body: ImpactRequest, client: AxiosClient = apiClient) =>
    client.post<ImpactResult>("/predictions/impact", body).then((r) => r.data),

  history: (
    params: { page?: number; page_size?: number } = {},
    client: AxiosClient = apiClient,
  ) =>
    client
      .get<PredictionHistoryResponse>("/predictions/history", { params })
      .then((r) => r.data),

  byId: (id: string, client: AxiosClient = apiClient) =>
    client.get<PredictionResult>(`/predictions/${id}`).then((r) => r.data),

  // Premium-only: download the most recent 30-day forecast batch as a PDF blob.
  forecastPdf: (client: AxiosClient = apiClient) =>
    client
      .get<Blob>("/predictions/forecast-30d/pdf", { responseType: "blob" })
      .then((r) => r.data),
}

// ---------------------------------------------------------------------------
// /regions  (all public)
// ---------------------------------------------------------------------------
export const regions = {
  trends: (client: AxiosClient = api) =>
    client.get<TrendsData>("/regions/trends").then((r) => r.data),

  continentStats: (client: AxiosClient = api) =>
    client.get<ContinentStats>("/regions/continent-stats").then((r) => r.data),

  insuranceGap: (client: AxiosClient = api) =>
    client.get<InsuranceRatios>("/regions/insurance-gap").then((r) => r.data),

  seasonalPeaks: (client: AxiosClient = api) =>
    client.get<SeasonalPeaks>("/regions/seasonal-peaks").then((r) => r.data),

  secondaryDisasters: (client: AxiosClient = api) =>
    client.get<SecondaryDisasters>("/regions/secondary-disasters").then((r) => r.data),

  timeseries: (client: AxiosClient = api) =>
    client.get<TimeSeriesData>("/regions/timeseries").then((r) => r.data),

  stats: (
    params: { disaster_type: string; country?: string },
    client: AxiosClient = api,
  ) =>
    client
      .get<RegionStats>("/regions/stats", { params })
      .then((r) => r.data),

  riskMap: (client: AxiosClient = api) =>
    client.get<RiskMapPoint[]>("/regions/risk-map").then((r) => r.data),

  countries: (client: AxiosClient = api) =>
    client.get<CountriesResponse>("/regions/countries").then((r) => r.data),
}

// ---------------------------------------------------------------------------
// /recommendations  (public — personalisation kicks in only when a token is sent)
// ---------------------------------------------------------------------------
export const recommendations = {
  list: (params: RecommendationQuery, client: AxiosClient = api) =>
    client
      .get<RecommendationResponse>("/recommendations", { params })
      .then((r) => r.data),
}

// ---------------------------------------------------------------------------
// /subscriptions  (most endpoints require auth; DELETE is public/token-based)
// ---------------------------------------------------------------------------
export const subscriptions = {
  list: (client: AxiosClient = apiClient) =>
    client.get<SubscriptionListItem[]>("/subscriptions").then((r) => r.data),

  create: (body: SubscriptionCreate, client: AxiosClient = apiClient) =>
    client.post<SubscriptionResponse>("/subscriptions", body).then((r) => r.data),

  // Public read-only lookup by token — names the region before confirming unsubscribe.
  lookup: (token: string, client: AxiosClient = api) =>
    client.get<SubscriptionLookup>(`/subscriptions/lookup/${token}`).then((r) => r.data),

  // Works for both dashboard (authenticated) and one-click email links (no auth).
  unsubscribe: (token: string, client: AxiosClient = apiClient) =>
    client
      .delete<{ status: string; region_name: string }>(`/subscriptions/${token}`)
      .then((r) => r.data),
}

// ---------------------------------------------------------------------------
// /alerts  (Subscriber+)
// ---------------------------------------------------------------------------
export const alerts = {
  history: (
    params: { page?: number; page_size?: number } = {},
    client: AxiosClient = apiClient,
  ) =>
    client
      .get<AlertHistoryResponse>("/alerts/history", { params })
      .then((r) => r.data),

  // Premium-only: email the user their most recent forecast's highest-risk day.
  emailForecast: (client: AxiosClient = apiClient) =>
    client
      .post<EmailForecastResponse>("/alerts/email-forecast")
      .then((r) => r.data),

  // Monthly digest — Admin or X-Dispatch-Secret. Defaults to previous month.
  monthlyDispatch: (
    body: MonthlyDispatchRequest,
    client: AxiosClient = apiClient,
  ) =>
    client
      .post<MonthlyDispatchResponse>("/alerts/monthly-dispatch", body)
      .then((r) => r.data),
}

// ---------------------------------------------------------------------------
// /premium  (checkout: Subscriber+; webhook: public)
// ---------------------------------------------------------------------------
export const premium = {
  checkout: (body: CheckoutRequest, client: AxiosClient = apiClient) =>
    client.post<CheckoutResponse>("/premium/checkout", body).then((r) => r.data),

  // Called by the mock-checkout page to simulate webhook confirmation.
  // X-Mock-Signature is required by MockPaymentService.verify_webhook_signature.
  confirmMockWebhook: (sessionId: string, client: AxiosClient = apiClient) =>
    client
      .post<WebhookResponse>(
        "/premium/webhook",
        { type: "payment.success", session_id: sessionId },
        { headers: { "X-Mock-Signature": "mock-valid" } },
      )
      .then((r) => r.data),
}

// ---------------------------------------------------------------------------
// /admin  (Admin role only — apiClient attaches JWT automatically)
// ---------------------------------------------------------------------------
export const admin = {
  users: (
    params: { page?: number; page_size?: number } = {},
    client: AxiosClient = apiClient,
  ) =>
    client
      .get<AdminUsersResponse>("/admin/users", { params })
      .then((r) => r.data),

  patchUser: (
    id: string,
    body: PatchUserRequest,
    client: AxiosClient = apiClient,
  ) =>
    client
      .patch<AdminUser>(`/admin/users/${id}`, body)
      .then((r) => r.data),

  dataStatus: (client: AxiosClient = apiClient) =>
    client.get<DataStatus>("/admin/data-status").then((r) => r.data),

  manualDispatch: (client: AxiosClient = apiClient) =>
    client
      .post<DispatchResult>("/alerts/dispatch", { alert_type: "weekly_digest" })
      .then((r) => r.data),

  stats: (client: AxiosClient = apiClient) =>
    client.get<SiteStats>("/admin/stats").then((r) => r.data),

  modelStats: (client: AxiosClient = apiClient) =>
    client.get<ModelStats>("/admin/model-stats").then((r) => r.data),

  dispatchPreview: (client: AxiosClient = apiClient) =>
    client.get<DispatchPreviewResponse>("/admin/alerts/dispatch-preview").then((r) => r.data),

  allAds: (client: AxiosClient = apiClient) =>
    client.get<AdAdminItem[]>("/admin/ads").then((r) => r.data),

  createAd: (body: AdCreate, client: AxiosClient = apiClient) =>
    client.post<AdAdminItem>("/admin/ads", body).then((r) => r.data),

  updateAd: (id: string, body: AdUpdate, client: AxiosClient = apiClient) =>
    client.patch<AdAdminItem>(`/admin/ads/${id}`, body).then((r) => r.data),

  deleteAd: (id: string, client: AxiosClient = apiClient) =>
    client.delete<{ deleted: boolean }>(`/admin/ads/${id}`).then((r) => r.data),
}

// ---------------------------------------------------------------------------
// /ads  (public — home-page promotional content for guests)
// ---------------------------------------------------------------------------
export const ads = {
  list: (client: AxiosClient = api) =>
    client.get<Ad[]>("/ads").then((r) => r.data),
}

// ---------------------------------------------------------------------------
// /health  (public, used by status indicators)
// ---------------------------------------------------------------------------
export interface HealthResponse {
  status: "ok"
  timestamp: string
  models_loaded: boolean
  rag_loaded: boolean
}
export const health = {
  check: (client: AxiosClient = api) =>
    client.get<HealthResponse>("/health").then((r) => r.data),
}

// ---------------------------------------------------------------------------
// Single entry point — `import { endpoints } from "@/lib/endpoints"`
// ---------------------------------------------------------------------------
export const endpoints = {
  auth,
  predictions,
  regions,
  recommendations,
  subscriptions,
  alerts,
  premium,
  health,
  admin,
  ads,
}
