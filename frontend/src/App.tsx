import { useEffect, useState } from 'react'
import { API_BASE, api, type Health } from '@/lib/api'

type Status = { kind: 'loading' } | { kind: 'ok'; health: Health } | { kind: 'error'; message: string }

/**
 * Phase 0 shell. The balance-graph canvas (Phase 1), sidebar (Phase 2) and
 * LOD/choropleth layers (Phase 3) mount into this frame. What it proves now:
 * the frontend builds, the theme tokens resolve, and it can read service B.
 */
export default function App() {
  const [status, setStatus] = useState<Status>({ kind: 'loading' })

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
      <header className="flex items-center justify-between border-b px-4 py-2">
        <div className="flex items-baseline gap-3">
          <h1 className="text-sm font-semibold tracking-tight">Northern European Electricity Balance Terminal</h1>
          <span className="text-xs text-muted-foreground">phase 0 — foundations</span>
        </div>
        <NodeTypeLegend />
      </header>

      <main className="relative flex flex-1 items-center justify-center">
        <p className="text-sm text-muted-foreground">Balance-graph canvas mounts here in Phase 1.</p>
      </main>

      <footer className="flex items-center gap-4 border-t px-4 py-1.5 font-mono text-[11px] text-muted-foreground">
        <span>api {API_BASE}</span>
        <BackendStatus status={status} />
      </footer>
    </div>
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
    case 'ok': {
      const m = status.health.db.migrations
      return (
        <span>
          <span className="text-node-source">backend: {status.health.status}</span> · v{status.health.version} ·
          db migrations: {m.map((x) => `${String(x.version).padStart(4, '0')}_${x.name}`).join(', ') || 'none'} ·
          server time: {status.health.time_utc}
        </span>
      )
    }
  }
}
