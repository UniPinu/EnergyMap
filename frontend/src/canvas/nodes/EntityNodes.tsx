import { memo } from 'react'
import type { NodeProps } from '@xyflow/react'
import { Activity, ArrowLeftRight, Battery, Gauge, Hourglass, Percent, Scale, TrendingUp, Zap } from 'lucide-react'
import type { ConsumptionFlowNode, GridFlowNode, SourceFlowNode, StorageFlowNode } from '@/canvas/types'
import { NodeShell } from './NodeShell'
import { mw, pct, sign, signedPct } from './format'
import { fmtMw } from './style'

/**
 * The four typed nodes (MVP.md §3.2). Each face shows the three headline statistics of its
 * kind from the live state vector; anything the backend does not know renders as "—".
 */

export const SourceNode = memo(function SourceNode({ data, selected }: NodeProps<SourceFlowNode>) {
  const s = data.stats
  const stale = s?.quality === 'estimated'
  return (
    <NodeShell
      kind="source"
      title={data.name}
      badge={data.fuel ?? undefined}
      selected={!!selected}
      related={data.related}
      scale={data.scale}
      rows={[
        { icon: Zap, label: 'P_gen', value: mw(s?.p_gen), primary: true, stale },
        { icon: Gauge, label: 'u', value: data.capacityMw ? `${pct(s?.u)} of ${fmtMw(data.capacityMw)}` : pct(s?.u) },
        { icon: TrendingUp, label: 'δ 1h', value: signedPct(s?.delta_1h) },
      ]}
    />
  )
})

export const GridNode = memo(function GridNode({ data, selected }: NodeProps<GridFlowNode>) {
  const s = data.stats
  return (
    <NodeShell
      kind="grid"
      title={data.name}
      badge={data.voltageKv ? `${data.voltageKv} kV` : data.zone}
      selected={!!selected}
      related={data.related}
      scale={data.scale}
      rows={[
        { icon: ArrowLeftRight, label: 'T', value: mw(s?.t_flow), primary: true, stale: s?.quality === 'estimated' },
        { icon: Percent, label: 'λ', value: pct(s?.loading) },
        { icon: Scale, label: 'sgn n', value: sign(s?.net_injection) },
      ]}
    />
  )
})

export const ConsumptionNode = memo(function ConsumptionNode({ data, selected }: NodeProps<ConsumptionFlowNode>) {
  const s = data.stats
  return (
    <NodeShell
      kind="consumption"
      title={data.name}
      badge={data.zone}
      selected={!!selected}
      related={data.related}
      scale={data.scale}
      rows={[
        { icon: Activity, label: 'D', value: mw(s?.demand), primary: true, stale: s?.quality === 'estimated' },
        { icon: Gauge, label: 'ρ', value: pct(s?.rho) },
        { icon: TrendingUp, label: 'δ 1h', value: signedPct(s?.delta_1h) },
      ]}
    />
  )
})

export const StorageNode = memo(function StorageNode({ data, selected }: NodeProps<StorageFlowNode>) {
  const s = data.stats
  return (
    <NodeShell
      kind="storage"
      title={data.name}
      badge={data.fuel ?? undefined}
      selected={!!selected}
      related={data.related}
      scale={data.scale}
      rows={[
        { icon: Zap, label: 'P', value: data.capacityMw ? `${mw(s?.p_store)} / ${fmtMw(data.capacityMw)}` : mw(s?.p_store), primary: true },
        { icon: Battery, label: 'SoC', value: data.energyMwh ? `${pct(s?.soc)} of ${fmtMw(data.energyMwh, 'MWh')}` : pct(s?.soc) },
        { icon: Hourglass, label: 'dur', value: s?.duration_h == null ? '—' : `${s.duration_h.toFixed(1)} h` },
      ]}
    />
  )
})

