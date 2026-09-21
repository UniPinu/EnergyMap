/**
 * Client-side timescale switching (CONTEXT.md §1.4): one fetched series (widest window),
 * sliced to the range and bucket-averaged so the chart never draws more points than pixels.
 */
import type { SeriesPoint } from '@/lib/api'

export type Range = '24h' | 'week' | 'month'
export const RANGE_MS: Record<Range, number> = {
  '24h': 24 * 3600_000,
  week: 7 * 24 * 3600_000,
  month: 31 * 24 * 3600_000,
}

export interface ChartPoint {
  /** bucket start, epoch ms */
  t: number
  v: number
  /** fraction of the bucket's samples that were measured (1 = all measured) */
  measured: number
}

/** Points with t in [now - range, now]. */
export function windowPoints(points: readonly SeriesPoint[], range: Range, now = Date.now()): SeriesPoint[] {
  const from = now - RANGE_MS[range]
  return points.filter((p) => {
    const t = Date.parse(p.t)
    return t >= from && t <= now
  })
}

/** Mean per fixed-width bucket, at most `maxPoints` buckets across the range. */
export function downsample(points: readonly SeriesPoint[], range: Range, maxPoints = 360, now = Date.now()): ChartPoint[] {
  if (points.length === 0) return []
  const from = now - RANGE_MS[range]
  const width = Math.max(RANGE_MS[range] / maxPoints, 5 * 60_000)
  const buckets = new Map<number, { sum: number; n: number; measured: number }>()
  for (const p of points) {
    const t = Date.parse(p.t)
    const b = from + Math.floor((t - from) / width) * width
    const acc = buckets.get(b) ?? { sum: 0, n: 0, measured: 0 }
    acc.sum += p.v
    acc.n += 1
    if (p.q === 'measured') acc.measured += 1
    buckets.set(b, acc)
  }
  return [...buckets.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([t, a]) => ({ t, v: a.sum / a.n, measured: a.measured / a.n }))
}

/** Axis tick label appropriate for the range. */
export function tickLabel(t: number, range: Range): string {
  const d = new Date(t)
  if (range === '24h') return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', timeZone: 'UTC' })
}
