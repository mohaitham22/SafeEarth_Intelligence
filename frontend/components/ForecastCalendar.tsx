// 5x6 heatmap calendar for the 30-day forecast (CLAUDE.md Feature 10).
// Each cell shows day number + date, background follows the standard severity
// scale (Low green / Medium yellow / High orange / Critical red). Clicking a
// cell calls `onSelect(day)` so the page can expand the full prediction card.
// A Min Severity filter dims cells below the selected threshold to help users
// focus on high-risk windows without hiding context.

"use client"

import { useState } from "react"

import type { ForecastDay, SeverityLevel } from "@/types"
import { S, Sf } from "@/lib/strings"
import { FilterBar } from "@/components/FilterBar"

const SEVERITY_TILE: Record<SeverityLevel, string> = {
  Low:      "bg-green-100   hover:bg-green-200   text-green-900",
  Medium:   "bg-yellow-100  hover:bg-yellow-200  text-yellow-900",
  High:     "bg-orange-100  hover:bg-orange-200  text-orange-900",
  Critical: "bg-red-100     hover:bg-red-200     text-red-900",
}

const SEVERITY_RANK: Record<SeverityLevel, number> = {
  Low: 0, Medium: 1, High: 2, Critical: 3,
}

export function ForecastCalendar({
  days,
  selectedOffset,
  onSelect,
}: {
  days: ForecastDay[]
  selectedOffset: number | null
  onSelect: (offset: number) => void
}) {
  const [minSev, setMinSev] = useState("All")

  const minRank = minSev === "All" ? 0 : (SEVERITY_RANK[minSev as SeverityLevel] ?? 0)

  const sevOptions = [
    { value: "All",      label: S("filter.all.severities") },
    { value: "Medium",   label: S("filter.severity.mediumPlus") },
    { value: "High",     label: S("filter.severity.highPlus") },
    { value: "Critical", label: S("filter.severity.criticalOnly") },
  ]

  return (
    <div>
      <h2 className="text-lg font-semibold text-slate-800">
        {S("forecast.calendar.title")}
      </h2>
      <p className="mt-1 text-xs text-slate-500 max-w-2xl">
        {S("forecast.calendar.help")}
      </p>
      <div className="mt-3">
        <FilterBar
          filters={[
            {
              id: "fc-sev", label: S("filter.label.minSeverity"),
              options: sevOptions, value: minSev, onChange: setMinSev,
            },
          ]}
        />
      </div>
      <div className="mt-4 grid grid-cols-5 gap-2">
        {days.map((d) => {
          const sev    = d.severity_level
          const dimmed = SEVERITY_RANK[sev] < minRank
          const ringCls =
            selectedOffset === d.forecast_day_offset
              ? "ring-2 ring-slate-800"
              : "ring-1 ring-slate-200"
          const label = Sf("forecast.calendar.day", { n: d.forecast_day_offset + 1 })
          return (
            <button
              key={d.forecast_day_offset}
              type="button"
              onClick={() => onSelect(d.forecast_day_offset)}
              className={`relative aspect-square rounded-lg p-2 text-left text-xs ${SEVERITY_TILE[sev]} ${ringCls} focus:outline-none focus:ring-2 focus:ring-slate-800 transition-opacity ${dimmed ? "opacity-25" : "opacity-100"}`}
              aria-label={label}
            >
              <div className="text-[10px] uppercase tracking-wide opacity-75">
                {d.date.slice(5)}
              </div>
              <div className="text-base font-bold leading-tight">
                {d.forecast_day_offset + 1}
              </div>
              <div className="absolute bottom-1.5 right-1.5 text-[10px] tabular-nums opacity-80">
                {(d.probability_score * 100).toFixed(0)}%
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
