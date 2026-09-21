"""Demand distribution key per DK bus (the bus->zone rule for load, MVP.md §10).

PyPSA-Eur's rule, reproduced: each bus owns the Voronoi cell of its zone; NUTS3 population and
GDP are spread over the cells by area overlap; key_b = 0.6·pop_b/Σpop + 0.4·gdp_b/Σgdp within
the zone, so Σ_b key_b = 1 per zone. A NUTS3 region that no cell covers (Bornholm, outside the
DK2 polygon) is assigned wholly to the nearest bus of its zone.
"""

from __future__ import annotations

import pandas as pd
import shapely
from shapely.geometry import MultiPoint, Point, shape
from shapely.geometry.base import BaseGeometry

from .zones import assign_zone

W_POP, W_GDP = 0.6, 0.4


def voronoi_cells(buses: pd.DataFrame, zone_poly: BaseGeometry) -> dict[str, BaseGeometry]:
    """bus_id -> Voronoi cell clipped to the zone polygon (buses: index bus_id, columns x, y)."""
    pts = [Point(x, y) for x, y in zip(buses.x, buses.y, strict=True)]
    if len(pts) == 1:
        return {buses.index[0]: zone_poly}
    cells = shapely.voronoi_polygons(MultiPoint(pts), extend_to=zone_poly.envelope.buffer(2.0))
    out: dict[str, BaseGeometry] = {}
    for cell in cells.geoms:
        hit = [bid for bid, p in zip(buses.index, pts, strict=True) if cell.contains(p)]
        if len(hit) != 1:
            raise RuntimeError(f"voronoi cell matched {len(hit)} buses")
        out[hit[0]] = cell.intersection(zone_poly)
    return out


def load_keys(
    buses: pd.DataFrame,
    polygons: dict[str, BaseGeometry],
    nuts_gj: dict,
    stats: dict[str, dict[str, float]],
) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
    """(bus_id -> key, bus_id -> {pop_ths, gdp_meur}) for DK AC buses (index bus_id, x, y, zone)."""
    regions = []
    for f in nuts_gj["features"]:
        rid = f["properties"]["id"]
        st = stats.get(rid)
        if not st or not st.get("pop_ths"):
            continue  # DKZZZ extra-regio etc.
        geom = shape(f["geometry"])
        rp = geom.representative_point()
        zone = assign_zone(rp.x, rp.y, "DK", polygons)
        regions.append((rid, geom, st, zone))

    pop: dict[str, float] = dict.fromkeys(buses.index, 0.0)
    gdp: dict[str, float] = dict.fromkeys(buses.index, 0.0)
    cells: dict[str, BaseGeometry] = {}
    for zone, zb in buses.groupby("zone"):
        cells.update(voronoi_cells(zb, polygons[zone]))

    for _rid, geom, st, zone in regions:
        zb = buses[buses.zone == zone]
        overlaps = {b: cells[b].intersection(geom).area for b in zb.index}
        covered = sum(overlaps.values())
        if covered <= 1e-9:  # not covered by any cell (Bornholm): nearest bus of the zone
            rp = geom.representative_point()
            nearest = min(zb.index, key=lambda b: rp.distance(Point(zb.x[b], zb.y[b])))
            overlaps = {nearest: 1.0}
            covered = 1.0
        for b, a in overlaps.items():
            pop[b] += st["pop_ths"] * a / covered
            gdp[b] += st.get("gdp_meur", 0.0) * a / covered

    keys: dict[str, float] = {}
    for _zone, zb in buses.groupby("zone"):
        p_tot = sum(pop[b] for b in zb.index)
        g_tot = sum(gdp[b] for b in zb.index)
        for b in zb.index:
            kp = pop[b] / p_tot if p_tot else 1 / len(zb)
            kg = gdp[b] / g_tot if g_tot else kp
            keys[b] = W_POP * kp + W_GDP * kg
    detail = {b: {"pop_ths": round(pop[b], 3), "gdp_meur": round(gdp[b], 3)} for b in buses.index}
    return keys, detail
