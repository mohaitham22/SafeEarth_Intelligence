// Shared filter bar — one consistent row of labeled dropdowns reused across
// every chart in the app. Pass an array of FilterDef objects; the component
// renders them in order left-to-right and calls onChange on each user pick.

"use client"

export interface FilterOption {
  value: string
  label: string
}

export interface FilterDef {
  id:      string
  label:   string
  options: FilterOption[]
  value:   string
  onChange: (v: string) => void
}

export function FilterBar({ filters }: { filters: FilterDef[] }) {
  if (filters.length === 0) return null
  return (
    <div className="flex flex-wrap items-end gap-4 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
      {filters.map((f) => (
        <div key={f.id} className="flex flex-col gap-1">
          <label
            htmlFor={f.id}
            className="text-[11px] font-semibold uppercase tracking-wide text-slate-500"
          >
            {f.label}
          </label>
          <select
            id={f.id}
            value={f.value}
            onChange={(e) => f.onChange(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 focus:outline-none focus:ring-2 focus:ring-slate-800"
          >
            {f.options.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      ))}
    </div>
  )
}
