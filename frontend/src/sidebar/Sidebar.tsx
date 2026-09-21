import { useMemo } from 'react'
import type { ClusterNode, TopoNode, Topology } from '@/lib/api'
import { useLive } from '@/store/live'
import { useUi } from '@/store/ui'
import { cn } from '@/lib/utils'
import { ACCENT } from '@/canvas/nodes/style'
import { SeriesChart } from './SeriesChart'
import { ClusterVitals, NodeVitals, ZoneBalance } from './Vitals'
import type { Range } from './windowing'

const RANGES: Range[] = ['24h', 'week', 'month']

/**
 * LIAM-style detail panel (MVP.md §8 "Click → sidebar"): vital details not on the node face,
 * a shadcn chart of consumption / price switchable 24h / week / month, and the node's balance
 * contribution. Provenance (Phase 5) mounts below the charts.
 */
export function Sidebar({ topology }: { topology: Topology }) {
  const selectedId = useUi((s) => s.selectedId)
  const select = useUi((s) => s.select)
  const range = useUi((s) => s.range)
  const setRange = useUi((s) => s.setRange)
  const state = useLive((s) => s.state)

  const entity = useMemo(() => resolve(topology, selectedId), [topology, selectedId])
  if (!entity) return null
  const zoneState = state?.zones[entity.zone]
  const ns = entity.kind === 'node' ? state?.nodes[entity.node.id] : undefined
  const cs = entity.kind === 'cluster' ? state?.clusters[String(entity.cluster.level)]?.[entity.cluster.id] : undefined
  const accent = ACCENT[entity.kind === 'node' ? entity.node.kind : 'cluster']
  const isDk = entity.zone.startsWith('DK')
  const node = entity.kind === 'node' ? entity.node : null

  return (
    <aside className="absolute right-0 top-0 flex h-full w-[360px] flex-col border-l bg-card/95 text-card-foreground backdrop-blur">
      <header className="flex items-start gap-2 border-b px-3 py-2">
        <span className={cn('mt-1.5 inline-block size-2 shrink-0 rounded-full', accent.dot)} />
        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-semibold">{entity.name}</h2>
          <p className="text-xs text-muted-foreground">
            {node ? node.kind : `cluster · Π${entity.kind === 'cluster' ? entity.cluster.level : ''}`} · zone {entity.zone}
            {node?.fuel ? ` · ${node.fuel}` : ''}
          </p>
        </div>
        <button onClick={() => select(null)} className="text-muted-foreground hover:text-foreground" aria-label="close">
          ✕
        </button>
      </header>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-3 py-3">
        {node ? <NodeVitals node={node} s={ns} /> : entity.kind === 'cluster' ? <ClusterVitals c={entity.cluster} p={cs} /> : null}
        {isDk && <ZoneBalance z={zoneState} zone={entity.zone} />}
        {!isDk && <p className="rounded border border-dashed p-2 text-xs text-muted-foreground">Neighbour zones go live in Phase 4 (ENTSO-E).</p>}

        <div className="flex items-center gap-1 text-xs" role="radiogroup" aria-label="chart range">
          <span className="mr-1 text-muted-foreground">range</span>
          {RANGES.map((r) => (
            <button
              key={r}
              role="radio"
              aria-checked={range === r}
              onClick={() => setRange(r)}
              className={cn('rounded border px-2 py-0.5 font-mono', range === r ? 'border-primary bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground')}
            >
              {r}
            </button>
          ))}
        </div>

        {node?.kind === 'source' && isDk && <SeriesChart entityId={node.id} quantity="p_gen" label="This source — P_gen" color="var(--node-source)" range={range} />}
        {node?.kind === 'consumption' && isDk && <SeriesChart entityId={node.id} quantity="demand" label="This load — D" color="var(--node-consumption)" range={range} />}
        {isDk && <SeriesChart entityId={entity.zone} quantity="demand" label={`${entity.zone} consumption`} color="var(--node-consumption)" range={range} />}
        {isDk && <SeriesChart entityId={entity.zone} quantity="price" label={`${entity.zone} day-ahead price`} color="var(--node-grid)" range={range} />}
      </div>
    </aside>
  )
}

type Entity =
  | { kind: 'node'; node: TopoNode; name: string; zone: string }
  | { kind: 'cluster'; cluster: ClusterNode; name: string; zone: string }

function resolve(topology: Topology, id: string | null): Entity | null {
  if (!id) return null
  const node = topology.nodes.find((n) => n.id === id)
  if (node) return { kind: 'node', node, name: node.name, zone: node.zone }
  for (const view of Object.values(topology.views)) {
    const c = view.nodes.find((x) => x.id === id)
    if (c) return { kind: 'cluster', cluster: c, name: c.name, zone: c.zone }
  }
  return null
}
