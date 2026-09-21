"""Distribution rule: conservation, capping, remainder routing, key-proportional demand."""

from __future__ import annotations

import pytest

from emap.analytics.distribution import (
    class_of,
    distribute_demand,
    distribute_generation,
    plan_zone,
)
from emap.schema import Node


def _n(id, kind, zone="DK1", **kw):
    base = dict(name=id, lat=56.0, lon=9.0, cluster={})
    base.update(kw)
    return Node(id=id, kind=kind, zone=zone, **base)


NODES = [
    _n("plant:a", "source", fuel="wind_offshore", capacity_mw=400.0),
    _n("plant:b", "source", fuel="wind_offshore", capacity_mw=100.0),
    _n("plant:c", "source", fuel="coal", capacity_mw=350.0),  # thermal_ge100
    _n("plant:d", "source", fuel="gas", capacity_mw=60.0),  # thermal_lt100
    _n("dg:x", "source", fuel="distributed", dist_key=0.75),
    _n("dg:y", "source", fuel="distributed", dist_key=0.25),
    _n("load:x", "consumption", dist_key=0.75),
    _n("load:y", "consumption", dist_key=0.25),
    _n("plant:other", "source", zone="DK2", fuel="solar", capacity_mw=50.0),  # other zone
]


def test_class_mapping():
    by = {n.id: n for n in NODES}
    assert class_of(by["plant:a"]) == "wind_offshore"
    assert class_of(by["plant:c"]) == "thermal_ge100" and class_of(by["plant:d"]) == "thermal_lt100"
    assert class_of(by["dg:x"]) is None and class_of(by["load:x"]) is None


def test_plan_only_takes_the_zone():
    plan = plan_zone("DK1", NODES)
    assert plan.class_capacity == {
        "wind_offshore": 500.0,
        "wind_onshore": 0.0,
        "solar": 0.0,
        "thermal_ge100": 350.0,
        "thermal_lt100": 60.0,
    }
    assert plan.dg_keys == {"dg:x": 0.75, "dg:y": 0.25} and plan.load_keys == {
        "load:x": 0.75,
        "load:y": 0.25,
    }


def test_generation_is_conserved_and_proportional_below_capacity():
    plan = plan_zone("DK1", NODES)
    got = distribute_generation(plan, {"wind_offshore": 250.0})
    assert got["plant:a"] == pytest.approx(200.0) and got["plant:b"] == pytest.approx(50.0)
    assert got["dg:x"] == 0.0 and got["dg:y"] == 0.0  # nothing left over
    assert sum(got.values()) == pytest.approx(250.0)


def test_capping_routes_the_remainder_to_dg_by_key():
    plan = plan_zone("DK1", NODES)
    got = distribute_generation(
        plan, {"wind_offshore": 800.0, "solar": 120.0, "thermal_lt100": 90.0}
    )
    assert got["plant:a"] == 400.0 and got["plant:b"] == 100.0  # at cap (u = 1)
    assert got["plant:d"] == 60.0
    # remainder: (800-500) + 120 (no solar plants) + (90-60) = 450, split 75/25
    assert got["dg:x"] == pytest.approx(337.5) and got["dg:y"] == pytest.approx(112.5)
    assert sum(got.values()) == pytest.approx(800.0 + 120.0 + 90.0)


def test_missing_classes_are_not_zeroed():
    plan = plan_zone("DK1", NODES)
    got = distribute_generation(plan, {"thermal_ge100": 100.0})
    assert "plant:a" not in got and got["plant:c"] == 100.0
    assert distribute_generation(plan, {}) == {}


def test_demand_split_by_key_is_conserved():
    plan = plan_zone("DK1", NODES)
    got = distribute_demand(plan, 2000.0)
    assert got == {"load:x": 1500.0, "load:y": 500.0}
    assert sum(got.values()) == pytest.approx(2000.0)


def test_real_artifact_plans_conserve_totals():
    from emap.config import get_settings
    from emap.topology import load_topology

    topo = load_topology(get_settings().emap_topology_path)
    for zone in ("DK1", "DK2"):
        plan = plan_zone(zone, topo.nodes)
        assert sum(plan.load_keys.values()) == pytest.approx(1.0, abs=1e-4)
        assert sum(plan.dg_keys.values()) == pytest.approx(1.0, abs=1e-4)
        totals = {
            "wind_offshore": 1500.0,
            "wind_onshore": 1200.0,
            "solar": 900.0,
            "thermal_ge100": 800.0,
            "thermal_lt100": 500.0,
        }
        got = distribute_generation(plan, totals)
        assert sum(got.values()) == pytest.approx(sum(totals.values()))
        # every plant respects its nameplate
        cap = {nid: c for ps in plan.plants.values() for nid, c in ps}
        assert all(got[nid] <= cap[nid] + 1e-9 for nid in cap)
