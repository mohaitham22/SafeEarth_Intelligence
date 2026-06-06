// Shared cascading location picker: continent -> country -> fixed centroid.
//
// Replaces the old free-text lat/lon + country/continent inputs across every
// prediction form (req 1+2). The country list and its fixed centroids come from
// GET /regions/countries (generated offline from EM-DAT). `country` carries the
// exact EM-DAT name so the backend country-tier impact lookup hits; lat/lon are
// derived from the selected country and shown read-only — the user never types
// coordinates.

"use client"

import { useEffect, useMemo, useState } from "react"

import { S, Sf } from "@/lib/strings"
import { endpoints } from "@/lib/endpoints"
import { apiClient } from "@/lib/api"
import type { CountriesResponse, CountryEntry } from "@/types"

export interface LocationValue {
  continent: string
  country:   string   // exact EM-DAT country name
  label:     string
  lat:       number
  lon:       number
}

// Fixed display order; only continents actually present are rendered.
const CONTINENT_ORDER = ["Africa", "Americas", "Asia", "Europe", "Oceania"]

function entryToValue(continent: string, e: CountryEntry): LocationValue {
  return { continent, country: e.name, label: e.label, lat: e.lat, lon: e.lon }
}

export function CountrySelect({
  value,
  onChange,
  idPrefix = "loc",
}: {
  value: LocationValue | null
  onChange: (v: LocationValue) => void
  idPrefix?: string
}) {
  const [data, setData]   = useState<CountriesResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Fetch the picker table once; seed the parent with the default country.
  useEffect(() => {
    let cancelled = false
    endpoints.regions
      .countries(apiClient)
      .then((d) => {
        if (cancelled) return
        setData(d)
        if (!value) {
          const def = d.default
          onChange({
            continent: def.continent,
            country:   def.name,
            label:     def.label,
            lat:       def.lat,
            lon:       def.lon,
          })
        }
      })
      .catch(() => {
        if (!cancelled) setError(S("location.error"))
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const continents = useMemo(
    () =>
      data
        ? CONTINENT_ORDER.filter((c) => (data.continents[c]?.length ?? 0) > 0)
        : [],
    [data],
  )

  // Countries for the currently selected continent, sorted alphabetically.
  const countryList = useMemo(() => {
    if (!data || !value) return []
    return [...(data.continents[value.continent] ?? [])].sort((a, b) =>
      a.label.localeCompare(b.label),
    )
  }, [data, value])

  if (error) {
    return (
      <div role="alert" className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-xs">
        {error}
      </div>
    )
  }

  if (!data || !value) {
    return <div className="text-xs text-slate-400">{S("location.loading")}</div>
  }

  function onContinentChange(continent: string) {
    const list = data!.continents[continent] ?? []
    if (list.length === 0) return
    // Default to the alphabetically first country of the new continent.
    const first = [...list].sort((a, b) => a.label.localeCompare(b.label))[0]
    onChange(entryToValue(continent, first))
  }

  function onCountryChange(name: string) {
    const e = (data!.continents[value!.continent] ?? []).find((c) => c.name === name)
    if (e) onChange(entryToValue(value!.continent, e))
  }

  return (
    <div className="space-y-3">
      <div>
        <label htmlFor={`${idPrefix}-continent`} className="block text-xs font-medium text-slate-700">
          {S("location.continent.label")}
        </label>
        <select
          id={`${idPrefix}-continent`}
          value={value.continent}
          onChange={(e) => onContinentChange(e.target.value)}
          className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-800"
        >
          {continents.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>

      <div>
        <label htmlFor={`${idPrefix}-country`} className="block text-xs font-medium text-slate-700">
          {S("location.country.label")}
        </label>
        <select
          id={`${idPrefix}-country`}
          value={value.country}
          onChange={(e) => onCountryChange(e.target.value)}
          className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-800"
        >
          {countryList.map((c) => (
            <option key={c.name} value={c.name}>{c.label}</option>
          ))}
        </select>
      </div>

      <p className="text-[11px] text-slate-400">
        {Sf("location.coords.auto", {
          lat: value.lat.toFixed(2),
          lon: value.lon.toFixed(2),
        })}
      </p>
    </div>
  )
}
