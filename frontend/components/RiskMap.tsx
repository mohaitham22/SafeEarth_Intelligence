// Leaflet risk heatmap — Client Component, browser-only.
//
// CRITICAL: Leaflet touches `window` at module load. This file is loaded ONLY
// via `next/dynamic(import("@/components/RiskMap"), { ssr: false })` from the
// /map page. Do NOT import this file from a Server Component anywhere else —
// it will crash SSR.

"use client"

import { useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { useSession } from "next-auth/react"
import {
  MapContainer,
  TileLayer,
  Popup,
  useMap,
  useMapEvents,
} from "react-leaflet"
import L from "leaflet"
import "leaflet/dist/leaflet.css"
import "leaflet.heat"

import { S } from "@/lib/strings"
import { FilterBar } from "@/components/FilterBar"
import { endpoints } from "@/lib/endpoints"
import type { RiskMapPoint } from "@/types"

// Green / Yellow / Orange / Red per CLAUDE.md Feature 2.
const HEAT_GRADIENT: Record<number, string> = {
  0.0: "#16a34a",
  0.4: "#facc15",
  0.7: "#f97316",
  1.0: "#dc2626",
}

// Risk score → severity band (mirrors backend severity thresholds but for
// the composite 0–100 risk score, not the 0–1 probability).
function getRiskLevel(score: number): string {
  if (score >= 76) return "Critical"
  if (score >= 56) return "High"
  if (score >= 31) return "Medium"
  return "Low"
}

interface ClickInfo {
  lat: number
  lon: number
}

// ------------------------------------------------------------------
// HeatLayer: adds an L.heatLayer to the parent map when points arrive.
// Re-runs when points change; cleans up on unmount.
// ------------------------------------------------------------------
function HeatLayer({ points }: { points: RiskMapPoint[] }) {
  const map = useMap()

  useEffect(() => {
    if (!map || points.length === 0) return
    const heatPoints: Array<[number, number, number]> = points.map((p) => [
      p.lat,
      p.lon,
      Math.max(0, Math.min(1, p.risk_score / 100)),
    ])
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const layer = (L as any).heatLayer(heatPoints, {
      radius:    22,
      blur:      24,
      maxZoom:   8,
      max:       1.0,
      minOpacity: 0.4,
      gradient:  HEAT_GRADIENT,
    })
    layer.addTo(map)
    return () => {
      layer.remove()
    }
  }, [map, points])

  return null
}

// ------------------------------------------------------------------
// ClickHandler: captures map clicks, surfaces a popup with a CTA.
// ------------------------------------------------------------------
function ClickHandler({ onClick }: { onClick: (info: ClickInfo) => void }) {
  useMapEvents({
    click(e) {
      onClick({ lat: e.latlng.lat, lon: e.latlng.lng })
    },
  })
  return null
}

// ------------------------------------------------------------------
// Legend: small fixed panel, always visible.
// ------------------------------------------------------------------
function Legend() {
  return (
    <div className="absolute right-3 bottom-3 z-[1000] rounded-md border border-slate-200 bg-white/95 backdrop-blur px-3 py-2 shadow text-xs">
      <div className="font-semibold text-slate-700 mb-1">
        {S("map.legend.title")}
      </div>
      <div className="flex items-center gap-2 mb-1">
        <span className="h-3 w-3 rounded-sm" style={{ background: "#16a34a" }} />
        <span className="text-slate-600">{S("map.legend.low")}</span>
      </div>
      <div className="flex items-center gap-2 mb-1">
        <span className="h-3 w-3 rounded-sm" style={{ background: "#facc15" }} />
        <span className="text-slate-600">{S("map.legend.medium")}</span>
      </div>
      <div className="flex items-center gap-2 mb-1">
        <span className="h-3 w-3 rounded-sm" style={{ background: "#f97316" }} />
        <span className="text-slate-600">{S("map.legend.high")}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="h-3 w-3 rounded-sm" style={{ background: "#dc2626" }} />
        <span className="text-slate-600">{S("map.legend.critical")}</span>
      </div>
    </div>
  )
}

// ------------------------------------------------------------------
// Main component
// ------------------------------------------------------------------
export default function RiskMap() {
  const router  = useRouter()
  const { status } = useSession()
  const isAuthed = status === "authenticated"

  const [points,  setPoints]  = useState<RiskMapPoint[]>([])
  const [dataErr, setDataErr] = useState<string | null>(null)
  const [pending, setPending] = useState<ClickInfo | null>(null)

  // Filter state
  const [filterType,  setFilterType]  = useState("All")
  const [filterLevel, setFilterLevel] = useState("All")

  useEffect(() => {
    let live = true
    endpoints.regions
      .riskMap()
      .then((pts) => { if (live) setPoints(pts) })
      .catch(() => { if (live) setDataErr(S("map.dataError")) })
    return () => { live = false }
  }, [])

  // Derive unique disaster types from loaded data (risk_map.json has 5 types).
  const availableTypes = useMemo(
    () => [...new Set(points.map((p) => p.disaster_type))].sort(),
    [points],
  )

  const typeOptions = useMemo(() => [
    { value: "All", label: S("filter.all.types") },
    ...availableTypes.map((t) => ({ value: t, label: t })),
  ], [availableTypes])

  const levelOptions = [
    { value: "All",      label: S("filter.all.levels") },
    { value: "Low",      label: S("filter.riskLevel.low") },
    { value: "Medium",   label: S("filter.riskLevel.medium") },
    { value: "High",     label: S("filter.riskLevel.high") },
    { value: "Critical", label: S("filter.riskLevel.critical") },
  ]

  // Client-side filter — no extra network call needed.
  const filteredPoints = useMemo(
    () =>
      points.filter((p) => {
        const typeOk  = filterType  === "All" || p.disaster_type === filterType
        const levelOk = filterLevel === "All" || getRiskLevel(p.risk_score) === filterLevel
        return typeOk && levelOk
      }),
    [points, filterType, filterLevel],
  )

  function handleConfirm() {
    if (!pending) return
    if (isAuthed) {
      router.push(`/dashboard?lat=${pending.lat.toFixed(4)}&lon=${pending.lon.toFixed(4)}`)
    } else {
      router.push("/register")
    }
  }

  return (
    <div className="space-y-3">
      <FilterBar
        filters={[
          {
            id: "map-type", label: S("filter.label.disasterType"),
            options: typeOptions, value: filterType, onChange: setFilterType,
          },
          {
            id: "map-level", label: S("filter.label.riskLevel"),
            options: levelOptions, value: filterLevel, onChange: setFilterLevel,
          },
        ]}
      />

      <div className="relative h-[70vh] min-h-[420px] rounded-xl overflow-hidden border border-slate-200">
        <MapContainer
          center={[15, 10]}
          zoom={2}
          minZoom={2}
          maxZoom={10}
          scrollWheelZoom
          worldCopyJump
          className="h-full w-full"
        >
          <TileLayer
            attribution={S("map.attribution")}
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          <HeatLayer points={filteredPoints} />

          <ClickHandler onClick={setPending} />

          {pending && (
            <Popup
              position={[pending.lat, pending.lon]}
              eventHandlers={{ remove: () => setPending(null) }}
            >
              <div className="text-xs">
                <div className="font-medium text-slate-800">
                  {S("map.popup.lat")}: {pending.lat.toFixed(4)} ·{" "}
                  {S("map.popup.lon")}: {pending.lon.toFixed(4)}
                </div>
                <button
                  type="button"
                  onClick={handleConfirm}
                  className="mt-2 inline-flex items-center rounded-md bg-slate-800 text-white px-3 py-1.5 text-xs font-medium hover:bg-slate-700"
                >
                  {isAuthed
                    ? S("map.popup.subscriberCta")
                    : S("map.popup.guestCta")}
                </button>
              </div>
            </Popup>
          )}
        </MapContainer>

        <Legend />

        {dataErr && (
          <div className="absolute left-3 top-3 z-[1000] rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 max-w-xs">
            {dataErr}
          </div>
        )}
        {!dataErr && points.length === 0 && (
          <div className="absolute left-3 top-3 z-[1000] rounded-md border border-slate-200 bg-white/95 px-3 py-2 text-xs text-slate-600">
            {S("map.dataLoading")}
          </div>
        )}
      </div>
    </div>
  )
}
