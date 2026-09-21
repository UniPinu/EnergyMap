import { describe, expect, it } from 'vitest'
import { northernEuropeProjection } from '@/components/shadcnmaps/map-data/northern-europe'
import { NORTHERN_EUROPE_BOUNDS, fitBounds } from './projection'
import { WORLD } from './topology'

/**
 * Cross-language guard: the authored map-data (Python, topology/emap_topology/mapdata.py)
 * must use exactly the projection the canvas uses, or the choropleth would drift from the nodes.
 */
describe('map-data projection matches the canvas projection', () => {
  it('uses the same bounds, world and padding', () => {
    expect(northernEuropeProjection.bounds).toEqual(NORTHERN_EUROPE_BOUNDS)
    expect(northernEuropeProjection.world).toBe(WORLD.width)
    expect(northernEuropeProjection.world).toBe(WORLD.height)
  })

  it('produces the same scale/translate and pixel for Copenhagen', () => {
    const p = fitBounds(NORTHERN_EUROPE_BOUNDS, WORLD, northernEuropeProjection.padding)
    expect(p.scale).toBeCloseTo(northernEuropeProjection.scale, 6)
    expect(p.translate.x).toBeCloseTo(northernEuropeProjection.translate[0], 6)
    expect(p.translate.y).toBeCloseTo(northernEuropeProjection.translate[1], 6)
    const cph = p.project({ lon: 12.5683, lat: 55.6761 })
    expect(cph.x).toBeCloseTo(14651.712838, 4)
    expect(cph.y).toBeCloseTo(27124.254468, 4)
  })
})
