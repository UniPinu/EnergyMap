import { useMemo, useState, type ReactNode } from 'react'
import { ChevronDown, ChevronUp, LineChart, Scale, Sigma, X } from 'lucide-react'
import type { ClusterNode, TopoNode, Topology } from '@/lib/api'
import { useLive } from '@/store/live'
import { useUi } from '@/store/ui'
import { KIND_ICON } from '@/canvas/nodes/style'
import { SeriesChart } from './SeriesChart'
import { ClusterVitals, NodeVitals, ZoneBalance } from './Vitals'
import type { Range } from './windowing'
import './detail.css'

const RANGES: Range[] = ['24h', 'week', 'month']

/**
 * LIAM TableDetail drawer, ported (Head + CollapsibleHeader sections + DetailItems):
 * vital details not on the node face, the zone balance with its residual, and shadcn charts of
 * consumption / price switchable 24h / week / month (MVP.md §8). Provenance lands in Phase 5.
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
  const node = entity.kind === 'node' ? entity.node : null
  const cluster = entity.kind === 'cluster' ? entity.cluster : null
  const ns = node ? state?.nodes[node.id] : undefined
  const cs = cluster ? state?.clusters[String(cluster.level)]?.[cluster.id] : undefined
  const Icon = KIND_ICON[node ? node.kind : 'cluster']
  const isDk = entity.zone.startsWith('DK')

  return (
    <aside className="emap-detail absolute right-0 top-0" aria-label="details">
      <div className="emap-detail__head">
        <div className="emap-detail__head-title">
          <Icon strokeWidth={1.5} aria-hidden style={{ color: `var(--node-${node ? node.kind : 'source'})` }} />
          <h1 className="emap-detail__heading" title={entity.name}>
            {entity.name}
          </h1>
          <span className="emap-detail__subtitle">
            {node ? node.kind : `Π${cluster?.level}`} · {entity.zone}
            {node?.fuel ? ` · ${node.fuel}` : ''}
          </span>
        </div>
        <button type="button" className="emap-detail__icon-button" aria-label="Close" title="Close" onClick={() => select(null)}>
          <X />
        </button>
      </div>

      <div className="emap-detail__body">
        <Section title="Vitals" icon={<Sigma />}>
          {node ? <NodeVitals node={node} s={ns} /> : cluster ? <ClusterVitals c={cluster} p={cs} /> : null}
        </Section>
        <Section title={`Zone balance · ${entity.zone}`} icon={<Scale />}>
          {isDk ? (
            <ZoneBalance z={zoneState} />
          ) : (
            <div className="emap-detail__item">
              <p className="emap-detail__note">Neighbour zones go live in Phase 4 (ENTSO-E).</p>
            </div>
          )}
        </Section>
        <Section title="Charts" icon={<LineChart />}>
          <div className="emap-detail__item">
            <div className="emap-detail__segments" role="radiogroup" aria-label="chart range">
              {RANGES.map((r) => (
                <button key={r} type="button" role="radio" aria-checked={range === r} className="emap-detail__segment" onClick={() => setRange(r)}>
                  {r}
                </button>
              ))}
            </div>
          </div>
          {!isDk && (
            <div className="emap-detail__item">
              <p className="emap-detail__note">No series for neighbour zones yet.</p>
            </div>
          )}
          {node?.kind === 'source' && isDk && (
            <div className="emap-detail__item">
              <SeriesChart entityId={node.id} quantity="p_gen" label="This source · P_gen" color="var(--node-source)" range={range} />
            </div>
          )}
          {node?.kind === 'consumption' && isDk && (
            <div className="emap-detail__item">
              <SeriesChart entityId={node.id} quantity="demand" label="This load · D" color="var(--node-consumption)" range={range} />
            </div>
          )}
          {isDk && (
            <div className="emap-detail__item">
              <SeriesChart entityId={entity.zone} quantity="demand" label={`${entity.zone} consumption`} color="var(--node-consumption)" range={range} />
            </div>
          )}
          {isDk && (
            <div className="emap-detail__item">
              <SeriesChart entityId={entity.zone} quantity="price" label={`${entity.zone} day-ahead price`} color="var(--node-grid)" range={range} />
            </div>
          )}
        </Section>
      </div>
    </aside>
  )
}

/** LIAM CollapsibleHeader */
function Section({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
  const [closed, setClosed] = useState(false)
  return (
    <>
      <div className="emap-detail__section" role="button" tabIndex={0} onClick={() => setClosed((c) => !c)} onKeyDown={(e) => e.key === 'Enter' && setClosed((c) => !c)}>
        <div className="emap-detail__section-title">
          {icon}
          <h2>{title}</h2>
        </div>
        <span className="emap-detail__icon-button" aria-hidden>
          {closed ? <ChevronDown /> : <ChevronUp />}
        </span>
      </div>
      <div className="emap-detail__content" data-closed={closed}>
        {children}
      </div>
    </>
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
