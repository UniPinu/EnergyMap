# topology — service A (offline PyPSA-Eur export)

Builds `artifacts/topology.json`: the canonical Node/Edge graph for DK (bus granularity) and
neighbour bidding zones (super-nodes), with the cluster hierarchy Π₀ ≼ Π₁ ≼ Π₂ and precomputed
per-level structural views. The artifact is **committed**; running the app never needs this
package.

Inputs are exactly what PyPSA-Eur consumes (URLs pinned from its `data/versions.csv`):

| Input | Version | Role |
|---|---|---|
| OSM prebuilt electricity network (`buses/lines/links/converters/transformers.csv`) | 0.7 (ODbL) | grid buses ≥ 220 kV, AC lines, HVDC links |
| powerplantmatching `powerplants.csv` | 0.8.1 | plants → source/storage nodes; neighbour nameplate aggregates |
| entsoe-py bidding-zone GeoJSONs | V0.6.18 | bus/plant → zone (point-in-polygon), zone anchors |
| `data/osm_bus_names.json` | fetched once via Overpass | substation names for DK buses |

## Rebuild

```bash
cd topology
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # Windows; use .venv/bin on Unix
.venv/Scripts/python -m emap_topology.build --fetch               # downloads ~45 MB into work/ once
.venv/Scripts/python -m pytest
```

## Modelling rules (see MVP.md §2.3, §4.1)

- **DK1/DK2** — every AC bus is a `grid` node; one `consumption` node per bus (recipient of the
  zone→bus demand distribution decided in Phase 2); plants ≥ 20 MW and storage ≥ 1 MW become
  `source`/`storage` nodes at their real coordinates, connected to the nearest AC bus of their
  zone; units with `DateOut < 2026` are dropped. DC converter buses are collapsed onto their AC side.
- **Zone assignment** — country → candidate zones → containing polygon → nearest polygon within
  0.75° (offshore farms) → else not modelled (Faroe Islands). Bornholm is forced to DK2 (the
  entsoe-py DK_2 polygon omits it). Verified: the only DK1↔DK2 grid edge is the Great Belt HVDC,
  and each DK zone's AC network is one connected component.
- **Neighbour zones** — one `grid` hub (interconnectors land here) + aggregate `source`,
  `consumption` and (if any) `storage` satellites. Corridors between a DK bus and a zone, or
  between two zones, are bundled into one `ic:` edge (rating = Σ members; members kept in
  `edge_members`).
- **Π₁** — PyPSA's native k-means busmap inside DK1 (6) / DK2 (4), weighted by attached source
  capacity; satellites inherit their bus's cluster. Π₀ = zones, Π₂ = entities.
