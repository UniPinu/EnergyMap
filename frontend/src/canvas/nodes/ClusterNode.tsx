import { memo } from 'react'
import type { NodeProps } from '@xyflow/react'
import type { ClusterFlowNode } from '@/canvas/types'
import { NodeShell } from './NodeShell'
import { mw } from './format'

/** Super-node for Π_ℓ, ℓ < L: balance-preserving sums over its members (MVP.md §4.1). */
export const ClusterNodeView = memo(function ClusterNodeView({ data, selected }: NodeProps<ClusterFlowNode>) {
  const c = data.counts
  const s = data.stats
  const n = s?.net_injection
  return (
    <NodeShell
      kind="cluster"
      title={data.name}
      subtitle={`Π${data.level}`}
      selected={!!selected}
      related={data.related}
      scale={data.scale}
      stale={s?.quality === 'estimated'}
      rows={[
        { label: 'n', value: n == null ? '—' : `${n > 0 ? '+' : ''}${mw(n)}` },
        { label: 'gen / load', value: `${mw(s?.p_gen)} / ${mw(s?.demand)}` },
        { label: 'members', value: `${c.grid}g ${c.source}s ${c.consumption}c ${c.storage}b` },
      ]}
    />
  )
})
