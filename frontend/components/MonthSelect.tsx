// Shared month/season selector used by all three single-shot prediction cards
// (Disaster Type Predictor, Disaster Impact Prediction, Risk Level Classifier).
//
// Replaces the old free-text season <Field> so month/season is entered the SAME
// way everywhere (req 3). Emits a clean number: 0 = "current month" (the backend
// treats season=0 as the current calendar month), 1-12 = a specific month. The
// 30-day Forecast does not use this — it derives each day's month automatically.

"use client"

import { S } from "@/lib/strings"

const MONTH_KEYS = [
  "month.jan", "month.feb", "month.mar", "month.apr", "month.may", "month.jun",
  "month.jul", "month.aug", "month.sep", "month.oct", "month.nov", "month.dec",
]

export function MonthSelect({
  value,
  onChange,
  id = "month",
}: {
  value: number              // 0 = current month, 1-12 = specific month
  onChange: (v: number) => void
  id?: string
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-slate-700">
        {S("month.label")}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(parseInt(e.target.value, 10))}
        className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-800"
      >
        <option value={0}>{S("month.current")}</option>
        {MONTH_KEYS.map((key, i) => (
          <option key={key} value={i + 1}>{S(key)}</option>
        ))}
      </select>
    </div>
  )
}
