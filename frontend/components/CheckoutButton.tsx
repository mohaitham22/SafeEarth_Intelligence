"use client"

import { useState } from "react"
import { useSession } from "next-auth/react"
import { useRouter } from "next/navigation"
import { endpoints } from "@/lib/endpoints"
import { apiClient } from "@/lib/api"
import { S } from "@/lib/strings"
import { meetsRole } from "@/lib/permissions"

interface Props {
  planName:  "monthly" | "yearly"
  label:     string
  highlight?: boolean
}

export function CheckoutButton({ planName, label, highlight }: Props) {
  const { data: session } = useSession()
  const router = useRouter()
  const [busy, setBusy]   = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Already Premium (or admin) — show a static badge instead of a CTA.
  if (meetsRole(session?.user?.role, "premium")) {
    return (
      <div className="mt-8 w-full rounded-md border border-emerald-300 bg-emerald-50 px-4 py-2.5 text-center text-sm font-medium text-emerald-700">
        {S("pricing.currentPlan")}
      </div>
    )
  }

  async function handleClick() {
    setError(null)

    if (!session) {
      router.push("/login?from=/pricing")
      return
    }

    setBusy(true)
    try {
      const data = await endpoints.premium.checkout({ plan_name: planName }, apiClient)
      window.location.href = data.checkout_url
    } catch {
      setError(S("pricing.checkout.error"))
      setBusy(false)
    }
  }

  return (
    <div>
      <button
        type="button"
        onClick={handleClick}
        disabled={busy}
        className={`mt-8 w-full rounded-md px-4 py-2.5 text-sm font-medium transition-opacity ${
          busy ? "cursor-wait opacity-60" : "cursor-pointer"
        } ${
          highlight
            ? "bg-slate-800 text-white hover:bg-slate-700"
            : "border border-slate-300 text-slate-700 hover:bg-slate-50"
        }`}
      >
        {busy ? S("pricing.checkout.busy") : label}
      </button>
      {error && (
        <p className="mt-2 text-xs text-red-600 text-center">{error}</p>
      )}
    </div>
  )
}
