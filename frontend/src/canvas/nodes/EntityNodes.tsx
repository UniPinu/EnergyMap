import { memo } from 'react'
import type { NodeProps } from '@xyflow/react'
import type { ConsumptionFlowNode, GridFlowNode, SourceFlowNode, StorageFlowNode } from '@/canvas/types'
import { NodeShell } from './NodeShell'
import { fmtMw } from './style'

/**
 * The four typed nodes (MVP.md §3.2). Each face shows the three headline statistics of its
 * kind; until live data arrives (Phase 2) the measured values render as "—" while the static
 * quantities (nameplate, E_max, voltage) come from the topology.
 */

export const SourceNode = memo(function SourceNode({ data, selected }: NodeProps<SourceFlowNode>) {
  return (
    <NodeShell
      kind="source"
      title={data.name}
      subtitle={data.fuel ?? undefined}
      selected={!!selected}
      related={data.related}
      scale={data.scale}
      rows={[
        { label: 'P_gen', value: fmtMw(null) },
        { label: 'u', value: data.capacityMw ? `— / ${fmtMw(data.capacityMw)}` : '—' },
        { label: 'δ 1h', value: '—' },
      ]}
    />
  )
})

export const GridNode = memo(function GridNode({ data, selected }: NodeProps<GridFlowNode>) {
  return (
    <NodeShell
      kind="grid"
      title={data.name}
      subtitle={data.voltageKv ? `${data.voltageKv} kV` : data.zone}
      selected={!!selected}
      related={data.related}
      scale={data.scale}
      rows={[
        { label: 'T', value: fmtMw(null) },
        { label: 'λ', value: '—' },
        { label: 'sgn n', value: '—' },
      ]}
    />
  )
})

export const ConsumptionNode = memo(function ConsumptionNode({ data, selected }: NodeProps<ConsumptionFlowNode>) {
  return (
    <NodeShell
      kind="consumption"
      title={data.name}
      subtitle={data.zone}
      selected={!!selected}
      related={data.related}
      scale={data.scale}
      rows={[
        { label: 'D', value: fmtMw(null) },
        { label: 'ρ', value: '—' },
        { label: 'δ 1h', value: '—' },
      ]}
    />
  )
})

export const StorageNode = memo(function StorageNode({ data, selected }: NodeProps<StorageFlowNode>) {
  return (
    <NodeShell
      kind="storage"
      title={data.name}
      subtitle={data.fuel ?? undefined}
      selected={!!selected}
      related={data.related}
      scale={data.scale}
      rows={[
        { label: 'P', value: data.capacityMw ? `— / ${fmtMw(data.capacityMw)}` : '—' },
        { label: 'SoC', value: data.energyMwh ? `— / ${fmtMw(data.energyMwh, 'MWh')}` : '—' },
        { label: 'dur', value: '—' },
      ]}
    />
  )
})
