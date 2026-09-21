import type { ClusterNode, ClusterState, NodeState, TopoNode, ZoneState } from '@/lib/api'
import { eur, mw, pct, sign, signedPct } from '@/canvas/nodes/format'
import { fmtMw } from '@/canvas/nodes/style'

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between gap-2 font-mono text-xs">
      <span className="text-muted-foreground">{k}</span>
      <span className="truncate">{v}</span>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-0.5">
      <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</h3>
      {children}
    </section>
  )
}

/** The §3.2 state vector of one node, plus its static facts from the topology. */
export function NodeVitals({ node, s }: { node: TopoNode; s?: NodeState }) {
  return (
    <Section title="vitals">
      {node.kind === 'source' && (
        <>
          <Row k="P_gen" v={mw(s?.p_gen, 1)} />
          <Row k="utilization u" v={pct(s?.u)} />
          <Row k="δ (1h)" v={signedPct(s?.delta_1h)} />
          <Row k="nameplate" v={fmtMw(node.capacity_mw)} />
          {node.dist_key != null && <Row k="zone share (key)" v={`${(node.dist_key * 100).toFixed(2)}%`} />}
          {node.co2_intensity != null && <Row k="CO₂ intensity" v={`${node.co2_intensity} t/MWh`} />}
        </>
      )}
      {node.kind === 'consumption' && (
        <>
          <Row k="demand D" v={mw(s?.demand, 1)} />
          <Row k="ρ (vs normal)" v={pct(s?.rho)} />
          <Row k="δ (1h)" v={signedPct(s?.delta_1h)} />
          {node.dist_key != null && <Row k="zone share (key)" v={`${(node.dist_key * 100).toFixed(2)}%`} />}
        </>
      )}
      {node.kind === 'grid' && (
        <>
          <Row k="through-flow T" v={mw(s?.t_flow)} />
          <Row k="loading λ" v={pct(s?.loading)} />
          <Row k="net injection n" v={`${mw(s?.net_injection)} (${sign(s?.net_injection)})`} />
          {node.voltage_kv != null && <Row k="voltage" v={`${node.voltage_kv} kV`} />}
        </>
      )}
      {node.kind === 'storage' && (
        <>
          <Row k="power P" v={mw(s?.p_store)} />
          <Row k="SoC" v={pct(s?.soc)} />
          <Row k="P_max / E_max" v={`${fmtMw(node.capacity_mw)} / ${fmtMw(node.energy_mwh, 'MWh')}`} />
        </>
      )}
      <Row k="data quality" v={s?.quality ?? 'missing'} />
    </Section>
  )
}

export function ClusterVitals({ c, p }: { c: ClusterNode; p?: ClusterState }) {
  return (
    <Section title="aggregate (Σ members)">
      <Row k="net injection n_c" v={mw(p?.net_injection)} />
      <Row k="Σ P_gen" v={mw(p?.p_gen)} />
      <Row k="Σ D" v={mw(p?.demand)} />
      <Row k="nameplate src / storage" v={`${fmtMw(c.capacity_mw['source'])} / ${fmtMw(c.capacity_mw['storage'])}`} />
      <Row k="members" v={`${c.counts.grid} grid · ${c.counts.source} src · ${c.counts.consumption} load · ${c.counts.storage} storage`} />
    </Section>
  )
}

/** Zone totals and the raw residual r = Σgen − Σload − X (MVP.md §3.4) — never hidden. */
export function ZoneBalance({ z, zone }: { z?: ZoneState; zone: string }) {
  const held = z?.demand_age_min != null && z.demand_age_min >= 60 ? ` (held ${Math.round(z.demand_age_min)} min)` : ''
  return (
    <Section title={`zone ${zone} balance (raw)`}>
      <Row k="Σ gen" v={mw(z?.p_gen)} />
      <Row k="Σ load" v={`${mw(z?.demand)}${held}`} />
      <Row k="net export X" v={mw(z?.exchange)} />
      <Row k="residual r" v={z?.residual == null ? '—' : `${mw(z.residual)} (${pct(z.residual_hat)} of load)`} />
      <Row k="price" v={eur(z?.price)} />
      <Row k="CO₂" v={z?.co2_intensity == null ? '—' : `${Math.round(z.co2_intensity * 1000)} g/kWh`} />
    </Section>
  )
}
