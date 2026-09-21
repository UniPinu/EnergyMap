import { memo } from 'react'
import { BaseEdge, getSmoothStepPath, type EdgeProps } from '@xyflow/react'
import type { CorridorEdge } from '@/canvas/types'
import './edge.css'

/**
 * Transmission corridor. Look ported from LIAM's RelationshipEdge: 1px `--pane-border-hover`
 * stroke, `--node-layout` (accent green) when highlighted, with LIAM's six travelling particles
 * along the highlighted path. Per MVP.md §8 the path is a step (not LIAM's bezier), thickness
 * grows with |F_e| when a flow is measured, and a loaded corridor tints toward warning/danger.
 */
const PARTICLE_COUNT = 6
const ANIMATE_DURATION = 6

function width(flow: number | null | undefined, ratingMw: number | null): number {
  const mwv = flow != null ? Math.abs(flow) : null
  if (mwv == null) return ratingMw && ratingMw > 3000 ? 1.5 : 1
  return Math.min(4, 1 + Math.log10(Math.max(mwv, 1)) * 0.8)
}

export const CorridorEdgeView = memo(function CorridorEdgeView({
  id,
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
  const loading = data?.loading ?? null
  const level = loading == null ? undefined : loading >= 0.9 ? 'danger' : loading >= 0.6 ? 'warning' : undefined
  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        className={`emap-edge${highlighted ? ' emap-edge--highlighted' : ''}`}
        style={{
          strokeWidth: width(data?.flow, data?.ratingMw ?? null),
          strokeDasharray: kind === 'hvdc_link' || kind === 'interconnector' ? '6 4' : undefined,
        }}
        data-loading={level}
      />
      {highlighted &&
        [...Array(PARTICLE_COUNT)].map((_, i) => (
          <ellipse key={`particle-${i}`} rx="5" ry="1.2" fill="url(#emapParticleGradient)">
            <animateMotion
              begin={`${-i * (ANIMATE_DURATION / PARTICLE_COUNT)}s`}
              dur={`${ANIMATE_DURATION}s`}
              repeatCount="indefinite"
              rotate="auto"
              path={path}
              calcMode="spline"
              keySplines="0.42, 0, 0.58, 1.0"
            />
          </ellipse>
        ))}
    </>
  )
})

/** LIAM's RelationshipEdgeParticleMarker gradient; mount once inside the ReactFlow canvas. */
export function ParticleGradient() {
  return (
    <svg width="0" height="0" style={{ position: 'absolute' }}>
      <defs>
        <linearGradient id="emapParticleGradient" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="var(--node-layout)" stopOpacity="0" />
          <stop offset="100%" stopColor="var(--node-layout)" stopOpacity="1" />
        </linearGradient>
      </defs>
    </svg>
  )
}
