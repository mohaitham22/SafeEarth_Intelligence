// Recharts LineChart — Day 1-30 vs probability_score for the selected
// disaster type (CLAUDE.md Feature 10).
//
// CLAUDE.md spec asks for "one line per disaster type". The backend
// /predictions/forecast-30d endpoint takes a single `disaster_type` per
// request, so a true multi-line view would require 8 forecast calls per
// Subscriber — and the rate limit is 5 per hour. Until a Phase 6 backend
// extension returns all 8 type probabilities in one shot, this chart renders
// a single line for whichever type the user selected on the forecast form.

"use client"

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { S } from "@/lib/strings"
import type { ForecastDay } from "@/types"

export function ForecastLineChart({
  days,
  disasterType,
}: {
  days: ForecastDay[]
  disasterType: string
}) {
  const rows = days.map((d) => ({
    day: d.forecast_day_offset + 1,
    probability_pct: +(d.probability_score * 100).toFixed(1),
  }))

  return (
    <div>
      <h2 className="text-lg font-semibold text-slate-800">
        {S("forecast.linechart.title")}
      </h2>
      <p className="mt-1 text-xs text-slate-500 max-w-2xl">
        {S("forecast.linechart.help")}
      </p>
      <div className="mt-4 h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
            <XAxis dataKey="day" tick={{ fontSize: 11, fill: "#475569" }} />
            <YAxis
              tick={{ fontSize: 11, fill: "#475569" }}
              tickFormatter={(v) => `${v}%`}
              domain={[0, 100]}
            />
            <Tooltip
              contentStyle={{ fontSize: 12 }}
              formatter={(v: number) => [`${v}%`, S("result.probability.label")]}
              labelFormatter={(l) => `Day ${l}`}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line
              type="monotone"
              dataKey="probability_pct"
              name={disasterType}
              stroke="#dc2626"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
