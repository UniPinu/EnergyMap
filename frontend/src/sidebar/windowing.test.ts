import { describe, expect, it } from 'vitest'
import type { SeriesPoint } from '@/lib/api'
import { RANGE_MS, downsample, windowPoints } from './windowing'

const NOW = Date.UTC(2026, 8, 21, 12, 0, 0)
const mk = (minutesAgo: number, v: number, q: SeriesPoint['q'] = 'measured'): SeriesPoint => ({
  t: new Date(NOW - minutesAgo * 60_000).toISOString(),
  v,
  q,
})

describe('windowPoints', () => {
  it('keeps only points inside [now - range, now]', () => {
    const pts = [mk(25 * 60, 1), mk(23 * 60, 2), mk(60, 3), mk(-10, 4)]
    expect(windowPoints(pts, '24h', NOW).map((p) => p.v)).toEqual([2, 3])
    expect(windowPoints(pts, 'week', NOW).map((p) => p.v)).toEqual([1, 2, 3])
  })
})

describe('downsample', () => {
  it('returns at most maxPoints buckets, each the mean of its samples, ordered by time', () => {
    // one point every 5 minutes for 24 h = 288 points; ask for 24 buckets (1 h each)
    const pts = Array.from({ length: 288 }, (_, i) => mk(5 * i, i))
    const out = downsample(pts, '24h', 24, NOW)
    expect(out.length).toBeLessThanOrEqual(25)
    expect(out.length).toBeGreaterThanOrEqual(24)
    for (let i = 1; i < out.length; i++) expect(out[i]!.t).toBeGreaterThan(out[i - 1]!.t)
    const first = out[0]!
    expect(first.t).toBe(NOW - RANGE_MS['24h'])
    // oldest bucket [from, from+1h) holds i = 287 … 277 (i = 276 sits exactly on the boundary)
    expect(first.v).toBeCloseTo(282, 6)
  })

  it('never buckets finer than the 5-minute canonical grid', () => {
    const pts = Array.from({ length: 12 }, (_, i) => mk(5 * i, 1))
    const out = downsample(pts, '24h', 100_000, NOW)
    expect(out.length).toBe(12)
  })

  it('reports the measured fraction per bucket', () => {
    const pts = [mk(2, 1, 'measured'), mk(1, 1, 'interpolated')]
    const out = downsample(pts, '24h', 1, NOW)
    expect(out).toHaveLength(1)
    expect(out[0]!.measured).toBe(0.5)
  })

  it('handles an empty series', () => {
    expect(downsample([], 'month', 10, NOW)).toEqual([])
  })
})
