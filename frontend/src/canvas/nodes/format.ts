/** Number formatting for node faces and the sidebar. `null`/`undefined` always renders as "—". */

export const mw = (v: number | null | undefined, digits = 0): string =>
  v == null ? '—' : `${v.toLocaleString('en-US', { maximumFractionDigits: digits })} MW`

export const pct = (v: number | null | undefined): string => (v == null ? '—' : `${Math.round(v * 100)}%`)

export const signedPct = (v: number | null | undefined): string => {
  if (v == null) return '—'
  const p = Math.round(v * 100)
  return `${p > 0 ? '▲' : p < 0 ? '▼' : '='} ${Math.abs(p)}%`
}

export const sign = (v: number | null | undefined): string =>
  v == null ? '—' : v > 0 ? '▲ inject' : v < 0 ? '▼ withdraw' : '= balanced'

export const eur = (v: number | null | undefined): string =>
  v == null ? '—' : `${v.toLocaleString('en-US', { maximumFractionDigits: 1 })} €/MWh`
