/**
 * Topology → React Flow graph for one cluster level.
 * Positions come ONLY from the shared projection of (lat, lon) (MVP.md §8); nodes are immovable.
 */
import { useEffect, useState } from 'react'
import { api, type State, type Topology } from '@/lib/api'
import { NORTHERN_EUROPE_BOUNDS, fitBounds, type Projection } from '@/lib/projection'
import type { AnyFlowNode, CorridorEdge, Side } from '@/canvas/types'
import { sourceHandle, targetHandle } from '@/canvas/types'

/**
 * World size in flow-pixels for the region frame (≈ 1° longitude ≈ 1,000 px, so two substations
 * 10 km apart are ~150 px apart and cards do not overlap). ONE constant world for every level:
 * the zoom-driven LOD (Phase 3) must switch levels without moving the viewport.
 */
export const WORLD = { width: 36000, height: 36000 }
export const projection: Projection = fitBounds(NORTHERN_EUROPE_BOUNDS, WORLD, 600)

/** Rendered card size at scale 1, used to centre nodes on their projected point. */
export const CARD = { width: 148, height: 71 }

/**
 * Card scale per cluster level: coarse levels carry few nodes and are viewed zoomed-out, so their
 * cards are drawn larger (information density scales with level, MVP.md §4.2).
 */
export const CARD_SCALE: Record<number, number> = { 0: 20, 1: 6, 2: 1 }
export const cardScale = (level: number) => CARD_SCALE[level] ?? 1

type Loaded = { state: 'loading' } | { state: 'ready'; topology: Topology } | { state: 'error'; message: string }

export function useTopology(): Loaded {
  const [loaded, setLoaded] = useState<Loaded>({ state: 'loading' })
  useEffect(() => {
    let cancelled = false
    api
      .GET('/api/topology')
      .then(({ data, error }) => {
        if (cancelled) return
        if (data) setLoaded({ state: 'ready', topology: data })
        else setLoaded({ state: 'error', message: JSON.stringify(error) })
      })
      .catch((e: unknown) => {
        if (!cancelled) setLoaded({ state: 'error', message: e instanceof Error ? e.message : String(e) })
      })
    return () => {
      cancelled = true
    }
  }, [])
  return loaded
}

function place(lat: number, lon: number, scale: number) {
  const p = projection.project({ lat, lon })
  return { x: p.x - (CARD.width * scale) / 2, y: p.y - (CARD.height * scale) / 2 }
}

/** Pick the handle sides so a step edge leaves/enters on the facing sides of the two cards. */
function sides(a: { x: number; y: number }, b: { x: number; y: number }): [Side, Side] {
  const dx = b.x - a.x
  const dy = b.y - a.y
  if (Math.abs(dx) * CARD.height >= Math.abs(dy) * CARD.width) return dx >= 0 ? ['r', 'l'] : ['l', 'r']
  return dy >= 0 ? ['b', 't'] : ['t', 'b']
}

export interface FlowGraph {
  nodes: AnyFlowNode[]
  edges: CorridorEdge[]
  /** node id → ids of adjacent nodes (for corridor highlight on select) */
  adjacency: Map<string, Set<string>>
}

const IMMOVABLE = { draggable: false, connectable: false, deletable: false } as const

/** Explicit size (card is deterministic): edges and the minimap render before measurement. */
const sized = (scale: number) => ({ width: CARD.width * scale, height: CARD.height * scale })

/** Build the graph for `level`: typed entity nodes at the finest level, cluster nodes above. */
export function buildFlow(topology: Topology, level: number): FlowGraph {
  const finest = topology.meta.finest_level
  const scale = cardScale(level)
  const nodes: AnyFlowNode[] = []
  const pos = new Map<string, { x: number; y: number }>()

  if (level >= finest) {
    for (const n of topology.nodes) {
      const position = place(n.lat, n.lon, scale)
      pos.set(n.id, position)
      nodes.push({
        id: n.id,
        type: n.kind,
        position,
        ...sized(scale),
        ...IMMOVABLE,
        data: {
          scale,
          name: n.name,
          zone: n.zone,
          kind: n.kind,
          capacityMw: n.capacity_mw ?? null,
          energyMwh: n.energy_mwh ?? null,
          fuel: n.fuel ?? null,
          voltageKv: n.voltage_kv ?? null,
          related: false,
        },
      } as AnyFlowNode)
    }
  } else {
    const view = topology.views[String(level)]
    if (!view) throw new Error(`no view for level ${level}`)
    for (const c of view.nodes) {
      const position = place(c.lat, c.lon, scale)
      pos.set(c.id, position)
      nodes.push({
        id: c.id,
        type: 'cluster',
        position,
        ...sized(scale),
        ...IMMOVABLE,
        data: {
          scale,
          name: c.name,
          zone: c.zone,
          level: c.level,
          counts: { source: 0, grid: 0, consumption: 0, storage: 0, ...c.counts },
          sourceMw: c.capacity_mw['source'] ?? 0,
          storageMw: c.capacity_mw['storage'] ?? 0,
          related: false,
        },
      })
    }
  }

  const raw =
    level >= finest
      ? topology.edges.map((e) => ({ id: e.id, from: e.from, to: e.to, kind: e.kind, rating: e.rating_mw, members: 1 }))
      : topology.views[String(level)]!.edges.map((e) => ({
          id: e.id,
          from: e.from,
          to: e.to,
          kind: e.kind,
          rating: e.rating_mw,
          members: e.members.length,
        }))

  const adjacency = new Map<string, Set<string>>()
  const edges: CorridorEdge[] = raw.map((e) => {
    const a = pos.get(e.from)!
    const b = pos.get(e.to)!
    const [sa, sb] = sides(a, b)
    ;(adjacency.get(e.from) ?? adjacency.set(e.from, new Set()).get(e.from)!).add(e.to)
    ;(adjacency.get(e.to) ?? adjacency.set(e.to, new Set()).get(e.to)!).add(e.from)
    return {
      id: e.id,
      source: e.from,
      target: e.to,
      sourceHandle: sourceHandle(sa),
      targetHandle: targetHandle(sb),
      type: 'corridor',
      selectable: false,
      data: { kind: e.kind, ratingMw: e.rating, members: e.members, highlighted: false, dimmed: false },
    }
  })
  return { nodes, edges, adjacency }
}

/**
 * Overlay a live /api/state snapshot onto a built graph. Nodes/edges the state knows nothing
 * about keep their object identity, so React Flow's memoized components skip them.
 */
export function applyState(graph: FlowGraph, state: State | null): FlowGraph {
  if (!state) return graph
  const nodes = graph.nodes.map((n) => {
    const stats = n.type === 'cluster' ? state.clusters[String(n.data.level)]?.[n.id] : state.nodes[n.id]
    if (!stats) return n
    return { ...n, data: { ...n.data, stats } } as AnyFlowNode
  })
  const edges = graph.edges.map((e) => {
    const es = state.edges[e.id]
    if (!es) return e
    return { ...e, data: { ...e.data!, flow: es.flow, loading: es.loading } }
  })
  return { nodes, edges, adjacency: graph.adjacency }
}
