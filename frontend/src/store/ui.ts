import { create } from 'zustand'
import type { Range } from '@/sidebar/windowing'

/**
 * UI state kept outside React Flow's own store (CONTEXT.md §1.1 perf rule 3): components read
 * narrow slices instead of the whole nodes/edges arrays.
 */
interface UiState {
  /** Cluster level currently rendered (Π₀ … Π_L). Zoom-driven selection arrives in Phase 3. */
  level: number
  /** Selected node id (a canonical node id at the finest level, or a cluster id). */
  selectedId: string | null
  /** Hovered node id — LIAM highlights the hovered node, its neighbours and their edges. */
  hoverId: string | null
  /** sidebar chart timescale (client-side window over one fetched series) */
  range: Range
  setLevel: (level: number) => void
  select: (id: string | null) => void
  hover: (id: string | null) => void
  setRange: (range: Range) => void
}

export const useUi = create<UiState>((set) => ({
  level: 0,
  selectedId: null,
  hoverId: null,
  range: '24h',
  setLevel: (level) => set({ level, selectedId: null }),
  select: (selectedId) => set({ selectedId }),
  hover: (hoverId) => set({ hoverId }),
  setRange: (range) => set({ range }),
}))
