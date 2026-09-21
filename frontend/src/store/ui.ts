import { create } from 'zustand'

/**
 * UI state kept outside React Flow's own store (CONTEXT.md §1.1 perf rule 3): components read
 * narrow slices instead of the whole nodes/edges arrays.
 */
interface UiState {
  /** Cluster level currently rendered (Π₀ … Π_L). Zoom-driven selection arrives in Phase 3. */
  level: number
  /** Selected node id (a canonical node id at the finest level, or a cluster id). */
  selectedId: string | null
  setLevel: (level: number) => void
  select: (id: string | null) => void
}

export const useUi = create<UiState>((set) => ({
  level: 0,
  selectedId: null,
  setLevel: (level) => set({ level, selectedId: null }),
  select: (selectedId) => set({ selectedId }),
}))
