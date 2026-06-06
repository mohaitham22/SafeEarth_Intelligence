// Leaflet risk map — Client Component, browser-only.
//
// CRITICAL: Leaflet touches `window` at module load. This file is loaded ONLY
// via `next/dynamic(import("@/components/RiskMap"), { ssr: false })` from the
// /map page. Do NOT import it from a Server Component anywhere else.
//
// Visualisation: discrete CircleMarkers colored by the shared risk scale
// (lib/riskScale) so a color ALWAYS means one risk level — the legend is exact.
// (A heatmap blends by density/interpolation and cannot guarantee that.)
//
// Interaction: CLICK-to-predict. Hover-to-predict is intentionally not used —
// POST /predictions/predict is Subscriber+, rate-limited 60/min, and runs ML+RAG,
// so firing it per hover would 401 for guests and exhaust the limit. Hovering a
// marker instead shows its precomputed risk in a tooltip (local data, no network).

"use client"

import { useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { useSession } from "next-auth/react"
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Tooltip,
  Popup,
  useMapEvents,
} from "react-leaflet"
import L from "leaflet"
import "leaflet/dist/leaflet.css"

import { S, Sf } from "@/lib/strings"
import { FilterBar } from "@/components/FilterBar"
import { SeverityBadge } from "@/components/SeverityBadge"
import { endpoints } from "@/lib/endpoints"
import type { ApiError } from "@/lib/api"
import { continentFromLatLon } from "@/lib/geo"
import { meetsRole } from "@/lib/permissions"
import { RISK_LEVELS, getRiskLevel, colorForScore } from "@/lib/riskScale"
import type { DisasterType, PredictionResult, RiskMapPoint } from "@/types"

interface Pending {
  lat: number
  lon: number
  disaster_type: DisasterType
}

// ------------------------------------------------------------------
// Click anywhere on the (empty) map → predict using the active filter type.
// ------------------------------------------------------------------
function MapClickHandler({ onPick }: { onPick: (lat: number, lon: number) => void }) {
  useMapEvents({
    click(e) {
      onPick(e.latlng.lat, e.latlng.lng)
    },
  })
  return null
}

// ------------------------------------------------------------------
// Legend — reads RISK_LEVELS so swatch color + range always match markers.
// ------------------------------------------------------------------
function Legend() {
  return (
    <div className="absolute right-3 bottom-3 z-[1000] rounded-md border border-slate-200 bg-white/95 backdrop-blur px-3 py-2 shadow text-xs">
      <div className="font-semibold text-slate-700 mb-1">{S("map.legend.title")}</div>
      {RISK_LEVELS.map((b) => (
        <div key={b.level} className="flex items-center gap-2 mb-1 last:mb-0">
          <span className="h-3 w-3 rounded-sm" style={{ background: b.color }} />
          <span className="text-slate-600">
            {S(`map.legend.${b.level.toLowerCase()}`)} · {b.min}–{b.max}
          </span>
        </div>
      ))}
    </div>
  )
}

