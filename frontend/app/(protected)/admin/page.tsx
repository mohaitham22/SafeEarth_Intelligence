"use client"

import { useEffect, useState } from "react"
import { useSession } from "next-auth/react"
import { useRouter } from "next/navigation"
import { Nav } from "@/components/Nav"
import { RoleBadge } from "@/components/RoleBadge"
import { endpoints } from "@/lib/endpoints"
import { S, Sf } from "@/lib/strings"
import type { AdminUser, DataStatus, DispatchResult, PatchUserRequest, UserRole } from "@/types"

// ---------------------------------------------------------------------------
// Constants — v4.2 model metrics (build-time constants from training)
// ---------------------------------------------------------------------------
const MODEL_VERSION  = "v4.2"
const MACRO_F1       = 0.7052
const WEIGHTED_F1    = 0.7587
const FEATURE_COUNT  = 16

const PER_CLASS_F1: { type: string; f1: number; support: number }[] = [
  { type: "Earthquake",          f1: 0.976, support: 1137 },
  { type: "Flood",               f1: 0.778, support: 5272 },
  { type: "Storm",               f1: 0.771, support: 4005 },
  { type: "Extreme temperature", f1: 0.749, support: 584  },
  { type: "Volcanic activity",   f1: 0.668, support: 222  },
  { type: "Wildfire",            f1: 0.628, support: 452  },
  { type: "Drought",             f1: 0.589, support: 685  },
  { type: "Landslide",           f1: 0.482, support: 713  },
]

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------
function NotImplemented({ endpoint }: { endpoint: string }) {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
      <span className="font-medium">Not yet implemented: </span>
      <code className="font-mono">{endpoint}</code>
      {" — this backend endpoint has not been built yet."}
    </div>
  )
}

