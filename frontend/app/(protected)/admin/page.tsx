"use client"

import { useEffect, useState } from "react"
import { useSession } from "next-auth/react"
import { useRouter } from "next/navigation"
import { Nav } from "@/components/Nav"
import { RoleBadge } from "@/components/RoleBadge"
import { endpoints } from "@/lib/endpoints"
import { S, Sf } from "@/lib/strings"
import { isAdmin } from "@/lib/permissions"
import type {
  AdminUser,
  AdAdminItem,
  AdCreate,
  AdUpdate,
  DispatchPreviewResponse,
  DispatchResult,
  ModelStats,
  MonthlyDispatchResponse,
  PatchUserRequest,
  SiteStats,
  UserRole,
} from "@/types"

// ── Shared helpers ─────────────────────────────────────────────────────────────

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-slate-800">{value}</p>
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

// ── Overview Tab ──────────────────────────────────────────────────────────────

function OverviewTab() {
  const [stats, setStats]     = useState<SiteStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState("")

  useEffect(() => {
    endpoints.admin.stats()
      .then(setStats)
      .catch(() => setError(S("admin.overview.error")))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-sm text-slate-500">{S("admin.overview.loading")}</p>
  if (error)   return <p className="text-sm text-red-600">{error}</p>
  if (!stats)  return null

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-slate-700">{S("admin.overview.title")}</h2>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard label={S("admin.overview.users")}         value={stats.users.total} />
        <StatCard label={S("admin.overview.verified")}      value={stats.users.verified} />
        <StatCard label={S("admin.overview.premium")}       value={stats.users.by_role.premium} />
        <StatCard label={S("admin.overview.activeSubs")}    value={stats.subscriptions.active} />
        <StatCard label={S("admin.overview.revenue")}       value={`$${stats.payments.revenue_usd}`} />
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard label={S("admin.overview.predictions")}   value={stats.predictions.total} />
        <StatCard label={S("admin.overview.predictions7d")} value={stats.predictions.last_7_days} />
        <StatCard label={S("admin.overview.alertsSent")}    value={stats.alerts.total_sent} />
        <StatCard label={S("admin.overview.alerts7d")}      value={stats.alerts.last_7_days} />
        <StatCard label={S("admin.overview.emailLogs")}     value={stats.email_logs.total} />
      </div>
      <p className="text-sm text-slate-500">
        Role breakdown — Subscriber: {stats.users.by_role.subscriber} / Premium:{" "}
        {stats.users.by_role.premium} / Admin: {stats.users.by_role.admin}
      </p>
    </div>
  )
}

// ── Users Tab ─────────────────────────────────────────────────────────────────

function UsersTab() {
  const [items, setItems]         = useState<AdminUser[]>([])
  const [total, setTotal]         = useState(0)
  const [page, setPage]           = useState(1)
  const PAGE_SIZE                 = 20
  const [loading, setLoading]     = useState(true)
  const [notImpl, setNotImpl]     = useState(false)
  const [saveState, setSaveState] = useState<Record<string, string>>({})
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
        const status =
          (err as { status?: number })?.status ??
          (err as { original?: { response?: { status?: number } } })?.original?.response?.status
        if (status === 404 || status === 422) setNotImpl(true)
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
      setItems((prev) => prev.map((u) => (u.id === user.id ? { ...u, role } : u)))
    } catch (err: unknown) {
      const status =
        (err as { status?: number })?.status ??
        (err as { original?: { response?: { status?: number } } })?.original?.response?.status
      if (status === 403) {
        setSaveState((prev) => ({ ...prev, [user.id]: "error" }))
      } else {
        setSaveState((prev) => ({ ...prev, [user.id]: "error" }))
      }
    }
  }

  if (loading) return <p className="text-sm text-slate-500">{S("admin.users.loading")}</p>

  if (notImpl)
    return <p className="text-sm text-amber-600">{S("admin.users.notImpl")}</p>

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
                          <option key={r} value={r}>
                            {r}
                          </option>
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
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
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

