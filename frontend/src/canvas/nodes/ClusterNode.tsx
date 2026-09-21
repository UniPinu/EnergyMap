import { memo } from 'react'
import type { NodeProps } from '@xyflow/react'
import { Boxes, Scale, Sigma } from 'lucide-react'
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
      badge={`Π${data.level}`}
      selected={!!selected}
      related={data.related}
      scale={data.scale}
      rows={[
        { icon: Scale, label: 'n', value: n == null ? '—' : `${n > 0 ? '+' : ''}${mw(n)}`, primary: true, stale: s?.quality === 'estimated' },
        { icon: Sigma, label: 'gen / load', value: s?.p_gen == null && s?.demand == null ? '—' : `${s?.p_gen == null ? '—' : Math.round(s.p_gen).toLocaleString('en-US')} / ${mw(s?.demand)}` },
        { icon: Boxes, label: 'members', value: `${c.grid}g ${c.source}s ${c.consumption}c ${c.storage}b` },
      ]}
    />
  )
})
