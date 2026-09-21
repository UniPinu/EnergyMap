/** Choropleth buckets for the residual r̂ (MVP.md §3.4 data-quality signal). */
export const RESIDUAL_BUCKETS: ReadonlyArray<{ upTo: number; cls: string; label: string }> = [
  { upTo: 0.02, cls: 'emap-chor-0', label: '≤ 2 %' },
  { upTo: 0.05, cls: 'emap-chor-1', label: '2–5 %' },
  { upTo: 0.1, cls: 'emap-chor-2', label: '5–10 %' },
  { upTo: 0.2, cls: 'emap-chor-3', label: '10–20 %' },
  { upTo: Infinity, cls: 'emap-chor-4', label: '> 20 %' },
]

export function residualBucket(rHat: number | null | undefined): { cls: string; label: string } {
  if (rHat == null || !Number.isFinite(rHat)) return { cls: 'emap-chor-none', label: 'no data' }
  const a = Math.abs(rHat)
  const b = RESIDUAL_BUCKETS.find((x) => a <= x.upTo) ?? RESIDUAL_BUCKETS[RESIDUAL_BUCKETS.length - 1]!
  return { cls: b.cls, label: b.label }
}