function ComingSoonPanel() {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-6 py-10 text-center">
      <p className="text-lg font-semibold text-slate-700">{S("admin.comingSoon.title")}</p>
      <p className="mt-1 text-sm text-slate-500">{S("admin.comingSoon.body")}</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Users tab
// ---------------------------------------------------------------------------
function UsersTab() {
  const [items, setItems]   = useState<AdminUser[]>([])
  const [total, setTotal]   = useState(0)
  const [page, setPage]     = useState(1)
  const PAGE_SIZE           = 20
  const [loading, setLoading] = useState(true)
  const [notImpl, setNotImpl] = useState(false)
  // per-row save state: "idle" | "saving" | "saved" | "error" | "notimpl"
  const [saveState, setSaveState] = useState<Record<string, string>>({})
  // per-row pending role edit
  const [pendingRole, setPendingRole] = useState<Record<string, UserRole>>({})

  useEffect(() => {
    setLoading(true)
    endpoints.admin.users({ page, page_size: PAGE_SIZE })
      .then((data) => {
        setItems(data.items)
        setTotal(data.total)
        setNotImpl(false)
      })
      .catch((err) => {
        if (err?.status === 404 || err?.status === 422 || err?.original?.response?.status === 404) {
          setNotImpl(true)
        }
      })
      .finally(() => setLoading(false))
  }, [page])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  function handleRoleChange(userId: string, role: UserRole) {
    setPendingRole((prev) => ({ ...prev, [userId]: role }))
    setSaveState((prev) => ({ ...prev, [userId]: "idle" }))
  }

  async function handleSave(user: AdminUser) {
    const role = pendingRole[user.id] ?? user.role
    setSaveState((prev) => ({ ...prev, [user.id]: "saving" }))
    try {
      await endpoints.admin.patchUser(user.id, { role } as PatchUserRequest)
      setSaveState((prev) => ({ ...prev, [user.id]: "saved" }))
      setItems((prev) => prev.map((u) => u.id === user.id ? { ...u, role } : u))
    } catch (err: unknown) {
      const status = (err as { status?: number })?.status
        ?? (err as { original?: { response?: { status?: number } } })?.original?.response?.status
      if (status === 404 || status === 422) {
        setSaveState((prev) => ({ ...prev, [user.id]: "notimpl" }))
      } else {
        setSaveState((prev) => ({ ...prev, [user.id]: "error" }))
      }
    }
  }

  if (loading) {
    return <p className="text-sm text-slate-500">{S("admin.users.loading")}</p>
  }

  if (notImpl) {
    return <NotImplemented endpoint="GET /admin/users" />
  }

  const roles: UserRole[] = ["guest", "subscriber", "premium", "admin"]

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-slate-700">{S("admin.users.title")}</h2>
      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              {[
                "admin.users.col.email",
                "admin.users.col.role",
                "admin.users.col.verified",
                "admin.users.col.expires",
                "admin.users.col.joined",
                "admin.users.col.actions",
              ].map((k) => (
                <th
                  key={k}
                  className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-500"
                >
                  {S(k)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {items.map((user) => {
              const currentRole = pendingRole[user.id] ?? user.role
              const ss = saveState[user.id] ?? "idle"
              return (
                <tr key={user.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 text-slate-800">{user.email}</td>
                  <td className="px-4 py-3">
                    <RoleBadge role={currentRole} />
                  </td>
                  <td className="px-4 py-3">
                    <span className={user.is_verified ? "text-emerald-600" : "text-slate-400"}>
                      {user.is_verified ? "Yes" : "No"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {user.premium_expires_at
                      ? new Date(user.premium_expires_at).toLocaleDateString()
                      : S("admin.users.never")}
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {new Date(user.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <select
                        value={currentRole}
                        onChange={(e) => handleRoleChange(user.id, e.target.value as UserRole)}
                        className="rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        {roles.map((r) => (
                          <option key={r} value={r}>{r}</option>
                        ))}
                      </select>
                      <button
                        disabled={ss === "saving"}
                        onClick={() => handleSave(user)}
                        className="rounded bg-blue-600 px-2 py-1 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                      >
                        {ss === "saving" ? S("admin.users.saving") : S("admin.users.save")}
                      </button>
                      {ss === "saved" && (
                        <span className="text-xs text-emerald-600">{S("admin.users.saved")}</span>
                      )}
                      {ss === "error" && (
                        <span className="text-xs text-red-600">{S("admin.users.saveError")}</span>
                      )}
                      {ss === "notimpl" && (
                        <span className="text-xs text-amber-600">{S("admin.users.patchNotImpl")}</span>
                      )}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {/* Pagination */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">
          {Sf("admin.users.pageOf", { page, total: totalPages })}
        </p>
        <div className="flex gap-2">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="rounded border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-40"
          >
            {S("admin.users.prev")}
          </button>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            className="rounded border border-slate-300 px-3 py-1 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-40"
          >
            {S("admin.users.next")}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Model Stats tab
// ---------------------------------------------------------------------------
function ModelStatsTab() {
  const [dataStatus, setDataStatus] = useState<DataStatus | null>(null)
  const [loading, setLoading]       = useState(true)

  useEffect(() => {
    endpoints.admin.dataStatus()
      .then(setDataStatus)
      .catch(() => {/* non-fatal — hardcoded metrics still display */})
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-slate-700">{S("admin.modelStats.title")}</h2>

      {/* Top metrics */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[
          { label: S("admin.modelStats.version"),    value: MODEL_VERSION },
          { label: S("admin.modelStats.macroF1"),    value: MACRO_F1.toFixed(4) },
          { label: S("admin.modelStats.weightedF1"), value: WEIGHTED_F1.toFixed(4) },
          { label: S("admin.modelStats.features"),   value: String(FEATURE_COUNT) },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-lg border border-slate-200 bg-white px-4 py-4">
            <p className="text-xs text-slate-500">{label}</p>
            <p className="mt-1 text-xl font-bold text-slate-800">{value}</p>
          </div>
        ))}
      </div>

      {/* Per-class F1 */}
      <div>
        <h3 className="mb-2 text-sm font-medium text-slate-600">{S("admin.modelStats.perClass")}</h3>
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                {["admin.modelStats.col.type", "admin.modelStats.col.f1", "admin.modelStats.col.support"].map((k) => (
                  <th key={k} className="px-4 py-3 text-left text-xs font-medium uppercase tracking-wide text-slate-500">
                    {S(k)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {PER_CLASS_F1.map(({ type, f1, support }) => (
                <tr key={type} className="hover:bg-slate-50">
                  <td className="px-4 py-2 font-medium text-slate-800">{type}</td>
                  <td className="px-4 py-2">
                    <div className="flex items-center gap-2">
                      <div className="h-2 w-24 overflow-hidden rounded-full bg-slate-200">
                        <div
                          className="h-full rounded-full bg-blue-500"
                          style={{ width: `${(f1 * 100).toFixed(0)}%` }}
                        />
                      </div>
                      <span className="text-slate-700">{f1.toFixed(3)}</span>
                    </div>
                  </td>
                  <td className="px-4 py-2 text-slate-500">{support.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pipeline status from /admin/data-status */}
      <div>
        <h3 className="mb-2 text-sm font-medium text-slate-600">{S("admin.modelStats.pipeline")}</h3>
        {loading ? (
          <p className="text-sm text-slate-400">{S("admin.modelStats.loading")}</p>
        ) : dataStatus ? (
          <div className="flex flex-wrap gap-3">
            {[
              { label: S("admin.modelStats.models"), ok: dataStatus.models_loaded },
              { label: S("admin.modelStats.rag"),    ok: dataStatus.rag_loaded },
            ].map(({ label, ok }) => (
              <span
                key={label}
                className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium ${
                  ok
                    ? "bg-emerald-100 text-emerald-700"
                    : "bg-red-100 text-red-700"
                }`}
              >
                {label}: {ok ? S("admin.modelStats.loaded") : S("admin.modelStats.notLoaded")}
              </span>
            ))}
          </div>
        ) : (
          <NotImplemented endpoint="GET /admin/data-status" />
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Manual Dispatch tab
// ---------------------------------------------------------------------------
function DispatchTab() {
  const [result, setResult]   = useState<DispatchResult | null>(null)
  const [error, setError]     = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleDispatch() {
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const data = await endpoints.admin.manualDispatch()
      setResult(data)
    } catch (err: unknown) {
      const msg = (err as { detail?: string })?.detail ?? "Unknown error"
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-xl space-y-4">
      <h2 className="text-lg font-semibold text-slate-700">{S("admin.dispatch.title")}</h2>
      <p className="text-sm text-slate-500">{S("admin.dispatch.description")}</p>
      <button
        disabled={loading}
        onClick={handleDispatch}
        className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        {loading ? S("admin.dispatch.busy") : S("admin.dispatch.cta")}
      </button>
      {result && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          <p className="font-semibold">{Sf("admin.dispatch.queued", { n: result.queued })}</p>
          <p className="mt-1 text-emerald-700">
            {S("admin.dispatch.message")}: {result.message}
          </p>
        </div>
      )}
      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          <p className="font-semibold">{S("admin.dispatch.error")}</p>
          <p className="mt-1 text-red-700">{error}</p>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Admin page shell
// ---------------------------------------------------------------------------
type Tab = "users" | "modelStats" | "payments" | "dispatch" | "emailLogs"

const TABS: { id: Tab; labelKey: string }[] = [
  { id: "users",      labelKey: "admin.tab.users"      },
  { id: "modelStats", labelKey: "admin.tab.modelStats" },
  { id: "payments",   labelKey: "admin.tab.payments"   },
  { id: "dispatch",   labelKey: "admin.tab.dispatch"   },
  { id: "emailLogs",  labelKey: "admin.tab.emailLogs"  },
]

export default function AdminPage() {
  const { data: session, status } = useSession()
  const router = useRouter()
  const [activeTab, setActiveTab] = useState<Tab>("users")

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login?from=/admin")
      return
    }
    if (status === "authenticated" && session?.user?.role !== "admin") {
      router.replace("/dashboard")
    }
  }, [status, session, router])

  if (status === "loading") {
    return (
      <>
        <Nav />
        <main className="max-w-6xl mx-auto px-4 py-12">
          <div className="h-8 w-48 animate-pulse rounded bg-slate-200" />
        </main>
      </>
    )
  }

  if (!session || session.user?.role !== "admin") return null

  return (
    <>
      <Nav />
      <main className="max-w-6xl mx-auto px-4 py-10">
        <h1 className="text-3xl font-bold text-slate-800">{S("page.admin.title")}</h1>

        {/* Tab bar */}
        <div className="mt-6 flex gap-1 border-b border-slate-200">
          {TABS.map(({ id, labelKey }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`rounded-t-md px-4 py-2 text-sm font-medium transition-colors ${
                activeTab === id
                  ? "border-b-2 border-blue-600 text-blue-600"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              {S(labelKey)}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="mt-6">
          {activeTab === "users"      && <UsersTab />}
          {activeTab === "modelStats" && <ModelStatsTab />}
          {activeTab === "payments"   && <ComingSoonPanel />}
          {activeTab === "dispatch"   && <DispatchTab />}
          {activeTab === "emailLogs"  && <ComingSoonPanel />}
        </div>
      </main>
    </>
  )
}
