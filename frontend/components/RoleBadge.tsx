// Small role chip used in the auth-aware Nav. Colour key:
//   guest      → slate
//   subscriber → blue
//   premium    → emerald
//   admin      → amber

import { S } from "@/lib/strings"
import type { UserRole } from "@/types"

const ROLE_CLASSES: Record<UserRole, string> = {
  guest:      "bg-slate-100   text-slate-700   border-slate-200",
  subscriber: "bg-blue-100    text-blue-800    border-blue-200",
  premium:    "bg-emerald-100 text-emerald-800 border-emerald-200",
  admin:      "bg-amber-100   text-amber-800   border-amber-200",
}

export function RoleBadge({ role }: { role: UserRole }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${ROLE_CLASSES[role]}`}
    >
      {S(`nav.role.${role}`)}
    </span>
  )
}
