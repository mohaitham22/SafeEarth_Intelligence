# SKILL: Add a New Frontend Page

Read this file completely before creating any Next.js page, component, or layout.
This is the binding pattern for every UI file in SafeEarth Intelligence.

---

## The Decision Tree — Before Writing Any Code

```
Q1: Does this page require a logged-in user?
── YES → add it under app/(protected)/ and add to middleware
── NO  → add it under app/(public)/

Q2: Does this page fetch data?
── YES → is the data user-specific or frequently changing?
│   ── YES → Client Component (use useState + useEffect + Axios)
│   ── NO  → Server Component (fetch directly, no useState)
── NO  → Server Component (pure UI, no data fetching)

Q3: Does this page have any interactivity (clicks, forms, dropdowns)?
── YES → must be Client Component ("use client" at top)
── NO  → keep as Server Component

Q4: Role requirement?
── GUEST OK         → no auth check needed
── ANY LOGGED IN    → middleware guard in frontend
── PREMIUM ONLY     → Depends(require_premium) in API, role check in page
── ADMIN ONLY       → Depends(require_admin) in API, role check in page
```

---

## Folder Structure

```
frontend/app/
├── (public)/                 ← No auth required
│   ├── page.tsx              ← Home / public dashboard
│   ├── map/page.tsx          ← Risk heatmap
│   ├── analytics/page.tsx    ← Global analytics
│   └── pricing/page.tsx      ← Premium pricing page
├── (auth)/                   ← Login/register
│   ├── login/page.tsx
│   └── register/page.tsx
└── (protected)/              ← Requires login — middleware redirects guests
    ├── dashboard/page.tsx
    ├── dashboard/forecast/page.tsx
    └── admin/page.tsx
```

---

## Step 1 — Server Component Template

Use for: analytics pages, pricing page, public map, any read-only display.

```tsx
// frontend/app/(public)/analytics/page.tsx
// NO "use client" — this is a Server Component

import { api } from "@/lib/api"
import { TrendChart } from "@/components/analytics/TrendChart"

async function getAnalyticsData() {
  const [trends, continentStats] = await Promise.all([
    api.get("/regions/trends"),
    api.get("/regions/continent-stats"),
  ])
  return { trends: trends.data, continentStats: continentStats.data }
}

export default async function AnalyticsPage() {
  const data = await getAnalyticsData()

  return (
    <main className="max-w-6xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-slate-800 mb-2">Global Disaster Analytics</h1>
      <p className="text-slate-500 mb-8">
        Historical trends from 16,126 disaster events (1900–2021)
      </p>
      <section className="mb-12">
        <h2 className="text-lg font-semibold mb-4">Disaster Frequency by Decade</h2>
        <TrendChart data={data.trends} />
      </section>
    </main>
  )
}

export const revalidate = 86400  // revalidate every 24 hours
```

---

## Step 2 — Client Component Template

Use for: prediction form, dashboard tabs, subscriptions management, any form or interactive UI.

```tsx
// frontend/app/(protected)/dashboard/page.tsx
"use client"  // REQUIRED at very top — no blank lines before it

import { useState } from "react"
import { useSession } from "next-auth/react"
import { apiClient } from "@/lib/api"
import { LoadingSpinner } from "@/components/ui/LoadingSpinner"
import type { PredictionResult } from "@/types/prediction"

export default function DashboardPage() {
  const { data: session } = useSession()
  const [result, setResult]   = useState<PredictionResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)

  async function handlePredict(lat: number, lon: number) {
    setLoading(true)
    setError(null)
    try {
      const res = await apiClient.post("/predictions/predict", { latitude: lat, longitude: lon })
      setResult(res.data)
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "Prediction failed. Please try again.")
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <LoadingSpinner label="Running prediction..." />

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}
      {/* form and result UI */}
    </div>
  )
}
```

---

## Step 3 — Role-Restricted Page Pattern

