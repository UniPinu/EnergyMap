import { memo } from 'react'
import type { NodeProps } from '@xyflow/react'
import type { ClusterFlowNode } from '@/canvas/types'
import { NodeShell } from './NodeShell'
import { fmtMw } from './style'

/** Super-node for Π_ℓ, ℓ < L: aggregates its members (MVP.md §4.1). Primary statistic only. */
export const ClusterNodeView = memo(function ClusterNodeView({ data, selected }: NodeProps<ClusterFlowNode>) {
  const c = data.counts
  return (
    <NodeShell
      kind="cluster"
      title={data.name}
      subtitle={`Π${data.level}`}
      selected={!!selected}
      related={data.related}
      scale={data.scale}
      rows={[
        { label: 'n', value: fmtMw(null) },
        { label: 'Σ cap', value: fmtMw(data.sourceMw) },
        { label: 'members', value: `${c.grid}g ${c.source}s ${c.consumption}c ${c.storage}b` },
      ]}
    />
  )
})
