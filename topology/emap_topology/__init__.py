"""emap_topology — service A (IMPLEMENTATION_PLAN.md §1): one-time, versioned export of the
PyPSA-Eur network into the canonical Node/Edge graph plus the cluster hierarchy Π₀…Π_L.

Inputs are exactly the datasets PyPSA-Eur consumes (pinned in its data/versions.csv):
  * OSM prebuilt electricity network (buses/lines/links/converters/transformers)
  * powerplantmatching `powerplants.csv`
  * bidding-zone polygons shipped with entsoe-py
"""

__version__ = "0.0.1"
