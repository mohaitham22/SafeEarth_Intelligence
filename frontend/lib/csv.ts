// Client-side CSV export. No backend involved: builds an RFC-4180 CSV string
// from headers + rows and triggers a browser download via a Blob URL. Used by
// the dashboard prediction cards, the 30-day forecast, and prediction history
// to provide a "Download data" action (req 5).

type Cell = string | number | null | undefined

function escapeCell(value: Cell): string {
  if (value === null || value === undefined) return ""
  const s = String(value)
  // Quote when the cell contains a comma, quote, CR or LF; double internal quotes.
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

export function toCsv(headers: string[], rows: Cell[][]): string {
  return [headers, ...rows]
    .map((row) => row.map(escapeCell).join(","))
    .join("\r\n")
}

export function downloadCsv(filename: string, csv: string): void {
  // Prepend a UTF-8 BOM (﻿) so Excel opens non-ASCII content correctly.
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
