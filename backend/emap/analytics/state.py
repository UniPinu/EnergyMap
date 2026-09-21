"""Stage ④ STATE COMPUTE: canonical samples -> per-node state vectors (MVP.md §3.2) at time t.

Only DK zones are live in Phase 2. For each zone we take the latest canonical sample at or
before t for every quantity (a value held beyond its native step is flagged `estimated`; beyond
a horizon it is `missing`), apply the distribution rule to plants / dg / loads, derive δ(1h)
from the same computation at t - 1h, and report zone totals with the raw residual
r = Σgen − Σload − X (L = 0 until Phase 3 formalizes losses and reconciliation).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import duckdb

from emap.analytics.distribution import (
    CLASS_IDS,
    ZonePlan,
    distribute_demand,
    distribute_generation,
    plan_zone,
)
from emap.analytics.models import ClusterState, EdgeState, NodeState, State, ZoneState
from emap.analytics.reconcile_zone import reconcile_zone
from emap.normalize.energinet import class_entity, corridor_map
from emap.normalize.grid import floor_to_grid
from emap.schema import Quality
from emap.topology import Topology

DK_ZONES = ("DK1", "DK2")
# Natives are already expanded onto the 5-min grid, so a sample is fresh only when it exists at
# t itself; anything older is a held value (`estimated`) until the horizon, then `missing`.
HORIZON = {"p_gen": 60, "flow": 60, "co2_intensity": 60, "price": 60 * 26, "demand": 60 * 6}


def latest(
    cur: duckdb.DuckDBPyConnection, entity_id: str, quantity: str, t: datetime
) -> tuple[float | None, Quality, float | None]:
    """(value, quality, age_minutes) of the latest sample at or before t."""
    row = cur.execute(
        "SELECT value, t_utc, quality FROM samples WHERE entity_id = ? AND quantity = ? "
        "AND t_utc <= ? AND value IS NOT NULL ORDER BY t_utc DESC LIMIT 1",
        [entity_id, quantity, t],
    ).fetchone()
    if row is None:
        return None, "missing", None
    value, t_sample, q = row
    age = (t - t_sample).total_seconds() / 60.0
    if age > HORIZON[quantity]:
        return None, "missing", age
    if age > 0:
        return value, "estimated", age
    return value, q, age


class ZoneRead:
    """Everything the store knows about one zone at instant t."""

    def __init__(self, cur, zone: str, t: datetime, corridor_edges: list[str]) -> None:
        self.zone, self.t = zone, t
        self.demand, self.demand_q, self.demand_age = latest(cur, zone, "demand", t)
        self.p_gen, self.p_gen_q, _ = latest(cur, zone, "p_gen", t)
        self.price, _, _ = latest(cur, zone, "price", t)
        self.co2, _, _ = latest(cur, zone, "co2_intensity", t)
        self.classes: dict[str, float] = {}
        for c in CLASS_IDS:
            v, _q, _ = latest(cur, class_entity(zone, c), "p_gen", t)
            if v is not None:
                self.classes[c] = v
        self.flows: dict[str, tuple[float | None, Quality]] = {}
        for edge_id in corridor_edges:
            v, q, _ = latest(cur, edge_id, "flow", t)
            self.flows[edge_id] = (v, q)

    @property
    def live(self) -> bool:
        return self.p_gen is not None or self.demand is not None


def _delta(now: float | None, prev: float | None) -> float | None:
    """δ(t; 1h) = (x(t) - x(t-1h)) / x(t-1h); undefined below a 1 kW base."""
    if now is None or prev is None or prev < 1e-3:
        return None
    return (now - prev) / prev


def _sign(x: float) -> int:
    return 1 if x > 0 else -1 if x < 0 else 0


def latest_snapshot_time(cur: duckdb.DuckDBPyConnection) -> datetime | None:
    """Most recent grid instant with 5-min DK production data (the freshest complete slot)."""
    row = cur.execute(
        "SELECT max(t_utc) FROM samples WHERE quantity = 'p_gen' AND entity_id IN ('DK1', 'DK2') "
        "AND t_utc <= ?",
        [datetime.now(UTC)],
    ).fetchone()
    return row[0] if row and row[0] is not None else None


def compute_state(
    topology: Topology, cur: duckdb.DuckDBPyConnection, t: datetime | None = None
) -> State:
    if t is None:
        # default = latest complete 5-min slot, so fresh measurements are not flagged as held
        t = latest_snapshot_time(cur) or datetime.now(UTC)
    t = floor_to_grid(t.astimezone(UTC))
    t_prev = t - timedelta(hours=1)
    nodes_by_id = topology.node_index()
    edges_by_id = {e.id: e for e in topology.edges}
    corridors = corridor_map(topology)
    edges_of_zone: dict[str, list[str]] = {z: [] for z in DK_ZONES}
    for (dk, _nb), (edge_id, _orientation) in corridors.items():
        edges_of_zone[dk].append(edge_id)
    plans: dict[str, ZonePlan] = {z: plan_zone(z, topology.nodes) for z in DK_ZONES}

    node_states: dict[str, NodeState] = {}
    edge_states: dict[str, EdgeState] = {}
    zone_states: dict[str, ZoneState] = {}
    attached: dict[str, list[str]] = {}  # grid node -> satellites (for n_g)
    incident: dict[str, list[str]] = {}  # grid node -> edge ids
    for e in topology.edges:
        a, b = nodes_by_id[e.from_], nodes_by_id[e.to]
        if a.kind == "grid" and b.kind != "grid":
            attached.setdefault(a.id, []).append(b.id)
        elif b.kind == "grid" and a.kind != "grid":
            attached.setdefault(b.id, []).append(a.id)
        incident.setdefault(e.from_, []).append(e.id)
        incident.setdefault(e.to, []).append(e.id)

    for zone in DK_ZONES:
        now = ZoneRead(cur, zone, t, edges_of_zone[zone])
        prev = ZoneRead(cur, zone, t_prev, edges_of_zone[zone])
        plan = plans[zone]
        gen_q: Quality = "measured" if now.classes else "missing"
        # Reconcile the zone identity (gen − load − X = 0); the balanced state drives the faces,
        # the raw residual stays visible. Both instants are reconciled so δ(1h) compares alike.
        rec = reconcile_zone(
            zone, now.classes, gen_q, now.demand, now.demand_q, now.flows, edges_by_id, nodes_by_id
        )
        rec_prev = reconcile_zone(
            zone,
            prev.classes,
            "measured" if prev.classes else "missing",
            prev.demand,
            prev.demand_q,
            prev.flows,
            edges_by_id,
            nodes_by_id,
        )
        classes_now = rec.by_class if rec else now.classes
        classes_prev = rec_prev.by_class if rec_prev else prev.classes
        demand_now = rec.demand if rec else now.demand
        demand_prev = rec_prev.demand if rec_prev else prev.demand
        gen_now = distribute_generation(plan, classes_now)
        gen_prev = distribute_generation(plan, classes_prev)
        dem_now = distribute_demand(plan, demand_now) if demand_now is not None else {}
        dem_prev = distribute_demand(plan, demand_prev) if demand_prev is not None else {}
        node_q: Quality = "estimated" if rec else gen_q
        for nid, p in gen_now.items():
            n = nodes_by_id[nid]
            cap = n.capacity_mw
            node_states[nid] = NodeState(
                id=nid, kind=n.kind, quality=node_q, p_gen=p,
                u=(p / cap if cap else None), delta_1h=_delta(p, gen_prev.get(nid)),
            )  # fmt: skip
        for nid, d in dem_now.items():
            n = nodes_by_id[nid]
            node_states[nid] = NodeState(
                id=nid, kind=n.kind, quality="estimated" if rec else now.demand_q, demand=d,
                delta_1h=_delta(d, dem_prev.get(nid)),
            )  # fmt: skip
        exchange = 0.0
        any_flow = False
        for edge_id, (f, q) in now.flows.items():
            edge = edges_by_id[edge_id]
            f_rec = rec.flows.get(edge_id) if rec else None
            shown = f_rec if f_rec is not None else f
            loading = abs(shown) / edge.rating_mw if shown is not None and edge.rating_mw else None
            edge_states[edge_id] = EdgeState(
                id=edge_id, flow=shown, flow_raw=f, quality=q, loading=loading
            )
            if f is not None:
                # flow is signed from->to; leaving this zone counts as export
                exchange += f if nodes_by_id[edge.from_].zone == zone else -f
                any_flow = True
        residual = r_hat = None
        if now.p_gen is not None and now.demand is not None and any_flow:
            residual = now.p_gen - now.demand - exchange
            r_hat = residual / now.demand if now.demand else None
        zone_states[zone] = ZoneState(
            id=zone, live=now.live, p_gen=now.p_gen, by_class=now.classes, demand=now.demand,
            demand_quality=now.demand_q, demand_age_min=now.demand_age,
            exchange=exchange if any_flow else None, price=now.price, co2_intensity=now.co2,
            residual=residual, residual_hat=r_hat, reconciled=rec,
        )  # fmt: skip

    # grid buses: net injection of attached satellites; through-flow from known corridors only
    for n in topology.nodes:
        if n.kind != "grid" or n.zone not in DK_ZONES:
            continue
        inj, known = 0.0, False
        for sid in attached.get(n.id, []):
            s = node_states.get(sid)
            if s is None:
                continue
            if s.p_gen is not None:
                inj, known = inj + s.p_gen, True
            if s.demand is not None:
                inj, known = inj - s.demand, True
        flows = [
            abs(es.flow)
            for eid in incident.get(n.id, [])
            if (es := edge_states.get(eid)) is not None and es.flow is not None
        ]
        node_states[n.id] = NodeState(
            id=n.id, kind="grid", quality="estimated" if known else "missing",
            net_injection=inj if known else None, net_sign=_sign(inj) if known else None,
            t_flow=(0.5 * sum(flows) if flows else None),
        )  # fmt: skip

    # cluster aggregation (balance-preserving sums, MVP.md §4.1) for the coarse levels
    clusters: dict[str, dict[str, ClusterState]] = {}
    for level, view in topology.views.items():
        clusters[level] = {}
        for c in view.nodes:
            p = d = 0.0
            has_p = has_d = False
            for mid in c.members:
                s = node_states.get(mid)
                if s is None:
                    continue
                if s.p_gen is not None:
                    p, has_p = p + s.p_gen, True
                if s.demand is not None:
                    d, has_d = d + s.demand, True
            clusters[level][c.id] = ClusterState(
                id=c.id, level=int(level), p_gen=p if has_p else None, demand=d if has_d else None,
                net_injection=(p - d) if (has_p and has_d) else None,
                quality="estimated" if (has_p or has_d) else "missing",
            )  # fmt: skip

    return State(
        t_utc=t, computed_at_utc=datetime.now(UTC), nodes=node_states, edges=edge_states,
        zones=zone_states, clusters=clusters,
    )  # fmt: skip
