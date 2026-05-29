// Recommendations panel — renders the 5 RAG categories with a fixed colour
// map. Used by the dashboard prediction card, the 30-day forecast page, and
// the standalone /recommendations page once built. Sorting comes from the
// backend (evacuation → kit → shelter → medical → contact); we don't re-sort.

import { S } from "@/lib/strings"
import type { RecommendationCategory, RecommendationItem } from "@/types"

const CATEGORY_STYLES: Record<RecommendationCategory, { ring: string; chip: string; dot: string }> = {
  evacuation: { ring: "border-red-200    bg-red-50",    chip: "bg-red-100    text-red-800",    dot: "bg-red-500" },
  kit:        { ring: "border-orange-200 bg-orange-50", chip: "bg-orange-100 text-orange-800", dot: "bg-orange-500" },
  shelter:    { ring: "border-amber-200  bg-amber-50",  chip: "bg-amber-100  text-amber-800",  dot: "bg-amber-500" },
  medical:    { ring: "border-blue-200   bg-blue-50",   chip: "bg-blue-100   text-blue-800",   dot: "bg-blue-500" },
  contact:    { ring: "border-slate-200  bg-slate-50",  chip: "bg-slate-100  text-slate-700",  dot: "bg-slate-500" },
}

export function RecommendationsPanel(props: {
  items: RecommendationItem[]
  personalisationNotice?: string | null
}) {
  if (!props.items.length) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-500">
        {S("rec.empty")}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-slate-700">{S("rec.title")}</h3>

      {props.personalisationNotice && (
        <p className="rounded-md bg-blue-50 border border-blue-200 px-3 py-2 text-xs text-blue-800">
          {props.personalisationNotice}
        </p>
      )}

      <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {props.items.map((rec, i) => {
          const style = CATEGORY_STYLES[rec.category] ?? CATEGORY_STYLES.contact
          return (
            <li
              key={i}
              className={`rounded-lg border p-3 ${style.ring}`}
            >
              <div className="flex items-center gap-2">
                <span className={`h-2 w-2 rounded-full ${style.dot}`} aria-hidden />
                <span
                  className={`text-[10px] font-semibold uppercase tracking-wide rounded-full px-2 py-0.5 ${style.chip}`}
                >
                  {S(`rec.category.${rec.category}`)}
                </span>
              </div>
              <p className="mt-2 text-sm font-medium text-slate-800">{rec.title}</p>
              <p className="mt-1 text-xs text-slate-600 leading-relaxed">{rec.body}</p>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
