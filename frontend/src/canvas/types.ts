import type { Edge, Node } from '@xyflow/react'
import type { EdgeKind, NodeKind } from '@/lib/api'

/** Data on a finest-level typed node. Live stats (Phase 2) are optional; `null` renders as "—". */
export interface EntityData extends Record<string, unknown> {
  /** card scale for the level (CSS zoom), see lib/topology CARD_SCALE */
  scale: number
  name: string
  zone: string
  kind: NodeKind
  capacityMw: number | null
  energyMwh: number | null
  fuel: string | null
  voltageKv: number | null
  /** true when the node is adjacent to the selected node (LIAM corridor highlight). */
  related: boolean
}

/** Data on a cluster super-node (levels ℓ < L). */
export interface ClusterData extends Record<string, unknown> {
  scale: number
  name: string
  zone: string
  level: number
  counts: Record<NodeKind, number>
  sourceMw: number
  storageMw: number
  related: boolean
}

export interface CorridorData extends Record<string, unknown> {
  kind: EdgeKind
  ratingMw: number | null
  /** number of physical members bundled into this corridor (1 for a plain edge) */
  members: number
  /** incident to the selected node → full opacity + accent */
  highlighted: boolean
  /** some node is selected and this edge is not incident → dimmed */
  dimmed: boolean
}

export type SourceFlowNode = Node<EntityData, 'source'>
export type GridFlowNode = Node<EntityData, 'grid'>
export type ConsumptionFlowNode = Node<EntityData, 'consumption'>
export type StorageFlowNode = Node<EntityData, 'storage'>
export type ClusterFlowNode = Node<ClusterData, 'cluster'>
export type AnyFlowNode = SourceFlowNode | GridFlowNode | ConsumptionFlowNode | StorageFlowNode | ClusterFlowNode
export type CorridorEdge = Edge<CorridorData, 'corridor'>

/** Handle ids: one source and one target handle per side; chosen per edge from geometry. */
export type Side = 'l' | 'r' | 't' | 'b'
export const sourceHandle = (s: Side) => `s-${s}`
export const targetHandle = (s: Side) => `t-${s}`
