import { useEffect, useState } from 'react'
import { Zap } from 'lucide-react'
import { api, type Health } from '@/lib/api'
import { useTopology } from '@/lib/topology'
import { useUi } from '@/store/ui'
import { GridCanvas } from '@/canvas/GridCanvas'
import { Sidebar } from '@/sidebar/Sidebar'
import { startStatePolling, useLive } from '@/store/live'
import './app.css'

type Status = { kind: 'loading' } | { kind: 'ok'; health: Health } | { kind: 'error'; message: string }

/**
 * App frame in LIAM's ERDRenderer layout: AppBar + main canvas with the detail drawer on the
 * right and the toolbar floating at the bottom. The browser talks only to service B.
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
    <div className="emap-app">
      <header className="emap-appbar">
        <Zap className="emap-appbar__logo" strokeWidth={1.5} aria-hidden />
        <h1 className="emap-appbar__title">
          Northern European Electricity Balance Terminal<em>phase 2 · DK live</em>
        </h1>
        <div className="emap-appbar__right">
          <StatusLine status={status} />
          <NodeTypeLegend />
        </div>
      </header>

      <main className="emap-main">
        {topo.state === 'loading' && <div className="emap-center">loading topology…</div>}
        {topo.state === 'error' && (
          <div className="emap-center" style={{ color: 'var(--danger-default)' }}>
            topology unavailable: {topo.message}
          </div>
        )}
        {topo.state === 'ready' && <GridCanvas topology={topo.topology} />}
        {topo.state === 'ready' && <Sidebar topology={topo.topology} />}
      </main>
    </div>
  )
}

function StatusLine({ status }: { status: Status }) {
  const state = useLive((s) => s.state)
  const error = useLive((s) => s.error)
  const selectedId = useUi((s) => s.selectedId)
  if (status.kind === 'error') return <span className="emap-appbar__status"><i>backend unreachable · {status.message}</i></span>
  if (status.kind === 'loading') return <span className="emap-appbar__status">connecting…</span>
  if (error && !state) return <span className="emap-appbar__status"><i>state unavailable · {error}</i></span>
  if (!state) return <span className="emap-appbar__status">state loading…</span>
  const dk1 = state.zones['DK1']
  return (
    <span className="emap-appbar__status" data-testid="live-status">
      <b>●</b> {state.t_utc.slice(0, 16).replace('T', ' ')}Z · DK1 {dk1?.live ? 'live' : 'no data'}
      {dk1?.live && dk1.p_gen != null ? ` · gen ${Math.round(dk1.p_gen)} MW · load ${dk1.demand == null ? '—' : Math.round(dk1.demand) + ' MW'}` : ''}
      {dk1?.residual_hat != null ? ` · r̂ ${(dk1.residual_hat * 100).toFixed(1)}%` : ''}
      {selectedId ? ` · selected ${selectedId}` : ''}
    </span>
  )
}

function NodeTypeLegend() {
  const types = ['source', 'grid', 'consumption', 'storage'] as const
  return (
    <ul className="emap-legend" aria-label="node types">
      {types.map((t) => (
        <li key={t}>
          <i style={{ background: `var(--node-${t})` }} />
          {t}
        </li>
      ))}
    </ul>
  )
}
