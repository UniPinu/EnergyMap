import { useCallback, useMemo } from 'react'
import { Background, BackgroundVariant, Controls, MiniMap, ReactFlow, type NodeMouseHandler, type ReactFlowInstance } from '@xyflow/react'
import type { Topology } from '@/lib/api'
import { buildFlow } from '@/lib/topology'
import { useUi } from '@/store/ui'
import type { AnyFlowNode, CorridorEdge } from '@/canvas/types'
import { CorridorEdgeView } from '@/canvas/edges/CorridorEdge'
import { ClusterNodeView } from '@/canvas/nodes/ClusterNode'
import { ConsumptionNode, GridNode, SourceNode, StorageNode } from '@/canvas/nodes/EntityNodes'

// Hoisted — defining these inline would remount every node on each render (CONTEXT.md §1.1).
const nodeTypes = {
  source: SourceNode,
  grid: GridNode,
  consumption: ConsumptionNode,
  storage: StorageNode,
  cluster: ClusterNodeView,
}
const edgeTypes = { corridor: CorridorEdgeView }
const MINIMAP_COLOR: Record<string, string> = {
  source: 'var(--node-source)',
  grid: 'var(--node-grid)',
  consumption: 'var(--node-consumption)',
  storage: 'var(--node-storage)',
  cluster: 'var(--foreground)',
}
const minimapNodeColor = (n: AnyFlowNode) => MINIMAP_COLOR[n.type ?? 'cluster'] ?? 'var(--foreground)'
const proOptions = { hideAttribution: false }
const fitViewOptions = { padding: 0.05 }

/**
 * The balance-graph layer (MVP.md §8): React Flow with immovable, projection-positioned
 * typed nodes and step corridors. Renders ONE cluster level at a time; the zoom→level function
 * and viewport/budget culling arrive in Phase 3 (until then, level is chosen manually).
 */
export function GridCanvas({ topology }: { topology: Topology }) {
  const level = useUi((s) => s.level)
  const selectedId = useUi((s) => s.selectedId)
  const select = useUi((s) => s.select)

  // Structure for the level: built once per (topology, level).
  const graph = useMemo(() => buildFlow(topology, level), [topology, level])

  // Selection overlay: mark the selected node, its neighbours and incident corridors.
  const nodes = useMemo<AnyFlowNode[]>(() => {
    const related = selectedId ? graph.adjacency.get(selectedId) : undefined
    return graph.nodes.map((n) => {
      const isSel = n.id === selectedId
      const isRel = related?.has(n.id) ?? false
      if (!isSel && !isRel && !n.selected && !n.data.related) return n
      return { ...n, selected: isSel, data: { ...n.data, related: isRel } } as AnyFlowNode
    })
  }, [graph, selectedId])

  const edges = useMemo<CorridorEdge[]>(() => {
    if (!selectedId) return graph.edges
    return graph.edges.map((e) => {
      const hit = e.source === selectedId || e.target === selectedId
      return { ...e, data: { ...e.data!, highlighted: hit, dimmed: !hit } }
    })
  }, [graph, selectedId])

  const onNodeClick = useCallback<NodeMouseHandler<AnyFlowNode>>((_, node) => select(node.id), [select])
  const onPaneClick = useCallback(() => select(null), [select])
  // Dev-only hook for the runtime smoke harness (scripts/smoke.mjs): drive fitView/zoom from outside.
  const onInit = useCallback((instance: ReactFlowInstance<AnyFlowNode, CorridorEdge>) => {
    if (import.meta.env.DEV) (window as unknown as { __emapFlow?: unknown }).__emapFlow = instance
  }, [])

  return (
    <ReactFlow<AnyFlowNode, CorridorEdge>
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodeClick={onNodeClick}
      onPaneClick={onPaneClick}
      onInit={onInit}
      nodesDraggable={false}
      nodesConnectable={false}
      elementsSelectable
      selectNodesOnDrag={false}
      onlyRenderVisibleElements
      minZoom={0.015}
      maxZoom={6}
      fitView
      fitViewOptions={fitViewOptions}
      proOptions={proOptions}
      colorMode="dark"
      className="bg-background"
    >
      <Background variant={BackgroundVariant.Dots} gap={40} size={1} color="color-mix(in oklch, var(--foreground) 12%, transparent)" />
      <Controls showInteractive={false} />
      <MiniMap pannable zoomable nodeColor={minimapNodeColor} maskColor="color-mix(in oklch, var(--background) 70%, transparent)" />
    </ReactFlow>
  )
}
