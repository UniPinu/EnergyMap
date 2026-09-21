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

/** Thickness ∝ |F_e| when a flow is measured (MVP.md §8), else ∝ rating (structural). */
function width(flow: number | null | undefined, ratingMw: number | null): number {
  const mwv = flow != null ? Math.abs(flow) : ratingMw
  if (mwv == null || mwv <= 0) return 1
  return Math.min(8, 1 + Math.log10(mwv) * 1.2)
}

/** Tint ∝ loading ℓ_e: kind colour below 60 %, amber toward 90 %, red above. */
function loadingStroke(kind: EdgeKind, loading: number | null | undefined): string {
  if (loading == null) return STROKE[kind]
  if (loading >= 0.9) return 'var(--destructive)'
  if (loading >= 0.6) return 'var(--node-consumption)'
  return STROKE[kind]
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
        stroke: highlighted ? 'var(--ring)' : loadingStroke(kind, data?.loading),
        strokeWidth: width(data?.flow, data?.ratingMw ?? null) * (highlighted ? 1.5 : 1),
        strokeDasharray: kind === 'hvdc_link' || kind === 'interconnector' ? '6 4' : undefined,
        opacity: dimmed ? 0.12 : highlighted ? 1 : data?.flow != null ? 0.85 : 0.45,
      }}
    />
  )
})
