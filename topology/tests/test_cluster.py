"""Hierarchy nestedness and balance-preserving edge bundling on a hand-built toy graph."""

from __future__ import annotations

import pytest

from emap_topology.cluster import assign_clusters, build_views, check_nested
from emap_topology.config import BuildParams
from emap_topology.graph import Graph


def toy() -> Graph:
    """DK1: 4 buses in two spatial groups (west pair, east pair), one plant, one load each.
    DK2: 1 bus. NO2: hub. Edges: west-west line, east-east line, west-east line (DK1 internal),
    DK1 east -> DK2 (Great Belt), DK1 west -> NO2 hub, plant/load connections."""
    g = Graph()

    def node(id, kind, zone, lat, lon, cap=None):
        g.add_node(
            id=id,
            kind=kind,
            name=id,
            zone=zone,
            lat=lat,
            lon=lon,
            capacity_mw=cap,
            fuel=None,
            co2_intensity=None,
            cluster={},
        )

    for b, lon in (("bus:w1", 8.0), ("bus:w2", 8.2), ("bus:e1", 10.0), ("bus:e2", 10.2)):
        node(b, "grid", "DK1", 56.0, lon)
        g.bus_of[b] = b
    node("bus:z", "grid", "DK2", 55.5, 12.0)
    g.bus_of["bus:z"] = "bus:z"
    node("hub:NO2", "grid", "NO2", 58.5, 8.0)
    g.bus_of["hub:NO2"] = "hub:NO2"
    node("plant:p1", "source", "DK1", 56.1, 8.0, cap=400.0)
    g.bus_of["plant:p1"] = "bus:w1"
    node("load:e1", "consumption", "DK1", 55.9, 10.0)
    g.bus_of["load:e1"] = "bus:e1"
    g.zone_anchor = {"DK1": (56.0, 9.0), "DK2": (55.5, 12.0), "NO2": (58.5, 8.0)}

    g.add_edge("line:ww", "bus:w1", "bus:w2", "ac_line", 1000.0, 10.0)
    g.add_edge("line:ee", "bus:e1", "bus:e2", "ac_line", 1000.0, 10.0)
    g.add_edge("line:we", "bus:w2", "bus:e1", "ac_line", 1500.0, 100.0)
    g.add_edge("link:gb", "bus:e2", "bus:z", "interconnector", 600.0, 50.0)
    g.add_edge("ic:bus:w1--hub:NO2", "bus:w1", "hub:NO2", "interconnector", 1640.0)
    g.add_edge("conn:p1", "plant:p1", "bus:w1", "ac_line", 400.0, 5.0)
    g.add_edge("feed:e1", "bus:e1", "load:e1", "ac_line", None)
    return g


@pytest.fixture
def g() -> Graph:
    graph = toy()
    assign_clusters(graph, BuildParams(dk_clusters={"DK1": 2, "DK2": 1}, kmeans_seed=0))
    return graph


def test_levels_are_nested_and_complete(g: Graph):
    check_nested(g)
    for n in g.nodes:
        assert set(n["cluster"]) == {0, 1, 2}
        assert n["cluster"][0] == n["zone"]
        assert n["cluster"][2] == n["id"]


def test_kmeans_splits_dk1_into_west_and_east(g: Graph):
    c = {n["id"]: n["cluster"][1] for n in g.nodes}
    assert c["bus:w1"] == c["bus:w2"] != c["bus:e1"] == c["bus:e2"]
    assert {c["bus:w1"], c["bus:e1"]} == {"DK1/c0", "DK1/c1"}
    assert c["bus:w1"] == "DK1/c0"  # labels ordered west -> east
    # satellites inherit the cluster of the bus they hang off
    assert c["plant:p1"] == c["bus:w1"] and c["load:e1"] == c["bus:e1"]
    # neighbours are one cluster at every level
    assert c["hub:NO2"] == "NO2" and c["bus:z"] == "DK2"


def test_views_partition_nodes_and_bundle_edges(g: Graph):
    views = build_views(g)
    ids = {n["id"] for n in g.nodes}
    for level, v in views.items():
        members = [m for c in v["nodes"] for m in c["members"]]
        assert sorted(members) == sorted(ids), f"level {level} members must partition V"
    v0 = {c["id"]: c for c in views[0]["nodes"]}
    assert v0["DK1"]["counts"] == {"source": 1, "grid": 4, "consumption": 1, "storage": 0}
    assert v0["DK1"]["capacity_mw"]["source"] == 400.0
    e0 = {(e["from"], e["to"]): e for e in views[0]["edges"]}
    # internal DK1 edges vanish; cross-zone corridors survive with summed ratings
    assert set(e0) == {("DK1", "DK2"), ("DK1", "NO2")}
    assert (
        e0[("DK1", "DK2")]["rating_mw"] == 600.0 and e0[("DK1", "DK2")]["kind"] == "interconnector"
    )
    assert e0[("DK1", "NO2")]["members"] == ["ic:bus:w1--hub:NO2"]
    e1 = {(e["from"], e["to"]): e for e in views[1]["edges"]}
    # the west<->east line becomes an intra-zone ac_line bundle between the two DK1 clusters
    assert e1[("DK1/c0", "DK1/c1")]["kind"] == "ac_line"
    assert e1[("DK1/c0", "DK1/c1")]["rating_mw"] == 1500.0
    assert e1[("DK1/c1", "DK2")]["kind"] == "interconnector"


def test_bundle_rating_is_sum_of_members(g: Graph):
    g.add_edge("line:we2", "bus:w1", "bus:e2", "ac_line", 700.0, 120.0)
    views = build_views(g)
    e1 = {(e["from"], e["to"]): e for e in views[1]["edges"]}
    b = e1[("DK1/c0", "DK1/c1")]
    assert b["rating_mw"] == 2200.0 and sorted(b["members"]) == ["line:we", "line:we2"]


def test_cluster_positions_are_member_centroids(g: Graph):
    v1 = {c["id"]: c for c in build_views(g)[1]["nodes"]}
    assert v1["DK1/c0"]["lon"] == pytest.approx(8.1)
    assert v1["DK1/c1"]["lon"] == pytest.approx(10.1)
    v0 = {c["id"]: c for c in build_views(g)[0]["nodes"]}
    assert (v0["DK1"]["lat"], v0["DK1"]["lon"]) == (56.0, 9.0)  # zone anchor at Π₀