```tsx
// frontend/app/(protected)/admin/page.tsx
"use client"

import { useSession } from "next-auth/react"
import { useRouter } from "next/navigation"
import { useEffect } from "react"
import { LoadingSpinner } from "@/components/ui/LoadingSpinner"

export default function AdminPage() {
  const { data: session, status } = useSession()
  const router = useRouter()

  useEffect(() => {
    if (status === "loading") return
    if (!session) { router.replace("/login"); return }
    if (session.user.role !== "admin") { router.replace("/dashboard"); return }
  }, [session, status, router])

  if (status === "loading" || !session || session.user.role !== "admin") {
    return <LoadingSpinner />
  }

  return <div>{/* Admin content */}</div>
}
```

---

## Step 4 — Middleware (add new protected routes here)

```typescript
// frontend/middleware.ts
import { withAuth } from "next-auth/middleware"

export default withAuth({
  callbacks: {
    authorized: ({ token }) => !!token,
  },
})

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/alerts/:path*",
    "/subscriptions/:path*",
    "/admin/:path*",
    // Add new protected routes here
  ],
}
```

---

## Step 5 — API Calls (always use lib/api.ts)

Never use fetch() directly. Never create an Axios instance inside a component.

```typescript
// frontend/lib/api.ts
import axios from "axios"
import { getSession } from "next-auth/react"

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL

// Server-side instance (Server Components — no auth headers)
export const api = axios.create({ baseURL: BASE_URL })

// Client-side instance (Client Components — adds JWT auth header automatically)
export const apiClient = axios.create({ baseURL: BASE_URL })

apiClient.interceptors.request.use(async (config) => {
  const session = await getSession()
  if (session?.accessToken) {
    config.headers.Authorization = `Bearer ${session.accessToken}`
  }
  return config
})
```

---

## Step 6 — TypeScript Types

Every API response must have a TypeScript type defined in `frontend/types/`.

```typescript
// frontend/types/prediction.ts
export interface SHAPFeature {
  feature: string
  contribution_pct: number
}

export interface PredictionResult {
  id: string
  disaster_type: string
  probability_score: number
  severity_level: "Low" | "Medium" | "High" | "Critical"
  risk_score: number
  estimated_deaths: number
  estimated_injuries: number
  estimated_affected: number
  estimated_damage_usd: number
  uninsured_loss_usd: number
  shap_explanation: SHAPFeature[]
  secondary_disaster_warning: string | null
  seasonal_peak_months: number[]
  data_quality: "full" | "limited"
  data_source: "country" | "region" | "global"
  recommendations: Recommendation[]
}
```

---

## Loading, Error, and Empty State Rules

Every async operation must show a loading state. Every API call must handle errors.

```tsx
if (loading) return <LoadingSpinner label="Loading predictions..." />

if (error) return (
  <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700">
    <p className="font-medium">Something went wrong</p>
    <p className="text-sm mt-1">{error}</p>
  </div>
)

if (data.length === 0) return (
  <div className="text-center py-12 text-slate-400">
    <p>No predictions yet.</p>
    <a href="/" className="mt-2 text-blue-500 underline text-sm">Make your first prediction</a>
  </div>
)
```

---

## Tailwind Rules

Only use Tailwind core utility classes — no inline styles, no CSS modules.

Severity level colour mapping — always use this exact mapping:
```tsx
const SEVERITY_COLORS = {
  Low:      "bg-green-100  text-green-800  border-green-200",
  Medium:   "bg-yellow-100 text-yellow-800 border-yellow-200",
  High:     "bg-orange-100 text-orange-800 border-orange-200",
  Critical: "bg-red-100    text-red-800    border-red-200",
}
```

---

## Checklist Before Committing a New Page

- [ ] Decision tree answered — correct folder (public/auth/protected)
- [ ] "use client" present if page has useState, useEffect, or event handlers
- [ ] "use client" absent if page is a pure server component
- [ ] API calls use `api` (server) or `apiClient` (client) from lib/api.ts — never fetch()
- [ ] TypeScript type defined in frontend/types/ for every API response
- [ ] Loading state shown during every async operation
- [ ] Error state handled for every API call
- [ ] Empty state shown when data array is empty
- [ ] Role check in useEffect if page is role-restricted
- [ ] Route added to middleware.ts matcher if page requires login
- [ ] No inline styles — Tailwind classes only
- [ ] No hardcoded API URLs — always NEXT_PUBLIC_API_BASE_URL via apiClient