// ── Studio Tab ────────────────────────────────────────────────────────────────

function StudioTab() {
  const [ads, setAds]           = useState<AdAdminItem[]>([])
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState("")
  const [creating, setCreating] = useState(false)
  const [newAd, setNewAd]       = useState<AdCreate>({ title: "", is_active: true, sort_order: 0 })
  const [editId, setEditId]     = useState<string | null>(null)
  const [editData, setEditData] = useState<AdUpdate>({})

  function load() {
    setLoading(true)
    endpoints.admin.allAds()
      .then(setAds)
      .catch(() => setError(S("admin.studio.error")))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  async function handleCreate() {
    if (!newAd.title.trim()) return
    setCreating(true)
    try {
      await endpoints.admin.createAd(newAd)
      setNewAd({ title: "", is_active: true, sort_order: 0 })
      load()
    } finally {
      setCreating(false)
    }
  }

  async function handleUpdate(id: string) {
    await endpoints.admin.updateAd(id, editData)
    setEditId(null)
    setEditData({})
    load()
  }

  async function handleDelete(id: string) {
    await endpoints.admin.deleteAd(id)
    load()
  }

  if (loading) return <p className="text-sm text-slate-500">{S("admin.studio.loading")}</p>
  if (error)   return <p className="text-sm text-red-600">{error}</p>

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-slate-700">{S("admin.studio.title")}</h2>

      {/* Create form */}
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-3">
        <p className="text-sm font-medium text-slate-700">{S("admin.studio.createTitle")}</p>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <input
            className="rounded border border-slate-300 px-3 py-1.5 text-sm"
            placeholder={S("admin.studio.label.title")}
            value={newAd.title}
            onChange={(e) => setNewAd((p) => ({ ...p, title: e.target.value }))}
          />
          <input
            className="rounded border border-slate-300 px-3 py-1.5 text-sm"
            placeholder={S("admin.studio.label.linkUrl")}
            value={newAd.link_url ?? ""}
            onChange={(e) => setNewAd((p) => ({ ...p, link_url: e.target.value || null }))}
          />
          <input
            className="rounded border border-slate-300 px-3 py-1.5 text-sm"
            placeholder={S("admin.studio.label.body")}
            value={newAd.body ?? ""}
            onChange={(e) => setNewAd((p) => ({ ...p, body: e.target.value || null }))}
          />
          <input
            className="rounded border border-slate-300 px-3 py-1.5 text-sm"
            placeholder={S("admin.studio.label.ctaLabel")}
            value={newAd.cta_label ?? ""}
            onChange={(e) => setNewAd((p) => ({ ...p, cta_label: e.target.value || null }))}
          />
        </div>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-1.5 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={newAd.is_active ?? true}
              onChange={(e) => setNewAd((p) => ({ ...p, is_active: e.target.checked }))}
            />
            {S("admin.studio.label.active")}
          </label>
          <button
            onClick={handleCreate}
            disabled={creating || !newAd.title.trim()}
            className="rounded bg-blue-600 px-4 py-1.5 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {creating ? S("admin.studio.saving") : S("admin.studio.newAd")}
          </button>
        </div>
      </div>

      {/* Ad list */}
      {ads.length === 0 ? (
        <p className="text-sm text-slate-400">{S("admin.studio.empty")}</p>
      ) : (
        <div className="space-y-3">
          {ads.map((ad) =>
            editId === ad.id ? (
              <div
                key={ad.id}
                className="rounded-lg border border-blue-200 bg-blue-50 p-4 space-y-3"
              >
                <p className="text-sm font-medium text-slate-700">{S("admin.studio.editTitle")}</p>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <input
                    className="rounded border border-slate-300 px-3 py-1.5 text-sm"
                    placeholder={S("admin.studio.label.title")}
                    defaultValue={ad.title}
                    onChange={(e) => setEditData((p) => ({ ...p, title: e.target.value }))}
                  />
                  <input
                    className="rounded border border-slate-300 px-3 py-1.5 text-sm"
                    placeholder={S("admin.studio.label.linkUrl")}
                    defaultValue={ad.link_url ?? ""}
                    onChange={(e) =>
                      setEditData((p) => ({ ...p, link_url: e.target.value || null }))
                    }
                  />
                  <input
                    className="rounded border border-slate-300 px-3 py-1.5 text-sm"
                    placeholder={S("admin.studio.label.ctaLabel")}
                    defaultValue={ad.cta_label ?? ""}
                    onChange={(e) =>
                      setEditData((p) => ({ ...p, cta_label: e.target.value || null }))
                    }
                  />
                  <label className="flex items-center gap-1.5 text-sm text-slate-600">
                    <input
                      type="checkbox"
                      defaultChecked={ad.is_active}
                      onChange={(e) =>
                        setEditData((p) => ({ ...p, is_active: e.target.checked }))
                      }
                    />
                    {S("admin.studio.label.active")}
                  </label>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleUpdate(ad.id)}
                    className="rounded bg-blue-600 px-3 py-1 text-xs text-white hover:bg-blue-700"
                  >
                    {S("admin.studio.save")}
                  </button>
                  <button
                    onClick={() => {
                      setEditId(null)
                      setEditData({})
                    }}
                    className="rounded border border-slate-300 px-3 py-1 text-xs text-slate-600"
                  >
                    {S("admin.studio.cancel")}
                  </button>
                </div>
              </div>
            ) : (
              <div
                key={ad.id}
                className="flex items-start justify-between rounded-lg border border-slate-200 bg-white p-4"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-slate-800">{ad.title}</span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                        ad.is_active
                          ? "bg-emerald-100 text-emerald-700"
                          : "bg-slate-100 text-slate-500"
                      }`}
                    >
                      {ad.is_active ? S("admin.studio.active") : S("admin.studio.inactive")}
                    </span>
                  </div>
                  {ad.body && (
                    <p className="mt-0.5 text-xs text-slate-500 truncate">{ad.body}</p>
                  )}
                  {ad.link_url && (
                    <p className="mt-0.5 text-xs text-blue-500 truncate">{ad.link_url}</p>
                  )}
                </div>
                <div className="ml-4 flex shrink-0 gap-2">
                  <button
                    onClick={() => {
                      setEditId(ad.id)
                      setEditData({})
                    }}
                    className="rounded border border-slate-300 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
                  >
                    Edit
                  </button>
                  {ad.is_active && (
                    <button
                      onClick={() => handleDelete(ad.id)}
                      className="rounded border border-red-200 px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                    >
                      {S("admin.studio.delete")}
                    </button>
                  )}
                </div>
              </div>
            )
          )}
        </div>
      )}
    </div>
  )
}

// ── Model Stats Tab ───────────────────────────────────────────────────────────

function ModelStatsTab() {
  const [stats, setStats]     = useState<ModelStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    endpoints.admin.modelStats()
      .then(setStats)
      .catch(() => {/* endpoint exists; failure shows nothing gracefully */})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-sm text-slate-500">{S("admin.modelStats.loading")}</p>
  if (!stats)  return null

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-slate-700">{S("admin.modelStats.title")}</h2>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <StatCard label={S("admin.modelStats.version")}    value={stats.version} />
        <StatCard label={S("admin.modelStats.macroF1")}    value={stats.macro_f1.toFixed(4)} />
        <StatCard label={S("admin.modelStats.weightedF1")} value={stats.weighted_f1.toFixed(4)} />
        <StatCard label={S("admin.modelStats.features")}   value={stats.feature_count} />
      </div>

      <div>
        <p className="mb-2 text-sm font-medium text-slate-600">Ensemble Weights</p>
        <div className="flex flex-wrap gap-3">
          {Object.entries(stats.ensemble).map(([name, weight]) => (
            <div
              key={name}
              className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-2 text-sm"
            >
              <span className="font-medium">{name}</span>
              <span className="ml-2 text-slate-500">
                {(weight * 100).toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium text-slate-600">
          {S("admin.modelStats.pipeline")}
        </h3>
        <div className="flex flex-wrap gap-3">
          {[
            { label: S("admin.modelStats.models"), ok: stats.models_loaded },
            { label: S("admin.modelStats.rag"),    ok: stats.rag_loaded },
          ].map(({ label, ok }) => (
            <span
              key={label}
              className={`inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-medium ${
                ok ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"
              }`}
            >
              {label}: {ok ? S("admin.modelStats.loaded") : S("admin.modelStats.notLoaded")}
            </span>
          ))}
        </div>
      </div>

      <div>
        <h3 className="mb-2 text-sm font-medium text-slate-600">
          {S("admin.modelStats.perClass")}
        </h3>
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                {[
                  "admin.modelStats.col.type",
                  "admin.modelStats.col.f1",
                  "admin.modelStats.col.support",
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
              {stats.per_class_f1.map(({ type, f1, support }) => (
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
    </div>
  )
}

// ── Alerts Tab ────────────────────────────────────────────────────────────────

function AlertsTab() {
  const [preview, setPreview]       = useState<DispatchPreviewResponse | null>(null)
  const [previewLoading, setPL]     = useState(true)
  const [weeklyState, setWeekly]    = useState<"idle" | "busy" | "done" | "error">("idle")
  const [weeklyMsg, setWeeklyMsg]   = useState("")
  const [monthlyState, setMonthly]  = useState<"idle" | "busy" | "done" | "error">("idle")
  const [monthlyMsg, setMonthlyMsg] = useState("")

  const now   = new Date()
  const prevM = now.getMonth() === 0 ? 12 : now.getMonth()
  const prevY = now.getMonth() === 0 ? now.getFullYear() - 1 : now.getFullYear()
  const [mYear, setMYear]   = useState(prevY)
  const [mMonth, setMMonth] = useState(prevM)

  useEffect(() => {
    endpoints.admin.dispatchPreview()
      .then(setPreview)
      .finally(() => setPL(false))
  }, [])

  async function handleWeekly() {
    setWeekly("busy")
    setWeeklyMsg("")
    try {
      const result: DispatchResult = await endpoints.admin.manualDispatch()
      setWeeklyMsg(Sf("admin.alerts.resultWeekly", { n: result.queued }))
      setWeekly("done")
    } catch {
      setWeeklyMsg(S("admin.alerts.error"))
      setWeekly("error")
    }
  }

  async function handleMonthly() {
    setMonthly("busy")
    setMonthlyMsg("")
    try {
      const result: MonthlyDispatchResponse = await endpoints.alerts.monthlyDispatch({
        year: mYear,
        month: mMonth,
      })
      setMonthlyMsg(
        Sf("admin.alerts.resultQueued", { n: result.dispatched, period: result.period }),
      )
      setMonthly("done")
    } catch {
      setMonthlyMsg(S("admin.alerts.error"))
      setMonthly("error")
    }
  }

  return (
    <div className="space-y-6">
      {/* Preview */}
      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <p className="mb-3 text-sm font-semibold text-slate-700">
          {S("admin.alerts.previewTitle")}
        </p>
        {previewLoading ? (
          <p className="text-sm text-slate-500">{S("admin.alerts.loading")}</p>
        ) : preview ? (
          <div className="flex flex-wrap gap-4">
            <StatCard label={S("admin.alerts.activeSubs")}   value={preview.active_subscriptions} />
            <StatCard label={S("admin.alerts.premiumUsers")} value={preview.premium_users} />
          </div>
        ) : null}
      </div>

      {/* Weekly dispatch */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
        <p className="text-sm font-semibold text-slate-700">{S("admin.alerts.weeklyTitle")}</p>
        <p className="text-xs text-slate-500">{S("admin.alerts.weeklyDesc")}</p>
        <button
          onClick={handleWeekly}
          disabled={weeklyState === "busy"}
          className="rounded-lg bg-blue-600 px-5 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {weeklyState === "busy" ? S("admin.alerts.weeklyBusy") : S("admin.alerts.weeklyCta")}
        </button>
        {weeklyMsg && (
          <p
            className={`text-sm ${
              weeklyState === "error" ? "text-red-600" : "text-emerald-600"
            }`}
          >
            {weeklyMsg}
          </p>
        )}
      </div>

      {/* Monthly digest */}
      <div className="rounded-lg border border-slate-200 bg-white p-4 space-y-3">
        <p className="text-sm font-semibold text-slate-700">{S("admin.alerts.monthlyTitle")}</p>
        <p className="text-xs text-slate-500">{S("admin.alerts.monthlyDesc")}</p>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs text-slate-600">
              {S("admin.alerts.monthlyYear")}
            </label>
            <input
              type="number"
              min={2000}
              max={2100}
              value={mYear}
              onChange={(e) => setMYear(Number(e.target.value))}
              className="w-24 rounded border border-slate-300 px-2 py-1.5 text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-600">
              {S("admin.alerts.monthlyMonth")}
            </label>
            <select
              value={mMonth}
              onChange={(e) => setMMonth(Number(e.target.value))}
              className="rounded border border-slate-300 px-2 py-1.5 text-sm"
            >
              {Array.from({ length: 12 }, (_, i) => (
                <option key={i + 1} value={i + 1}>
                  {new Date(2000, i).toLocaleString("default", { month: "long" })} ({i + 1})
                </option>
              ))}
            </select>
          </div>
          <button
            onClick={handleMonthly}
            disabled={monthlyState === "busy"}
            className="rounded-lg bg-indigo-600 px-5 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {monthlyState === "busy"
              ? S("admin.alerts.monthlyBusy")
              : S("admin.alerts.monthlyCta")}
          </button>
        </div>
        {monthlyMsg && (
          <p
            className={`text-sm ${
              monthlyState === "error" ? "text-red-600" : "text-emerald-600"
            }`}
          >
            {monthlyMsg}
          </p>
        )}
      </div>
    </div>
  )
}

// ── Admin page shell ──────────────────────────────────────────────────────────

type Tab = "overview" | "users" | "studio" | "modelStats" | "alerts" | "payments"

const TABS: { id: Tab; labelKey: string }[] = [
  { id: "overview",   labelKey: "admin.tab.overview"   },
  { id: "users",      labelKey: "admin.tab.users"      },
  { id: "studio",     labelKey: "admin.tab.studio"     },
  { id: "modelStats", labelKey: "admin.tab.modelStats" },
  { id: "alerts",     labelKey: "admin.tab.alerts"     },
  { id: "payments",   labelKey: "admin.tab.payments"   },
]

export default function AdminPage() {
  const { data: session, status } = useSession()
  const router    = useRouter()
  const [tab, setTab] = useState<Tab>("overview")

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login?from=/admin")
      return
    }
    if (status === "authenticated" && !isAdmin(session?.user?.role)) {
      router.replace("/dashboard")
    }
  }, [status, session, router])

  if (status === "loading") {
    return (
      <>
        <Nav />
        <main className="mx-auto max-w-6xl px-4 py-12">
          <div className="h-8 w-48 animate-pulse rounded bg-slate-200" />
        </main>
      </>
    )
  }

  if (!session || session.user?.role !== "admin") return null

  return (
    <>
      <Nav />
      <main className="mx-auto max-w-6xl px-4 py-10">
        <h1 className="text-3xl font-bold text-slate-800">{S("page.admin.title")}</h1>

        {/* Tab bar */}
        <div className="mt-6 flex flex-wrap gap-1 border-b border-slate-200">
          {TABS.map(({ id, labelKey }) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`rounded-t-md px-4 py-2 text-sm font-medium transition-colors ${
                tab === id
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
          {tab === "overview"   && <OverviewTab />}
          {tab === "users"      && <UsersTab />}
          {tab === "studio"     && <StudioTab />}
          {tab === "modelStats" && <ModelStatsTab />}
          {tab === "alerts"     && <AlertsTab />}
          {tab === "payments"   && <ComingSoonPanel />}
        </div>
      </main>
    </>
  )
}
