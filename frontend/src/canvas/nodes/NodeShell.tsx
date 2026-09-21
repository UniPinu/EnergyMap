import { Handle, Position } from '@xyflow/react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { NodeKind } from '@/lib/api'
import { sourceHandle, targetHandle } from '@/canvas/types'
import { ACCENT, KIND_ICON } from './style'
import './node.css'

/**
 * LIAM TableNode structure (TableNode → TableHeader → TableColumnList/TableColumn), ported:
 * a card with a muted header (icon + name) and rows of icon + label + monospace value.
 * `related` = LIAM's isHighlighted (1px accent border), `selected` = isActiveHighlighted (2px).
 * Cheap CSS on purpose — hundreds may be mounted (CONTEXT.md §1.1).
 */

const SIDES = [
  { side: 'l', pos: Position.Left },
  { side: 'r', pos: Position.Right },
  { side: 't', pos: Position.Top },
  { side: 'b', pos: Position.Bottom },
] as const

function Handles() {
  return (
    <>
      {SIDES.map(({ side, pos }) => (
        <span key={side}>
          <Handle id={sourceHandle(side)} type="source" position={pos} />
          <Handle id={targetHandle(side)} type="target" position={pos} />
        </span>
      ))}
    </>
  )
}

export interface StatRow {
  icon: LucideIcon
  label: string
  value: string
  /** the kind's primary statistic (rendered brighter, like LIAM's key column) */
  primary?: boolean
  /** value is held / carried forward */
  stale?: boolean
}

export function NodeShell({
  kind,
  title,
  badge,
  rows,
  selected,
  related,
  scale = 1,
}: {
  kind: NodeKind | 'cluster'
  title: string
  badge?: string
  rows: StatRow[]
  selected: boolean
  related: boolean
  /** CSS zoom applied to the whole card (coarse levels draw larger cards). */
  scale?: number
}) {
  const Icon = KIND_ICON[kind]
  const style: Record<string, string | number> = { '--accent': ACCENT[kind].var }
  if (scale !== 1) style['zoom'] = scale
  return (
    <div className={cn('emap-node', related && 'emap-node--highlighted', selected && 'emap-node--active')} style={style} data-kind={kind}>
      <Handles />
      <div className="emap-node__header">
        <Icon className="emap-node__icon" strokeWidth={1.5} aria-hidden />
        <span className="emap-node__name" title={title}>
          {title}
        </span>
        {badge && <span className="emap-node__badge">{badge}</span>}
      </div>
      {rows.map((r) => (
        <div key={r.label} className="emap-node__row">
          <div className="emap-node__cell">
            <r.icon className={cn('emap-node__row-icon', r.primary && 'emap-node__row-icon--primary')} strokeWidth={1.5} aria-hidden />
            <span className="emap-node__label">{r.label}</span>
            <span
              className={cn('emap-node__value', r.primary && 'emap-node__value--primary', r.stale && 'emap-node__value--stale')}
              title={r.stale ? 'held value (source lag)' : undefined}
            >
              {r.value}
              {r.stale ? ' ◌' : ''}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}
