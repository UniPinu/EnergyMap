import { describe, expect, it } from 'vitest'
import {
  MAX_LAT,
  fitBounds,
  makeProjection,
  mercatorUnit,
  mercatorUnitInverse,
  type LngLat,
} from './projection'

// Independent reference values from the OSM slippy-map formula
// (wiki.openstreetmap.org/wiki/Slippy_map_tilenames) at zoom 0 on a 256px world,
// plus the zoom-10 tile each city falls into. Computed outside this codebase.
const REF: Array<{ name: string; ll: LngLat; px256: [number, number]; tile10: [number, number] }> = [
  { name: 'Copenhagen', ll: { lon: 12.5683, lat: 55.6761 }, px256: [136.937458, 80.126872], tile10: [547, 320] },
  { name: 'Oslo', ll: { lon: 10.7522, lat: 59.9139 }, px256: [135.646009, 74.464602], tile10: [542, 297] },
  { name: 'Aalborg', ll: { lon: 9.9187, lat: 57.0488 }, px256: [135.053298, 78.36445], tile10: [540, 313] },
  { name: 'Hamburg', ll: { lon: 9.9937, lat: 53.5511 }, px256: [135.106631, 82.737083], tile10: [540, 330] },
]

describe('mercatorUnit', () => {
  it('maps the origin to the centre of the unit square', () => {
    const p = mercatorUnit({ lon: 0, lat: 0 })
    expect(p.x).toBeCloseTo(0.5, 12)
    expect(p.y).toBeCloseTo(0.5, 12)
  })

  it('maps the antimeridian and MAX_LAT to the square edges', () => {
    expect(mercatorUnit({ lon: -180, lat: 0 }).x).toBeCloseTo(0, 12)
    expect(mercatorUnit({ lon: 180, lat: 0 }).x).toBeCloseTo(1, 12)
    expect(mercatorUnit({ lon: 0, lat: MAX_LAT }).y).toBeCloseTo(0, 9)
    expect(mercatorUnit({ lon: 0, lat: -MAX_LAT }).y).toBeCloseTo(1, 9)
  })

  it('clamps latitudes beyond MAX_LAT instead of diverging', () => {
    expect(mercatorUnit({ lon: 0, lat: 90 })).toEqual(mercatorUnit({ lon: 0, lat: MAX_LAT }))
    expect(Number.isFinite(mercatorUnit({ lon: 0, lat: -90 }).y)).toBe(true)
  })

  it('has y pointing south (north is up on screen)', () => {
    const oslo = mercatorUnit({ lon: 10, lat: 60 })
    const hamburg = mercatorUnit({ lon: 10, lat: 53.5 })
    expect(oslo.y).toBeLessThan(hamburg.y)
  })

  it('is monotonic in lon (x) and lat (-y)', () => {
    for (let i = -170; i < 170; i += 17) {
      expect(mercatorUnit({ lon: i + 1, lat: 20 }).x).toBeGreaterThan(mercatorUnit({ lon: i, lat: 20 }).x)
    }
    for (let i = -80; i < 80; i += 7) {
      expect(mercatorUnit({ lon: 5, lat: i + 1 }).y).toBeLessThan(mercatorUnit({ lon: 5, lat: i }).y)
    }
  })

  it.each(REF)('matches the OSM reference for $name', ({ ll, px256, tile10 }) => {
    const u = mercatorUnit(ll)
    expect(u.x * 256).toBeCloseTo(px256[0], 5)
    expect(u.y * 256).toBeCloseTo(px256[1], 5)
    const n = 2 ** 10
    expect(Math.floor(u.x * n)).toBe(tile10[0])
    expect(Math.floor(u.y * n)).toBe(tile10[1])
  })
})

describe('mercatorUnitInverse', () => {
  it.each(REF)('round-trips $name to within 1e-9 degrees', ({ ll }) => {
    const back = mercatorUnitInverse(mercatorUnit(ll))
    expect(back.lon).toBeCloseTo(ll.lon, 9)
    expect(back.lat).toBeCloseTo(ll.lat, 9)
  })
})

describe('makeProjection', () => {
  it('applies scale then translate, and inverts exactly', () => {
    const p = makeProjection(1000, { x: -20, y: 30 })
    const u = mercatorUnit({ lon: 12, lat: 56 })
    const px = p.project({ lon: 12, lat: 56 })
    expect(px.x).toBeCloseTo(u.x * 1000 - 20, 9)
    expect(px.y).toBeCloseTo(u.y * 1000 + 30, 9)
    const back = p.unproject(px)
    expect(back.lon).toBeCloseTo(12, 9)
    expect(back.lat).toBeCloseTo(56, 9)
  })

  it('rejects a non-positive scale', () => {
    expect(() => makeProjection(0, { x: 0, y: 0 })).toThrow(RangeError)
    expect(() => makeProjection(-1, { x: 0, y: 0 })).toThrow(RangeError)
  })
})

describe('fitBounds', () => {
  const bounds = { west: 3, south: 49, east: 31, north: 71 }

  it('places the bbox corners on the padded box and centres the slack axis', () => {
    const size = { width: 1000, height: 1000 }
    const pad = 20
    const p = fitBounds(bounds, size, pad)
    const nw = p.project({ lon: bounds.west, lat: bounds.north })
    const se = p.project({ lon: bounds.east, lat: bounds.south })
    // Projected box must lie inside the padded area...
    expect(nw.x).toBeGreaterThanOrEqual(pad - 1e-9)
    expect(nw.y).toBeGreaterThanOrEqual(pad - 1e-9)
    expect(se.x).toBeLessThanOrEqual(size.width - pad + 1e-9)
    expect(se.y).toBeLessThanOrEqual(size.height - pad + 1e-9)
    // ...touch it on the limiting axis...
    const w = se.x - nw.x
    const h = se.y - nw.y
    expect(Math.max(w, h)).toBeCloseTo(size.width - 2 * pad, 9)
    // ...and be centred on the other.
    expect((nw.x + se.x) / 2).toBeCloseTo(size.width / 2, 9)
    expect((nw.y + se.y) / 2).toBeCloseTo(size.height / 2, 9)
  })

  it('preserves aspect ratio (uniform scale) regardless of box shape', () => {
    const wide = fitBounds(bounds, { width: 2000, height: 500 })
    const tall = fitBounds(bounds, { width: 500, height: 2000 })
    for (const p of [wide, tall]) {
      const a = p.project({ lon: 10, lat: 55 })
      const b = p.project({ lon: 11, lat: 55 })
      const c = p.project({ lon: 10, lat: 56 })
      const ua = mercatorUnit({ lon: 10, lat: 55 })
      const ub = mercatorUnit({ lon: 11, lat: 55 })
      const uc = mercatorUnit({ lon: 10, lat: 56 })
      const sx = (b.x - a.x) / (ub.x - ua.x)
      const sy = (c.y - a.y) / (uc.y - ua.y)
      expect(sx).toBeCloseTo(sy, 9)
      expect(sx).toBeCloseTo(p.scale, 9)
    }
  })

  it('rejects degenerate inputs', () => {
    expect(() => fitBounds({ west: 5, south: 49, east: 5, north: 71 }, { width: 10, height: 10 })).toThrow()
    expect(() => fitBounds({ west: 3, south: 71, east: 31, north: 49 }, { width: 10, height: 10 })).toThrow()
    expect(() => fitBounds(bounds, { width: 10, height: 10 }, 5)).toThrow()
  })
})
