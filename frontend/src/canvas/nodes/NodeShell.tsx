import { Handle, Position } from '@xyflow/react'
import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import type { NodeKind } from '@/lib/api'
import { ACCENT } from './style'
import { sourceHandle, targetHandle } from '@/canvas/types'

/**
 * LIAM-style card: accent header (colour = node type, MVP.md §8), three stat rows,
 * hidden handles on all four sides so step edges can enter/leave on the facing side.
 * Deliberately cheap CSS (no shadows/gradients) — hundreds of these may be mounted.
 */

const SIDES = [
  { side: 'l', pos: Position.Left },
  { side: 'r', pos: Position.Right },
  { side: 't', pos: Position.Top },
  { side: 'b', pos: Position.Bottom },
] as const

export function Handles() {
  return (
    <>
      {SIDES.map(({ side, pos }) => (
        <span key={side}>
          <Handle id={sourceHandle(side)} type="source" position={pos} className="!size-0 !min-h-0 !min-w-0 !border-0 !bg-transparent" />
          <Handle id={targetHandle(side)} type="target" position={pos} className="!size-0 !min-h-0 !min-w-0 !border-0 !bg-transparent" />
        </span>
      ))}
    </>
  )
}

export interface StatRow {
  label: string
  value: string
}

export function NodeShell({
  kind,
  title,
  subtitle,
  rows,
  selected,
  related,
  scale = 1,
  stale = false,
  children,
}: {
  kind: NodeKind | 'cluster'
  title: string
  subtitle?: string
  rows: StatRow[]
  selected: boolean
  related: boolean
  /** CSS zoom applied to the whole card (coarse levels draw larger cards). */
  scale?: number
  /** primary statistic is a held / carried-forward value, not a fresh measurement */
  stale?: boolean
  children?: ReactNode
}) {
  const a = ACCENT[kind]
  return (
    <div
      style={scale !== 1 ? { zoom: scale } : undefined}
      className={cn(
        'w-[148px] rounded-md border bg-card text-card-foreground text-[10px] leading-tight',
        'border-l-[3px]',
        a.border,
        selected && 'ring-2 ring-ring',
        related && !selected && 'ring-1 ring-ring/60',
      )}
    >
      <Handles />
      <div className="flex items-center gap-1.5 border-b px-1.5 py-1">
        <span className={cn('inline-block size-1.5 shrink-0 rounded-full', a.dot)} />
        <span className="truncate font-semibold" title={title}>
          {title}
        </span>
        {subtitle && <span className="ml-auto shrink-0 text-muted-foreground">{subtitle}</span>}
        {stale && (
          <span className="shrink-0 text-muted-foreground" title="held value (source lag)">
            ◌
          </span>
        )}
      </div>
      <div className="space-y-px px-1.5 py-1 font-mono">
        {rows.map((r) => (
          <div key={r.label} className="flex justify-between gap-1">
            <span className="text-muted-foreground">{r.label}</span>
            <span className={cn('truncate', r === rows[0] && a.text)}>{r.value}</span>
          </div>
        ))}
      </div>
      {children}
    </div>
  )
}
