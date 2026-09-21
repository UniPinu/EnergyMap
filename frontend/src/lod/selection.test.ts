import { describe, expect, it } from 'vitest'
import type { Topology } from '@/lib/api'
import { remapSelection } from './selection'

const topo = {
  meta: { finest_level: 2, levels: [] },
  nodes: [
    { id: 'bus:a', kind: 'grid', zone: 'DK1', cluster: { '0': 'DK1', '1': 'DK1/c0', '2': 'bus:a' } },
    { id: 'hub:NO2', kind: 'grid', zone: 'NO2', cluster: { '0': 'NO2', '1': 'NO2', '2': 'hub:NO2' } },
  ],
  views: {
    '0': { nodes: [{ id: 'DK1', level: 0, members: ['bus:a'] }, { id: 'NO2', level: 0, members: ['hub:NO2'] }], edges: [] },
    '1': { nodes: [{ id: 'DK1/c0', level: 1, members: ['bus:a'] }, { id: 'NO2', level: 1, members: ['hub:NO2'] }], edges: [] },
  },
} as unknown as Topology

describe('remapSelection', () => {
  it('maps a bus up to its cluster / zone', () => {
    expect(remapSelection(topo, 'bus:a', 2)).toBe('bus:a')
    expect(remapSelection(topo, 'bus:a', 1)).toBe('DK1/c0')
    expect(remapSelection(topo, 'bus:a', 0)).toBe('DK1')
  })
  it('maps a DK cluster down to nothing and a neighbour zone to its hub', () => {
    expect(remapSelection(topo, 'DK1', 2)).toBeNull()
    expect(remapSelection(topo, 'DK1', 1)).toBe('DK1/c0')
    expect(remapSelection(topo, 'NO2', 2)).toBe('hub:NO2')
    expect(remapSelection(topo, 'NO2', 1)).toBe('NO2')
  })
  it('handles nothing selected and unknown ids', () => {
    expect(remapSelection(topo, null, 0)).toBeNull()
    expect(remapSelection(topo, 'nope', 0)).toBeNull()
  })
})
