import type { ClusterNode, ClusterState, NodeState, TopoNode, ZoneState } from '@/lib/api'
import { eur, mw, pct, sign, signedPct } from '@/canvas/nodes/format'
import { fmtMw } from '@/canvas/nodes/style'

/** LIAM DetailItem: a heading and definition rows (label left, monospace value right). */
function Item({ heading, rows }: { heading?: string; rows: Array<[string, string, boolean?]> }) {
  return (
    <div className="emap-detail__item">
      {heading && <h3 className="emap-detail__item-heading">{heading}</h3>}
      <dl className="grid gap-1">
        {rows.map(([k, v, muted]) => (
          <div key={k} className="emap-detail__row">
            <dt>{k}</dt>
            <dd data-muted={muted || v === '—'}>{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

/** The §3.2 state vector of one node, plus its static facts from the topology. */
export function NodeVitals({ node, s }: { node: TopoNode; s?: NodeState }) {
  const rows: Array<[string, string, boolean?]> = []
  if (node.kind === 'source') {
    rows.push(['P_gen', mw(s?.p_gen, 1)], ['utilization u', pct(s?.u)], ['δ (1h)', signedPct(s?.delta_1h)], ['nameplate', fmtMw(node.capacity_mw)])
    if (node.dist_key != null) rows.push(['zone share (key)', `${(node.dist_key * 100).toFixed(2)}%`])
    if (node.co2_intensity != null) rows.push(['CO₂ intensity', `${node.co2_intensity} t/MWh`])
  }
  if (node.kind === 'consumption') {
    rows.push(['demand D', mw(s?.demand, 1)], ['ρ (vs normal)', pct(s?.rho)], ['δ (1h)', signedPct(s?.delta_1h)])
    if (node.dist_key != null) rows.push(['zone share (key)', `${(node.dist_key * 100).toFixed(2)}%`])
  }
  if (node.kind === 'grid') {
    rows.push(['through-flow T', mw(s?.t_flow)], ['loading λ', pct(s?.loading)], ['net injection n', `${mw(s?.net_injection)} · ${sign(s?.net_injection)}`])
    if (node.voltage_kv != null) rows.push(['voltage', `${node.voltage_kv} kV`])
  }
  if (node.kind === 'storage') {
    rows.push(['power P', mw(s?.p_store)], ['SoC', pct(s?.soc)], ['P_max / E_max', `${fmtMw(node.capacity_mw)} / ${fmtMw(node.energy_mwh, 'MWh')}`])
  }
  rows.push(['data quality', s?.quality ?? 'missing', (s?.quality ?? 'missing') !== 'measured'])
  return <Item rows={rows} />
}

export function ClusterVitals({ c, p }: { c: ClusterNode; p?: ClusterState }) {
  return (
    <Item
      heading="aggregate (Σ members)"
      rows={[
        ['net injection n_c', mw(p?.net_injection)],
        ['Σ P_gen', mw(p?.p_gen)],
        ['Σ D', mw(p?.demand)],
        ['nameplate src / storage', `${fmtMw(c.capacity_mw['source'])} / ${fmtMw(c.capacity_mw['storage'])}`],
        ['members', `${c.counts.grid} grid · ${c.counts.source} src · ${c.counts.consumption} load · ${c.counts.storage} storage`],
      ]}
    />
  )
}

/** Zone totals, the raw residual r = Σgen − Σload − X and the reconciled state (MVP.md §3.4). */
export function ZoneBalance({ z }: { z?: ZoneState }) {
  const held = z?.demand_age_min != null && z.demand_age_min >= 60 ? ` · held ${Math.round(z.demand_age_min)} min` : ''
  const r = z?.reconciled
  return (
    <>
      <Item
        heading="raw measurements"
        rows={[
          ['Σ gen', mw(z?.p_gen)],
          ['Σ load', `${mw(z?.demand)}${held}`, held !== ''],
          ['net export X', mw(z?.exchange)],
          ['residual r', z?.residual == null ? '—' : `${mw(z.residual)} · ${pct(z.residual_hat)} of load`, z?.residual == null],
          ['price', eur(z?.price)],
          ['CO₂', z?.co2_intensity == null ? '—' : `${Math.round(z.co2_intensity * 1000)} g/kWh`],
        ]}
      />
      <Item
        heading="reconciled state n* (weighted projection, Σ = 0)"
        rows={
          r
            ? [
                ['Σ gen*', `${mw(r.p_gen)} · Δ ${signed(sumClassAdjustments(r.adjustments))} MW`],
                ['Σ load*', `${mw(r.demand)} · Δ ${signed(r.adjustments['demand'])} MW`],
                ['net export X*', mw(r.exchange)],
                ['gen* − load* − X*', mw(r.p_gen - r.demand - r.exchange, 3)],
                ['trust w · flow / gen / load', `${weightOf(r.weights, 'flow:')} / ${weightOf(r.weights, 'class:')} / ${weightOf(r.weights, 'demand')}`],
              ]
            : [['state', 'identity cannot be formed (missing gen, load or a corridor flow)', true]]
        }
      />
    </>
  )
}

const signed = (v: number | undefined) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${Math.round(v)}`)
const sumClassAdjustments = (adj: Record<string, number>) =>
  Object.entries(adj)
    .filter(([k]) => k.startsWith('class:'))
    .reduce((a, [, v]) => a + v, 0)
const weightOf = (w: Record<string, number>, prefix: string) => {
  const k = Object.keys(w).find((x) => x.startsWith(prefix))
  return k ? String(w[k]) : '—'
}
