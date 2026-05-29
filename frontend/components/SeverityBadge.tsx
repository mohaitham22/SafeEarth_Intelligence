// Severity badge — exact colour map from add-frontend-page.md.
// Reused by the dashboard prediction card, the 30-day forecast page, and the
// alerts/history lists. Never inline these colours anywhere else.

import { S } from "@/lib/strings"
import type { SeverityLevel } from "@/types"

const SEVERITY_CLASSES: Record<SeverityLevel, string> = {
  Low:      "bg-green-100  text-green-800  border-green-200",
  Medium:   "bg-yellow-100 text-yellow-800 border-yellow-200",
  High:     "bg-orange-100 text-orange-800 border-orange-200",
  Critical: "bg-red-100    text-red-800    border-red-200",
}

export function SeverityBadge({ level }: { level: SeverityLevel }) {
  const cls = SEVERITY_CLASSES[level] ?? SEVERITY_CLASSES.Low
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${cls}`}
    >
      {S(`severity.${level}`)}
    </span>
  )
}