// ------------------------------------------------------------------
// Popup body — click-to-predict result (Subscriber+) or sign-up CTA (guest).
// Keyed by location so each click remounts with fresh state.
// ------------------------------------------------------------------
function PredictPopupBody({
  pending,
  isAuthed,
  onSignup,
  onOpenFull,
}: {
  pending: Pending
  isAuthed: boolean
  onSignup: () => void
  onOpenFull: () => void
}) {
  const [loading, setLoading] = useState(false)
  const [result, setResult]   = useState<PredictionResult | null>(null)
  const [error, setError]     = useState<string | null>(null)

  useEffect(() => {
    if (!isAuthed) return
    let alive = true
    setLoading(true)
    setError(null)
    setResult(null)
    endpoints.predictions
      .predict({
        latitude:      pending.lat,
        longitude:     pending.lon,
        disaster_type: pending.disaster_type,
        continent:     continentFromLatLon(pending.lat, pending.lon),
        country:       "Unknown", // backend EM-DAT lookup falls back to global
      })
      .then((r) => { if (alive) setResult(r) })
      .catch((e: unknown) => {
        if (!alive) return
        const err = e as ApiError
        if (err?.status === 429)      setError(S("map.popup.rateLimit"))
        else if (err?.status === 401) setError(S("map.popup.unauth"))
        else                          setError(S("map.popup.error"))
      })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [isAuthed, pending.lat, pending.lon, pending.disaster_type])

  const coords = (
    <div className="font-medium text-slate-800">
      {S("map.popup.lat")}: {pending.lat.toFixed(4)} · {S("map.popup.lon")}: {pending.lon.toFixed(4)}
    </div>
  )

  // Guest → no predict call; sign-up CTA.
  if (!isAuthed) {
    return (
      <div className="text-xs">
        {coords}
        <button
          type="button"
          onClick={onSignup}
          className="mt-2 inline-flex items-center rounded-md bg-slate-800 text-white px-3 py-1.5 text-xs font-medium hover:bg-slate-700"
        >
          {S("map.popup.guestCta")}
        </button>
      </div>
    )
  }

  return (
    <div className="text-xs min-w-[180px]">
      {coords}
      <div className="mt-1 text-slate-500">
        {S("map.popup.disaster")}: <span className="font-medium text-slate-700">{pending.disaster_type}</span>
      </div>

      {loading && <div className="mt-2 text-slate-500">{S("map.popup.predicting")}</div>}

      {error && <div className="mt-2 text-red-600">{error}</div>}

      {result && (
        <div className="mt-2 space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-slate-500">{S("map.popup.severity")}:</span>
            <SeverityBadge level={result.severity_level} />
          </div>
          <div className="text-slate-600 tabular-nums">
            {S("map.popup.probability")}: {(result.probability_score * 100).toFixed(1)}%
          </div>
          <div className="text-slate-600 tabular-nums">
            {S("map.popup.riskScore")}: {result.risk_score.toFixed(0)} / 100
          </div>
          <p className="text-[10px] text-slate-400">{S("map.popup.globalNote")}</p>
          <button
            type="button"
            onClick={onOpenFull}
            className="mt-1 inline-flex items-center rounded-md bg-slate-800 text-white px-3 py-1.5 text-xs font-medium hover:bg-slate-700"
          >
            {S("map.popup.openFull")}
          </button>
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------------------
// Main component
// ------------------------------------------------------------------
export default function RiskMap() {
  const router = useRouter()
  const { status } = useSession()
  const isAuthed = status === "authenticated"

  const [points,  setPoints]  = useState<RiskMapPoint[]>([])
  const [dataErr, setDataErr] = useState<string | null>(null)
  const [pending, setPending] = useState<Pending | null>(null)

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

  const filteredPoints = useMemo(
    () =>
      points.filter((p) => {
        const typeOk  = filterType  === "All" || p.disaster_type === filterType
        const levelOk = filterLevel === "All" || getRiskLevel(p.risk_score) === filterLevel
        return typeOk && levelOk
      }),
    [points, filterType, filterLevel],
  )

  // Disaster type to use for an empty-map click (no marker under the cursor).
  const fallbackType: DisasterType =
    (filterType !== "All" ? filterType : "Flood") as DisasterType

  function handleOpenFull() {
    // The dashboard form is now country-driven (no lat/lon params); the inline
    // popup above already ran the prediction for the clicked point.
    router.push("/dashboard")
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

          {/* Empty-map click → predict with the active filter type. */}
          <MapClickHandler
            onPick={(lat, lon) => setPending({ lat, lon, disaster_type: fallbackType })}
          />

          {/* Discrete markers — fill is the EXACT legend color for the risk band. */}
          {filteredPoints.map((p, i) => {
            const color = colorForScore(p.risk_score)
            const level = getRiskLevel(p.risk_score)
            return (
              <CircleMarker
                key={`${p.lat},${p.lon},${p.disaster_type},${i}`}
                center={[p.lat, p.lon]}
                radius={6}
                pathOptions={{
                  color,
                  fillColor: color,
                  fillOpacity: 0.85,
                  weight: 1,
                }}
                eventHandlers={{
                  click(e) {
                    // Don't also fire the empty-map click handler.
                    L.DomEvent.stopPropagation(e)
                    setPending({
                      lat: p.lat,
                      lon: p.lon,
                      disaster_type: p.disaster_type as DisasterType,
                    })
                  },
                }}
              >
                {/* Hover tooltip — precomputed risk, no network call. */}
                <Tooltip direction="top" offset={[0, -4]}>
                  <span className="text-xs">
                    {p.disaster_type} · {S(`severity.${level}`)} · {p.risk_score.toFixed(0)}/100
                  </span>
                </Tooltip>
              </CircleMarker>
            )
          })}

          {pending && (
            <Popup
              position={[pending.lat, pending.lon]}
              eventHandlers={{ remove: () => setPending(null) }}
            >
              <PredictPopupBody
                key={`${pending.lat},${pending.lon},${pending.disaster_type}`}
                pending={pending}
                isAuthed={isAuthed}
                onSignup={() => router.push("/register")}
                onOpenFull={handleOpenFull}
              />
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
