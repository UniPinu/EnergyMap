import { useEffect } from 'react'
import { useOnViewportChange, useStoreApi, type Viewport } from '@xyflow/react'
import type { FlowGraph } from '@/lib/topology'
import { useUi } from '@/store/ui'
import { selectLevel, viewportRect, type Rect } from './lod'

/**
 * Runs the LOD engine on every viewport change (must live inside <ReactFlow>): picks the level
 * for the zoom, counts the nodes the viewport would mount, demotes while over budget, and
 * publishes {level, visible, demoted} to the UI store — the canvas swaps arrays on `level`.
 */
export function LodController({ structures }: { structures: readonly FlowGraph[] }) {
  const store = useStoreApi()
  const setLod = useUi((s) => s.setLod)

  const evaluate = (vp: Viewport) => {
    const { width, height } = store.getState()
    const rect = viewportRect(vp.x, vp.y, vp.zoom, width, height)
    const boxes: Rect[][] = structures.map((g) => g.nodes.map((n) => ({ x: n.position.x, y: n.position.y, width: n.width ?? 0, height: n.height ?? 0 })))
    const current = useUi.getState().level
    const r = selectLevel(vp.zoom, rect, boxes, current)
    setLod({ ...r, zoom: vp.zoom })
  }

  useOnViewportChange({ onChange: evaluate })
  // evaluate once for the initial (fitView) viewport and whenever the structures change
  useEffect(() => {
    const { transform } = store.getState()
    evaluate({ x: transform[0], y: transform[1], zoom: transform[2] })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structures])
  return null
}
