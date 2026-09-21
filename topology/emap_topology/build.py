"""Build artifacts/topology.json.

python -m emap_topology.build            # uses work/ inputs (run sources.py first)
python -m emap_topology.build --fetch    # download pinned inputs if missing
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime

from . import __version__
from .cluster import FINEST, LEVELS, assign_clusters, build_views, check_nested
from .config import ARTIFACTS, PARAMS, ZONES
from .graph import Graph, build_graph
from .io import read_bus_names, read_osm, read_plants, read_zone_polygons
from .sources import fetch_all, provenance


def _clean(v):
    return None if isinstance(v, float) and math.isnan(v) else v


def build() -> dict:
    osm, plants, polys, names = read_osm(), read_plants(), read_zone_polygons(), read_bus_names()
    g: Graph = build_graph(osm, plants, polys, names, PARAMS)
    assign_clusters(g, PARAMS)
    check_nested(g)
    views = build_views(g)
    nodes = [{**n, "cluster": {str(k): v for k, v in n["cluster"].items()}} for n in g.nodes]
    for n in nodes:
        for k in ("capacity_mw", "co2_intensity", "energy_mwh"):
            if k in n:
                n[k] = _clean(n[k])
    edges = [
        {**e, "rating_mw": _clean(e["rating_mw"]), "length_km": _clean(e["length_km"])}
        for e in g.edges
    ]
    return {
        "meta": {
            "builder": f"emap_topology {__version__}",
            "built_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "params": {
                "plant_min_mw": PARAMS.plant_min_mw,
                "storage_min_mw": PARAMS.storage_min_mw,
                "as_of_year": PARAMS.as_of_year,
                "dk_clusters": PARAMS.dk_clusters,
                "kmeans_seed": PARAMS.kmeans_seed,
            },
            "sources": provenance(),
            "levels": LEVELS,
            "finest_level": FINEST,
        },
        "zones": [
            {
                "id": z.id,
                "name": z.name,
                "country": z.country,
                "detail": z.detail,
                "lat": g.zone_anchor[z.id][0],
                "lon": g.zone_anchor[z.id][1],
            }
            for z in ZONES.values()
        ],
        "nodes": nodes,
        "edges": edges,
        "edge_members": g.edge_members,
        "views": {str(k): v for k, v in views.items()},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="download pinned inputs if missing")
    ap.add_argument("--out", default=str(ARTIFACTS / "topology.json"))
    args = ap.parse_args()
    if args.fetch:
        fetch_all()
    doc = build()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=None, separators=(",", ":"))
        f.write("\n")
    kinds = {}
    for n in doc["nodes"]:
        kinds[n["kind"]] = kinds.get(n["kind"], 0) + 1
    print(f"wrote {args.out}")
    print(f"nodes={len(doc['nodes'])} {kinds} edges={len(doc['edges'])}")
    for lvl, v in doc["views"].items():
        print(f"level {lvl}: {len(v['nodes'])} cluster nodes, {len(v['edges'])} bundled edges")


if __name__ == "__main__":
    main()
