"""Invariants of the committed artifact (skipped when it has not been built)."""

from __future__ import annotations

import json
from collections import defaultdict

import pytest

from emap_topology.config import ARTIFACTS

ART = ARTIFACTS / "topology.json"
pytestmark = pytest.mark.skipif(not ART.exists(), reason="artifacts/topology.json not built")


@pytest.fixture(scope="module")
def doc():
    return json.loads(ART.read_text(encoding="utf-8"))


def test_ids_unique_and_edges_resolve(doc):
    ids = [n["id"] for n in doc["nodes"]]
    assert len(ids) == len(set(ids))
    eids = [e["id"] for e in doc["edges"]]
    assert len(eids) == len(set(eids))
    known = set(ids)
    for e in doc["edges"]:
        assert e["from"] in known and e["to"] in known, e["id"]
        assert e["from"] != e["to"], e["id"]


def test_all_four_kinds_present_in_dk_and_overall(doc):
    kinds = defaultdict(int)
    dk = defaultdict(int)
    for n in doc["nodes"]:
        kinds[n["kind"]] += 1
        if n["zone"] in ("DK1", "DK2"):
            dk[n["kind"]] += 1
    for k in ("source", "grid", "consumption", "storage"):
        assert kinds[k] > 0 and dk[k] > 0, k


def test_dk_zones_only_joined_by_great_belt_interconnector(doc):
    nodes = {n["id"]: n for n in doc["nodes"]}
    cross = [
        e
        for e in doc["edges"]
        if nodes[e["from"]]["kind"] == nodes[e["to"]]["kind"] == "grid"
        and {nodes[e["from"]]["zone"], nodes[e["to"]]["zone"]} == {"DK1", "DK2"}
    ]
    assert len(cross) == 1 and cross[0]["kind"] == "interconnector"
    assert cross[0]["rating_mw"] == 600.0  # Great Belt Power Link


def test_each_dk_zone_ac_grid_is_one_component(doc):
    nodes = {n["id"]: n for n in doc["nodes"]}
    adj = defaultdict(set)
    for e in doc["edges"]:
        a, b = nodes[e["from"]], nodes[e["to"]]
        if a["kind"] == b["kind"] == "grid" and a["zone"] == b["zone"] and e["kind"] == "ac_line":
            adj[a["id"]].add(b["id"])
            adj[b["id"]].add(a["id"])
    for zone in ("DK1", "DK2"):
        ids = [n["id"] for n in doc["nodes"] if n["kind"] == "grid" and n["zone"] == zone]
        seen, stack = set(), [ids[0]]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            stack.extend(adj[x] - seen)
        assert seen == set(ids), f"{zone} AC network is not connected"


def test_satellites_hang_off_exactly_one_grid_node(doc):
    nodes = {n["id"]: n for n in doc["nodes"]}
    deg = defaultdict(int)
    for e in doc["edges"]:
        for end in (e["from"], e["to"]):
            other = e["to"] if end == e["from"] else e["from"]
            if nodes[end]["kind"] != "grid" and nodes[other]["kind"] == "grid":
                deg[end] += 1
    for n in doc["nodes"]:
        if n["kind"] != "grid":
            assert deg[n["id"]] == 1, n["id"]


def test_cluster_levels_nested_and_views_consistent(doc):
    for fine, coarse in (("2", "1"), ("1", "0")):
        parent = {}
        for n in doc["nodes"]:
            c, p = n["cluster"][fine], n["cluster"][coarse]
            assert parent.setdefault(c, p) == p
    ids = sorted(n["id"] for n in doc["nodes"])
    rating = {e["id"]: e["rating_mw"] for e in doc["edges"]}
    for view in doc["views"].values():
        assert sorted(m for c in view["nodes"] for m in c["members"]) == ids
        for be in view["edges"]:
            s = sum(rating[m] or 0 for m in be["members"])
            assert be["rating_mw"] == pytest.approx(s, abs=1e-6), be["id"]
    assert len(doc["views"]["0"]["nodes"]) == len(doc["zones"])


def test_positions_within_region_frame(doc):
    for n in doc["nodes"]:
        assert -5 <= n["lon"] <= 32 and 48 <= n["lat"] <= 72, n["id"]


def test_provenance_pinned(doc):
    src = {s["dataset"]: s for s in doc["meta"]["sources"]}
    assert src["pypsa-eur osm-prebuilt buses"]["version"] == "0.7"
    assert src["powerplantmatching powerplants.csv"]["version"] == "0.8.1"
    assert all(len(s["sha256"]) == 64 for s in src.values())


def test_distribution_keys_sum_to_one_per_zone(doc):
    """Phase 2 bus->zone rule: demand keys on load nodes partition each zone's load."""
    by_zone = defaultdict(float)
    dg = defaultdict(float)
    for n in doc["nodes"]:
        if n["kind"] == "consumption":
            assert n.get("dist_key") is not None, n["id"]
            by_zone[n["zone"]] += n["dist_key"]
        if n["id"].startswith("dg:"):
            dg[n["zone"]] += n["dist_key"]
    for zone, total in by_zone.items():
        assert total == pytest.approx(1.0, abs=1e-4), zone
    assert dg["DK1"] == pytest.approx(1.0, abs=1e-4) and dg["DK2"] == pytest.approx(1.0, abs=1e-4)


def test_every_dk_bus_has_load_and_dg_satellites(doc):
    ids = {n["id"] for n in doc["nodes"]}
    for n in doc["nodes"]:
        if n["kind"] == "grid" and n["zone"] in ("DK1", "DK2"):
            bus = n["id"].removeprefix("bus:")
            assert f"load:{bus}" in ids and f"dg:{bus}" in ids
    # Copenhagen-area buses carry the largest DK2 keys; the biggest single key is < 30 %
    keys = [n["dist_key"] for n in doc["nodes"] if n["kind"] == "consumption" and n["zone"] == "DK2"]
    assert 0.1 < max(keys) < 0.3
