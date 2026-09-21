"""compute_state on synthetic samples: distribution, δ(1h), freshness, zone totals, residual."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from emap.analytics.state import compute_state, latest
from emap.config import get_settings
from emap.normalize.energinet import class_entity, corridor_map
from emap.schema import Sample
from emap.store import upsert_samples
from emap.store.db import Store
from emap.topology import load_topology

T = datetime(2026, 9, 21, 17, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def topo():
    return load_topology(get_settings().emap_topology_path)


def _s(entity, quantity, t, value, *, kind="node", unit="MW", res="PT5M", q="measured"):
    return Sample(entity_id=entity, entity_kind=kind, quantity=quantity, t_utc=t, value=value,
                  unit=unit, source="energinet", resolution=res, quality=q)  # fmt: skip


def seed(store: Store, topo) -> dict[str, str]:
    """DK1 at T and T-1h; DK2 left empty. Returns corridor edge ids by neighbour."""
    cm = corridor_map(topo)
    edges = {nb: eid for (dk, nb), (eid, _) in cm.items() if dk == "DK1"}
    rows = []
    for t, scale in ((T - timedelta(hours=1), 0.8), (T, 1.0)):
        classes = {
            "wind_offshore": 1500.0,
            "wind_onshore": 1000.0,
            "solar": 200.0,
            "thermal_ge100": 600.0,
            "thermal_lt100": 400.0,
        }
        for c, v in classes.items():
            rows.append(_s(class_entity("DK1", c), "p_gen", t, v * scale))
        rows.append(_s("DK1", "p_gen", t, sum(classes.values()) * scale))
        rows.append(_s("DK1", "demand", t, 2800.0 * scale, res="PT60M"))
        rows.append(_s("DK1", "price", t, 90.0, unit="EUR/MWh", res="PT15M"))
        rows.append(_s("DK1", "co2_intensity", t, 0.06, unit="tCO2/MWh"))
        # exports 900 to DE, imports 400 from NO2 (flow signed DK bus -> hub: export positive)
        rows.append(_s(edges["DE_LU"], "flow", t, 900.0 * scale, kind="edge"))
        rows.append(_s(edges["NO2"], "flow", t, -400.0 * scale, kind="edge"))
        for nb, eid in edges.items():  # the identity needs every corridor: the rest idle
            if nb not in ("DE_LU", "NO2"):
                rows.append(_s(eid, "flow", t, 0.0, kind="edge"))
    with store.cursor() as cur:
        upsert_samples(cur, rows)
    return edges


def test_latest_freshness_flags(store: Store, topo):
    seed(store, topo)
    with store.cursor() as cur:
        assert latest(cur, "DK1", "p_gen", T)[1] == "measured"
        v, q, age = latest(cur, "DK1", "p_gen", T + timedelta(minutes=20))
        assert v == 3700.0 and q == "estimated" and age == 20.0
        assert latest(cur, "DK1", "p_gen", T + timedelta(hours=3))[1] == "missing"
        assert latest(cur, "DK2", "p_gen", T) == (None, "missing", None)
        # hourly demand is expanded onto the grid at ingest, so any positive age is a hold
        assert latest(cur, "DK1", "demand", T + timedelta(minutes=55))[1] == "estimated"
        assert latest(cur, "DK1", "demand", T)[1] == "measured"


def test_state_distributes_and_conserves(store: Store, topo):
    edges = seed(store, topo)
    with store.cursor() as cur:
        st = compute_state(topo, cur, T)
    assert st.t_utc == T
    z = st.zones["DK1"]
    assert z.live and z.p_gen == 3700.0 and z.demand == 2800.0
    assert z.exchange == pytest.approx(900.0 - 400.0)  # net export
    assert z.residual == pytest.approx(3700.0 - 2800.0 - 500.0)
    assert z.residual_hat == pytest.approx(400.0 / 2800.0)
    assert z.price == 90.0 and z.co2_intensity == 0.06
    assert not st.zones["DK2"].live and st.zones["DK2"].residual is None
    # the faces carry the *reconciled* state: the zone identity closes exactly on it
    rec = z.reconciled
    assert rec is not None
    assert rec.p_gen - rec.demand - rec.exchange == pytest.approx(0.0, abs=1e-6)
    # least-trusted term (held demand) moves most, metered flows least; raw totals untouched
    assert abs(rec.adjustments["demand"]) > abs(rec.adjustments["class:wind_offshore"])
    assert all(
        abs(rec.adjustments[k]) < abs(rec.adjustments["demand"])
        for k in rec.adjustments
        if k.startswith("flow:")
    )
    dk1 = [n for n in topo.nodes if n.zone == "DK1"]
    gen = sum(st.nodes[n.id].p_gen or 0.0 for n in dk1 if n.kind == "source" and n.id in st.nodes)
    dem = sum(st.nodes[n.id].demand or 0.0 for n in dk1 if n.kind == "consumption")
    assert gen == pytest.approx(rec.p_gen) and dem == pytest.approx(rec.demand)
    assert gen < 3700.0 and dem > 2800.0  # r > 0 closes by lowering gen and raising load

    # every plant respects nameplate; δ(1h) = +25 % for all distributed quantities (0.8 -> 1.0)
    for n in dk1:
        s = st.nodes.get(n.id)
        if s and s.p_gen is not None and n.capacity_mw:
            assert s.u is not None and s.u <= 1.0 + 1e-9
        if s and s.delta_1h is not None:
            assert s.delta_1h == pytest.approx(0.25)
    # corridor edges carry the signed flows and a loading
    de = next(e for e in topo.edges if e.id == edges["DE_LU"])
    assert st.edges[de.id].flow_raw == 900.0 and st.edges[de.id].flow == pytest.approx(
        rec.flows[de.id]
    )
    assert st.edges[de.id].loading == pytest.approx(rec.flows[de.id] / de.rating_mw)
    assert st.edges[edges["NO2"]].flow_raw == -400.0
    # DK2 nodes have no state at all (never zeros)
    assert all(
        nid not in st.nodes
        for nid in (n.id for n in topo.nodes if n.zone == "DK2" and n.kind != "grid")
    )
    # cluster aggregation reproduces the zone at Π₀
    c = st.clusters["0"]["DK1"]
    # Π₀ cluster sums reproduce the reconciled zone, and n_c = X (KCL closes at the zone)
    assert c.p_gen == pytest.approx(rec.p_gen) and c.demand == pytest.approx(rec.demand)
    assert c.net_injection == pytest.approx(rec.exchange)
    assert st.clusters["0"]["DK2"].quality == "missing"
    assert sum(
        (st.clusters["1"][cid].p_gen or 0.0) for cid in st.clusters["1"] if cid.startswith("DK1/")
    ) == pytest.approx(rec.p_gen)


def test_grid_bus_net_injection_and_corridor_throughflow(store: Store, topo):
    edges = seed(store, topo)
    with store.cursor() as cur:
        st = compute_state(topo, cur, T)
    kasso = next(n for n in topo.nodes if n.name == "Kassø")
    s = st.nodes[kasso.id]
    assert s.net_injection is not None and s.net_sign in (-1, 0, 1)
    de_flow = st.zones["DK1"].reconciled.flows[edges["DE_LU"]]
    assert s.t_flow == pytest.approx(0.5 * abs(de_flow))  # only the DE corridor is known at Kassø
    de_edge = edges["DE_LU"]
    assert de_edge.endswith("hub:DE_LU") and kasso.id in de_edge
