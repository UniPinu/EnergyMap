import { describe, expect, it } from 'vitest'
import { LEVEL_ZOOM, N_MAX, countVisible, intersects, levelForZoom, levelForZoomWithHysteresis, selectLevel, viewportRect, type Rect } from './lod'

const box = (x: number, y: number, s = 10): Rect => ({ x, y, width: s, height: s })

describe('levelForZoom', () => {
  it('is max{ℓ : z ≥ z_ℓ}', () => {
    expect(levelForZoom(0.01)).toBe(0)
    expect(levelForZoom(LEVEL_ZOOM[1]!)).toBe(1)
    expect(levelForZoom(0.2)).toBe(1)
    expect(levelForZoom(LEVEL_ZOOM[2]!)).toBe(2)
    expect(levelForZoom(5)).toBe(2)
  })

  it('keeps the current level inside the hysteresis band and switches outside it', () => {
    const t = LEVEL_ZOOM[1]!
    expect(levelForZoomWithHysteresis(t * 1.05, 0)).toBe(0) // just above: stay at 0
    expect(levelForZoomWithHysteresis(t * 1.2, 0)).toBe(1) // clearly above: switch
    expect(levelForZoomWithHysteresis(t * 0.95, 1)).toBe(1) // just below: stay at 1
    expect(levelForZoomWithHysteresis(t * 0.8, 1)).toBe(0)
    expect(levelForZoomWithHysteresis(t * 1.05, null)).toBe(1) // no current: naive
  })
})

describe('viewport geometry', () => {
  it('converts the React Flow transform to a flow-space rect', () => {
    // pane 1000×500 at zoom 0.5 translated by (-100, -50): top-left = (200, 100), size = (2000, 1000)
    expect(viewportRect(-100, -50, 0.5, 1000, 500)).toEqual({ x: 200, y: 100, width: 2000, height: 1000 })
  })

  it('intersects and counts', () => {
    const vp = { x: 0, y: 0, width: 100, height: 100 }
    expect(intersects(box(95, 95), vp)).toBe(true) // partial overlap counts (React Flow mounts it)
    expect(intersects(box(100, 100), vp)).toBe(false) // touching edge is outside
    expect(countVisible([box(0, 0), box(50, 50), box(200, 200)], vp)).toBe(2)
  })
})

describe('selectLevel', () => {
  const vp = { x: 0, y: 0, width: 1000, height: 1000 }
  const inside = (n: number) => Array.from({ length: n }, (_, i) => box((i * 37) % 900, (i * 91) % 900))
  const levels = [inside(19), inside(27), inside(600)]

  it('takes the zoom level when within budget', () => {
    expect(selectLevel(0.2, vp, levels, null)).toEqual({ level: 1, visible: 27, demoted: false })
  })

  it('demotes when the finest level would exceed N_max, and reports it', () => {
    const r = selectLevel(1.0, vp, levels, null)
    expect(r.level).toBe(1)
    expect(r.visible).toBe(27)
    expect(r.demoted).toBe(true)
  })

  it('does not demote when only a subset is in view', () => {
    const smallVp = { x: 0, y: 0, width: 40, height: 40 } // few of the 600 boxes intersect
    const r = selectLevel(1.0, smallVp, levels, null)
    expect(r.level).toBe(2)
    expect(r.visible).toBeLessThanOrEqual(N_MAX)
  })

  it('never goes below Π₀ even if Π₀ exceeds the budget', () => {
    const r = selectLevel(0.01, vp, [inside(500)], null, 100)
    expect(r).toEqual({ level: 0, visible: 500, demoted: false })
  })
})
