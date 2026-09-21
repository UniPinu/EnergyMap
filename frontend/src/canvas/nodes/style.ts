import type { NodeKind } from '@/lib/api'

/** Colour = node type (MVP.md §8): emerald / cyan / amber / violet; clusters are neutral. */
export const ACCENT: Record<NodeKind | 'cluster', { border: string; text: string; dot: string }> = {
  source: { border: 'border-node-source', text: 'text-node-source', dot: 'bg-node-source' },
  grid: { border: 'border-node-grid', text: 'text-node-grid', dot: 'bg-node-grid' },
  consumption: { border: 'border-node-consumption', text: 'text-node-consumption', dot: 'bg-node-consumption' },
  storage: { border: 'border-node-storage', text: 'text-node-storage', dot: 'bg-node-storage' },
  cluster: { border: 'border-foreground/60', text: 'text-foreground', dot: 'bg-foreground/70' },
}

export const fmtMw = (v: number | null | undefined, unit = 'MW') =>
  v == null ? '—' : `${Math.round(v).toLocaleString('en-US')} ${unit}`
