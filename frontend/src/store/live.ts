import { create } from 'zustand'
import { api, type SeriesResponse, type State } from '@/lib/api'

/**
 * Live data slice: the latest /api/state snapshot (polled) and a cache of /api/series
 * responses keyed by entity|quantity (each fetched once for the widest window; the sidebar
 * windows it client-side to 24h / week / month — CONTEXT.md §1.4).
 */
interface LiveState {
  state: State | null
  fetchedAt: number | null
  error: string | null
  series: Record<string, SeriesResponse | 'loading' | { error: string }>
  refreshState: () => Promise<void>
  ensureSeries: (entityId: string, quantity: SeriesResponse['quantity']) => void
}

export const seriesKey = (entityId: string, quantity: string) => `${entityId}|${quantity}`

export const useLive = create<LiveState>((set, get) => ({
  state: null,
  fetchedAt: null,
  error: null,
  series: {},
  refreshState: async () => {
    try {
      const { data, error } = await api.GET('/api/state')
      if (data) set({ state: data, fetchedAt: Date.now(), error: null })
      else set({ error: JSON.stringify(error) })
    } catch (e) {
      set({ error: e instanceof Error ? e.message : String(e) })
    }
  },
  ensureSeries: (entityId, quantity) => {
    const key = seriesKey(entityId, quantity)
    if (get().series[key] !== undefined) return
    set((s) => ({ series: { ...s.series, [key]: 'loading' } }))
    const end = new Date()
    const start = new Date(end.getTime() - 31 * 24 * 3600 * 1000)
    api
      .GET('/api/series', { params: { query: { entity_id: entityId, quantity, start: start.toISOString(), end: end.toISOString() } } })
      .then(({ data, error }) => {
        set((s) => ({ series: { ...s.series, [key]: data ?? { error: JSON.stringify(error) } } }))
      })
      .catch((e: unknown) => {
        set((s) => ({ series: { ...s.series, [key]: { error: e instanceof Error ? e.message : String(e) } } }))
      })
  },
}))

/** Poll /api/state at the canonical cadence (the source updates every 5 min; we look every minute). */
export function startStatePolling(intervalMs = 60_000): () => void {
  const tick = () => void useLive.getState().refreshState()
  tick()
  const id = window.setInterval(tick, intervalMs)
  return () => window.clearInterval(id)
}
