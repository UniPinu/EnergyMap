import { BatteryCharging, Building2, Layers, Waypoints, Zap, type LucideIcon } from 'lucide-react'
import type { NodeKind } from '@/lib/api'

/** Header icon per kind (LIAM uses lucide's Table2 for every table; we key it by node type). */
export const KIND_ICON: Record<NodeKind | 'cluster', LucideIcon> = {
  source: Zap,
  grid: Waypoints,
  consumption: Building2,
  storage: BatteryCharging,
  cluster: Layers,
}

/** Colour = node type (MVP.md §8): source is LIAM's primary accent; the rest match its register. */
export const ACCENT: Record<NodeKind | 'cluster', { text: string; dot: string; var: string }> = {
  source: { text: 'text-node-source', dot: 'bg-node-source', var: 'var(--node-source)' },
  grid: { text: 'text-node-grid', dot: 'bg-node-grid', var: 'var(--node-grid)' },
  consumption: { text: 'text-node-consumption', dot: 'bg-node-consumption', var: 'var(--node-consumption)' },
  storage: { text: 'text-node-storage', dot: 'bg-node-storage', var: 'var(--node-storage)' },
  cluster: { text: 'text-node-source', dot: 'bg-node-source', var: 'var(--primary-accent)' },
}

export const fmtMw = (v: number | null | undefined, unit = 'MW') =>
  v == null ? '—' : `${Math.round(v).toLocaleString('en-US')} ${unit}`
