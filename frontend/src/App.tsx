import { useEffect, useState } from 'react'
import { API_BASE, api, type Health } from '@/lib/api'
import { useTopology } from '@/lib/topology'
import { useUi } from '@/store/ui'
import { GridCanvas } from '@/canvas/GridCanvas'
import { Sidebar } from '@/sidebar/Sidebar'
import { startStatePolling, useLive } from '@/store/live'
import { cn } from '@/lib/utils'

type Status = { kind: 'loading' } | { kind: 'ok'; health: Health } | { kind: 'error'; message: string }

/**
 * App frame. Phase 1: the balance-graph canvas renders the static topology at a chosen cluster
 * level. Sidebar (Phase 2), zoom-driven LOD + choropleth (Phase 3) mount into this frame.
 */
export default function App() {
  const [status, setStatus] = useState<Status>({ kind: 'loading' })
  const topo = useTopology()

  // Live state: the browser polls only service B (never Energinet), once a minute.
  useEffect(() => startStatePolling(60_000), [])

  useEffect(() => {
    let cancelled = false
    api
      .GET('/health')
      .then(({ data, error }) => {
        if (cancelled) return
        if (data) setStatus({ kind: 'ok', health: data })
        else setStatus({ kind: 'error', message: JSON.stringify(error) })
      })
      .catch((e: unknown) => {
        if (!cancelled) setStatus({ kind: 'error', message: e instanceof Error ? e.message : String(e) })
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className="flex h-full flex-col bg-background text-foreground">
      <header className="flex items-center justify-between gap-4 border-b px-4 py-2">
        <div className="flex items-baseline gap-3">
          <h1 className="text-sm font-semibold tracking-tight">Northern European Electricity Balance Terminal</h1>
          <span className="text-xs text-muted-foreground">phase 2 — DK live</span>
        </div>
        <div className="flex items-center gap-4">
          {topo.state === 'ready' && <LevelSwitch levels={topo.topology.meta.levels} />}
          <NodeTypeLegend />
        </div>
      </header>

      <main className="relative min-h-0 flex-1">
        {topo.state === 'loading' && <Center>loading topology…</Center>}
        {topo.state === 'error' && <Center className="text-destructive">topology unavailable: {topo.message}</Center>}
        {topo.state === 'ready' && <GridCanvas topology={topo.topology} />}
        {topo.state === 'ready' && <Sidebar topology={topo.topology} />}
      </main>

      <footer className="flex items-center gap-4 border-t px-4 py-1.5 font-mono text-[11px] text-muted-foreground">
        <span>api {API_BASE}</span>
        <BackendStatus status={status} />
        <LiveStatus />
        {topo.state === 'ready' && (
          <span className="ml-auto">
            topology {topo.topology.nodes.length} nodes · {topo.topology.edges.length} edges · built {topo.topology.meta.built_at_utc}
          </span>
        )}
      </footer>
    </div>
  )
}

function Center({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn('flex h-full items-center justify-center text-sm text-muted-foreground', className)}>{children}</div>
}

function LevelSwitch({ levels }: { levels: Array<{ level: number; name: string; description: string }> }) {
  const level = useUi((s) => s.level)
  const setLevel = useUi((s) => s.setLevel)
  return (
    <div className="flex items-center gap-1 text-xs" role="radiogroup" aria-label="cluster level">
      <span className="mr-1 text-muted-foreground">level</span>
      {levels.map((l) => (
        <button
          key={l.level}
          role="radio"
          aria-checked={level === l.level}
          title={l.description}
          onClick={() => setLevel(l.level)}
          className={cn(
            'rounded border px-2 py-0.5 font-mono',
            level === l.level ? 'border-primary bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          Π{l.level} {l.name}
        </button>
      ))}
    </div>
  )
}

function LiveStatus() {
  const state = useLive((s) => s.state)
  const error = useLive((s) => s.error)
  const selectedId = useUi((s) => s.selectedId)
  if (error && !state) return <span className="text-destructive">state: unavailable ({error})</span>
  if (!state) return <span>state: loading…</span>
  const dk1 = state.zones['DK1']
  return (
    <span data-testid="live-status">
      state @ {state.t_utc.slice(0, 16).replace('T', ' ')}Z · DK1 {dk1?.live ? 'live' : 'no data'}
      {dk1?.live && dk1.p_gen != null ? ` · gen ${Math.round(dk1.p_gen)} MW · load ${dk1.demand == null ? '—' : Math.round(dk1.demand) + ' MW'}` : ''}
      {dk1?.residual_hat != null ? ` · r̂ ${(dk1.residual_hat * 100).toFixed(1)}%` : ''}
      {selectedId ? ` · selected ${selectedId}` : ''}
    </span>
  )
}

function NodeTypeLegend() {
  const types: Array<[string, string]> = [
    ['source', 'bg-node-source'],
    ['grid', 'bg-node-grid'],
    ['consumption', 'bg-node-consumption'],
    ['storage', 'bg-node-storage'],
  ]
  return (
    <ul className="flex gap-3 text-xs text-muted-foreground">
      {types.map(([name, cls]) => (
        <li key={name} className="flex items-center gap-1.5">
          <span className={`inline-block size-2 rounded-full ${cls}`} />
          {name}
        </li>
      ))}
    </ul>
  )
}

function BackendStatus({ status }: { status: Status }) {
  switch (status.kind) {
    case 'loading':
      return <span>backend: connecting…</span>
    case 'error':
      return <span className="text-destructive">backend: unreachable ({status.message})</span>
    case 'ok':
      return (
        <span>
          <span className="text-node-source">backend: {status.health.status}</span> · v{status.health.version} · server time{' '}
          {status.health.time_utc}
        </span>
      )
  }
}
