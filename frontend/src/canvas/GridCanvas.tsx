import { useCallback, useEffect, useMemo } from 'react'
import { Background, BackgroundVariant, ReactFlow, type NodeMouseHandler, type ReactFlowInstance } from '@xyflow/react'
import type { Topology } from '@/lib/api'
import { applyState, buildFlow } from '@/lib/topology'
import { useLive } from '@/store/live'
import { useUi } from '@/store/ui'
import type { AnyFlowNode, CorridorEdge } from '@/canvas/types'
import { CorridorEdgeView, ParticleGradient } from '@/canvas/edges/CorridorEdge'
import { ClusterNodeView } from '@/canvas/nodes/ClusterNode'
import { ConsumptionNode, GridNode, SourceNode, StorageNode } from '@/canvas/nodes/EntityNodes'
import { Toolbar } from '@/canvas/Toolbar'
import { LodController } from '@/lod/LodController'
import { remapSelection } from '@/lod/selection'
import { ZoneChoropleth } from '@/map/ZoneChoropleth'

// Hoisted — defining these inline would remount every node on each render (CONTEXT.md §1.1).
const nodeTypes = {
  source: SourceNode,
  grid: GridNode,
  consumption: ConsumptionNode,
  storage: StorageNode,
  cluster: ClusterNodeView,
}
const edgeTypes = { corridor: CorridorEdgeView }
const proOptions = { hideAttribution: false }
const fitViewOptions = { padding: 0.05 }
const MIN_ZOOM = 0.015
const MAX_ZOOM = 6

/**
 * The balance-graph layer (MVP.md §8): React Flow with immovable, projection-positioned typed
 * nodes and step corridors, in LIAM's ErdContent configuration (dark, dotted background,
 * panOnScroll, no deletion) and with LIAM's highlight semantics: the active (selected) node
 * gets the 2px accent border; the hovered node, neighbours of the active/hovered node and their
 * corridors get the 1px accent + glow. The level rendered is chosen by the LOD engine from the
 * zoom and the render budget (MVP.md §4.2); Π₀ additionally shows the zone choropleth.
 */
export function GridCanvas({ topology }: { topology: Topology }) {
  const level = useUi((s) => s.level)
  const selectedId = useUi((s) => s.selectedId)
  const hoverId = useUi((s) => s.hoverId)
  const select = useUi((s) => s.select)
  const hover = useUi((s) => s.hover)

  // Structures for every level, built once: the LOD engine counts against all of them and the
  // canvas swaps arrays on the chosen level (positions share one world, so no viewport jump).
  const structures = useMemo(
    () => Array.from({ length: topology.meta.finest_level + 1 }, (_, l) => buildFlow(topology, l)),
    [topology],
  )
  const structure = structures[Math.min(level, structures.length - 1)]!

  // Keep the selection meaningful when the level changes (bus → its cluster, cluster → hub).
  useEffect(() => {
    const mapped = remapSelection(topology, useUi.getState().selectedId, level)
    if (mapped !== useUi.getState().selectedId) select(mapped)
  }, [topology, level, select])

  // Live overlay (one /api/state poll per minute): nodes without any stats keep their identity.
  const state = useLive((s) => s.state)
  const graph = useMemo(() => applyState(structure, state), [structure, state])

  // LIAM highlightNodesAndEdges: active + related-to-active | hovered | related-to-hovered.
  const nodes = useMemo<AnyFlowNode[]>(() => {
    const relActive = selectedId ? graph.adjacency.get(selectedId) : undefined
    const relHover = hoverId ? graph.adjacency.get(hoverId) : undefined
    if (!selectedId && !hoverId) return graph.nodes
    return graph.nodes.map((n) => {
      const isActive = n.id === selectedId
      const isRel = (relActive?.has(n.id) ?? false) || n.id === hoverId || (relHover?.has(n.id) ?? false)
      if (!isActive && !isRel) return n
      return { ...n, selected: isActive, data: { ...n.data, related: isRel } } as AnyFlowNode
    })
  }, [graph, selectedId, hoverId])

  const edges = useMemo<CorridorEdge[]>(() => {
    if (!selectedId && !hoverId) return graph.edges
    return graph.edges.map((e) => {
      const hit = e.source === selectedId || e.target === selectedId || e.source === hoverId || e.target === hoverId
      return hit ? { ...e, zIndex: 1, data: { ...e.data!, highlighted: true } } : e
    })
  }, [graph, selectedId, hoverId])

  const onNodeClick = useCallback<NodeMouseHandler<AnyFlowNode>>((_, node) => select(node.id), [select])
  const onNodeMouseEnter = useCallback<NodeMouseHandler<AnyFlowNode>>((_, node) => hover(node.id), [hover])
  const onNodeMouseLeave = useCallback(() => hover(null), [hover])
  const onPaneClick = useCallback(() => select(null), [select])
  // Dev-only hook for the runtime smoke harness (scripts/smoke.mjs): drive fitView/zoom from outside.
  const onInit = useCallback((instance: ReactFlowInstance<AnyFlowNode, CorridorEdge>) => {
    if (import.meta.env.DEV) (window as unknown as { __emapFlow?: unknown }).__emapFlow = instance
  }, [])

  return (
    <ReactFlow<AnyFlowNode, CorridorEdge>
      colorMode="dark"
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodeClick={onNodeClick}
      onNodeMouseEnter={onNodeMouseEnter}
      onNodeMouseLeave={onNodeMouseLeave}
      onPaneClick={onPaneClick}
      onInit={onInit}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable
      selectNodesOnDrag={false}
      onlyRenderVisibleElements
      panOnScroll
      deleteKeyCode={null}
      minZoom={MIN_ZOOM}
      maxZoom={MAX_ZOOM}
      fitView
      fitViewOptions={fitViewOptions}
      proOptions={proOptions}
      attributionPosition="bottom-left"
      className="bg-background"
    >
      <Background color="var(--color-gray-600)" variant={BackgroundVariant.Dots} size={1} gap={16} />
      <ParticleGradient />
      <ZoneChoropleth />
      <LodController structures={structures} />
      <Toolbar levels={topology.meta.levels} topology={topology} />
    </ReactFlow>
  )
}
