import { memo } from 'react'
import { BaseEdge, getSmoothStepPath, type EdgeProps } from '@xyflow/react'
import type { EdgeKind } from '@/lib/api'
import type { CorridorEdge } from '@/canvas/types'

/**
 * Transmission corridor (MVP.md §8): step path, thickness ∝ rating for now (∝ |F_e| once
 * flows arrive in Phase 2/3), tint by kind, full corridor highlighted when an incident node is
 * selected (LIAM behaviour), everything else dimmed.
 */
const STROKE: Record<EdgeKind, string> = {
  ac_line: 'var(--node-grid)',
  hvdc_link: 'var(--node-storage)',
  interconnector: 'var(--node-consumption)',
}

function width(ratingMw: number | null): number {
  if (ratingMw == null || ratingMw <= 0) return 1
  return Math.min(8, 1 + Math.log10(ratingMw) * 1.2)
}

export const CorridorEdgeView = memo(function CorridorEdgeView({
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps<CorridorEdge>) {
  const [path] = getSmoothStepPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, borderRadius: 6 })
  const kind = data?.kind ?? 'ac_line'
  const highlighted = data?.highlighted ?? false
  const dimmed = data?.dimmed ?? false
  return (
    <BaseEdge
      path={path}
      style={{
        stroke: highlighted ? 'var(--ring)' : STROKE[kind],
        strokeWidth: width(data?.ratingMw ?? null) * (highlighted ? 1.5 : 1),
        strokeDasharray: kind === 'hvdc_link' || kind === 'interconnector' ? '6 4' : undefined,
        opacity: dimmed ? 0.12 : highlighted ? 1 : 0.55,
      }}
    />
  )
})
