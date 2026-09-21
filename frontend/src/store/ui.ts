import { create } from 'zustand'
import type { Range } from '@/sidebar/windowing'

/**
 * UI state kept outside React Flow's own store (CONTEXT.md §1.1 perf rule 3): components read
 * narrow slices instead of the whole nodes/edges arrays.
 */
export interface LodInfo {
  level: number
  /** nodes of the level intersecting the viewport (what React Flow mounts) */
  visible: number
  /** true when the zoom asked for a finer level than the budget allows */
  demoted: boolean
  zoom: number
}

interface UiState {
  /** Cluster level currently rendered (Π₀ … Π_L), chosen by the LOD engine from the zoom. */
  level: number
  lod: LodInfo
  /** Selected node id (a canonical node id at the finest level, or a cluster id). */
  selectedId: string | null
  /** Hovered node id — LIAM highlights the hovered node, its neighbours and their edges. */
  hoverId: string | null
  /** sidebar chart timescale (client-side window over one fetched series) */
  range: Range
  setLod: (info: LodInfo) => void
  select: (id: string | null) => void
  hover: (id: string | null) => void
  setRange: (range: Range) => void
}

export const useUi = create<UiState>((set) => ({
  level: 0,
  lod: { level: 0, visible: 0, demoted: false, zoom: 0 },
  selectedId: null,
  hoverId: null,
  range: '24h',
  setLod: (lod) => set((s) => (s.level === lod.level && s.lod.visible === lod.visible && s.lod.demoted === lod.demoted && Math.abs(s.lod.zoom - lod.zoom) < 1e-3 ? {} : { level: lod.level, lod })),
  select: (selectedId) => set({ selectedId }),
  hover: (hoverId) => set({ hoverId }),
  setRange: (range) => set({ range }),
}))
