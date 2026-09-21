"""Cluster hierarchy Π₀ ≼ Π₁ ≼ Π₂ (MVP.md §4.1) and the per-level *structural* views.

  Π₀  zones            one super-node per bidding zone
  Π₁  DK bus clusters  PyPSA's k-means busmap within each DK zone (neighbours stay one node)
  Π₂  entities         every node is its own cluster

Membership is nested by construction: Π₁ clusters are formed inside a zone, and every non-grid
entity inherits the cluster of the grid node it hangs off (`Graph.bus_of`). Aggregation of
*state* over members (n_c = Σ n_i …) is done by the backend at runtime; here we precompute what
is static: membership, positions, member counts/capacities and the bundled inter-cluster edges
F_{c→c'} = Σ F_e (structure and Σ rating only).
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd
import pypsa
from pypsa.clustering.spatial import busmap_by_kmeans

from .config import PARAMS, ZONES, BuildParams
from .graph import Graph

LEVELS = [
    {"level": 0, "name": "zones", "description": "bidding-zone super-nodes"},
    {"level": 1, "name": "dk-clusters", "description": "k-means bus clusters inside DK1/DK2"},
    {"level": 2, "name": "entities", "description": "buses, plants, loads, storage"},
]
FINEST = 2


def _kmeans_busmap(grid: pd.DataFrame, weights: pd.Series, k: int, seed: int) -> pd.Series:
    """Cluster ids 0..k-1 for the grid nodes of one zone using PyPSA's k-means busmap."""
    if len(grid) <= k:
        return pd.Series(range(len(grid)), index=grid.index)
    n = pypsa.Network()
    n.add("Bus", grid.index, x=grid.lon.to_numpy(), y=grid.lat.to_numpy())
    bm = busmap_by_kmeans(n, weights.reindex(grid.index).fillna(1), k, random_state=seed, n_init=10)
    return bm.astype(int)


def assign_clusters(g: Graph, params: BuildParams = PARAMS) -> None:
    """Fill `node['cluster'] = {0: zone, 1: dk-cluster-or-zone, 2: own id}` for every node."""
    nodes = pd.DataFrame(g.nodes).set_index("id")
    # weight grid nodes by attached source capacity so plant-dense areas get more clusters
    attached = defaultdict(float)
    for n in g.nodes:
        if n["kind"] == "source" and n["capacity_mw"]:
            attached[g.bus_of[n["id"]]] += n["capacity_mw"]
    level1: dict[str, str] = {}
    for zid, k in params.dk_clusters.items():
        if k <= 1:
            continue  # a single cluster is the zone itself
        grid = nodes[(nodes.kind == "grid") & (nodes.zone == zid)]
        w = pd.Series({b: 1 + attached[b] / 100.0 for b in grid.index})
        bm = _kmeans_busmap(grid, w, k, params.kmeans_seed)
        # stable, geography-ordered labels: renumber clusters west→east by centroid longitude
        cx = grid.lon.groupby(bm).mean().sort_values()
        rank = {old: i for i, old in enumerate(cx.index)}
        for b, c in bm.items():
            level1[b] = f"{zid}/c{rank[c]}"
    for n in g.nodes:
        anchor = g.bus_of[n["id"]]
        zone = n["zone"]
        n["cluster"] = {0: zone, 1: level1.get(anchor, zone), 2: n["id"]}


def build_views(g: Graph) -> dict[int, dict]:
    """Per coarse level: cluster nodes (position = member centroid, or the zone anchor at Π₀)
    and bundled edges between distinct clusters."""
    views: dict[int, dict] = {}
    nodes_by_id = {n["id"]: n for n in g.nodes}
    for level in (0, 1):
        members: dict[str, list[str]] = defaultdict(list)
        for n in g.nodes:
            members[n["cluster"][level]].append(n["id"])
        cnodes = []
        for cid, ids in sorted(members.items()):
            ms = [nodes_by_id[i] for i in ids]
            zone = ms[0]["zone"]
            grid = [m for m in ms if m["kind"] == "grid"] or ms
            if "/" in cid:  # DK k-means cluster: position = centroid of member buses
                lat = float(np.mean([m["lat"] for m in grid]))
                lon = float(np.mean([m["lon"] for m in grid]))
                name = f"{zone} cluster {cid.split('/c')[-1]}"
            else:  # whole zone
                lat, lon = g.zone_anchor[zone]
                name = f"{ZONES[zone].name} ({zone})"
            counts = {
                k: sum(m["kind"] == k for m in ms)
                for k in ("source", "grid", "consumption", "storage")
            }
            cap = {
                k: round(sum(m["capacity_mw"] or 0 for m in ms if m["kind"] == k), 3)
                for k in ("source", "storage")
            }
            cnodes.append(
                {
                    "id": cid,
                    "level": level,
                    "zone": zone,
                    "name": name,
                    "lat": lat,
                    "lon": lon,
                    "members": ids,
                    "counts": counts,
                    "capacity_mw": cap,
                }
            )
        bundles: dict[tuple[str, str], dict] = {}
        for e in g.edges:
            a = nodes_by_id[e["from"]]["cluster"][level]
            b = nodes_by_id[e["to"]]["cluster"][level]
            if a == b:
                continue
            key = (a, b) if a <= b else (b, a)
            entry = bundles.setdefault(
                key, {"rating": 0.0, "members": [], "kinds": set(), "nan": False}
            )
            if e["rating_mw"] is None or (
                isinstance(e["rating_mw"], float) and np.isnan(e["rating_mw"])
            ):
                entry["nan"] = True
            else:
                entry["rating"] += e["rating_mw"]
            entry["members"].append(e["id"])
            entry["kinds"].add(e["kind"])
        cedges = []
        za = {c["id"]: c["zone"] for c in cnodes}
        for (a, b), en in sorted(bundles.items()):
            if za[a] != za[b]:
                kind = "interconnector"
            elif en["kinds"] == {"hvdc_link"}:
                kind = "hvdc_link"
            else:
                kind = "ac_line"
            cedges.append(
                {
                    "id": f"bundle:{level}:{a}--{b}",
                    "from": a,
                    "to": b,
                    "kind": kind,
                    "rating_mw": round(en["rating"], 3),
                    "length_km": None,
                    "members": en["members"],
                }
            )
        views[level] = {"nodes": cnodes, "edges": cedges}
    return views


def check_nested(g: Graph) -> None:
    """Π₀ ≼ Π₁ ≼ Π₂: a cluster at a finer level lies inside exactly one coarser cluster."""
    for fine, coarse in ((2, 1), (1, 0)):
        parent: dict[str, str] = {}
        for n in g.nodes:
            c, p = n["cluster"][fine], n["cluster"][coarse]
            if parent.setdefault(c, p) != p:
                raise AssertionError(f"cluster {c} at level {fine} spans {parent[c]} and {p}")
