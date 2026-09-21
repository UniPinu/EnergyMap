"""Finest-level graph (Π_L): DK buses / plants / loads / storage at entity granularity,
neighbour zones as hub + aggregate source / load / storage satellites (MVP.md §2.3).

Node ids:  bus:<osm bus>  plant:<ppm id>  load:<osm bus>  store:<ppm id>
           hub:<zone>  zgen:<zone>  zload:<zone>  zstore:<zone>
Edge ids:  line:<id>  xfmr:<id>  link:<id>  conn:<ppm id>  feed:<osm bus>
           ic:<a>--<b>  (bundled cross-zone corridor, members listed in `edge_members`)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from shapely.geometry.base import BaseGeometry

from .config import PARAMS, STORAGE_FUELTYPES, STORAGE_TECHS, ZONES, BuildParams
from .zones import assign_zones, zone_anchor

FUEL_MAP = {  # powerplantmatching Fueltype/Technology -> canonical `fuel`
    ("Wind", "Offshore"): "wind_offshore",
    ("Wind", "Onshore"): "wind_onshore",
    ("Solar", "PV"): "solar",
    ("Solar", "Csp"): "solar",
    ("Hydro", "Pumped Storage"): "hydro_pumped",
    ("Hydro", "Reservoir"): "hydro",
    ("Hydro", "Run-Of-River"): "hydro",
    ("Nuclear", None): "nuclear",
    ("Natural Gas", None): "gas",
    ("Hard Coal", None): "coal",
    ("Lignite", None): "lignite",
    ("Oil", None): "oil",
    ("Solid Biomass", None): "biomass",
    ("Biogas", None): "biomass",
    ("Waste", None): "waste",
    ("Battery", None): "battery",
    ("Hydrogen Storage", None): "hydrogen",
    ("Mechanical Storage", None): "mechanical",
    ("Geothermal", None): "geothermal",
    ("Other", None): "other",
}

# Indicative operating combustion intensities, tCO2/MWh_el. A per-node attribute only;
# the balance math never depends on them.
CO2 = {"coal": 0.82, "lignite": 0.95, "gas": 0.37, "oil": 0.65, "waste": 0.30, "biomass": 0.0}


def fuel_of(fueltype: str, tech: object) -> str:
    t = tech if isinstance(tech, str) else None
    return FUEL_MAP.get((fueltype, t)) or FUEL_MAP.get((fueltype, None)) or "other"


def is_storage(row: pd.Series) -> bool:
    if row.Set not in ("Store", "Storage"):
        return False
    return row.Fueltype in STORAGE_FUELTYPES or (row.Fueltype, row.Technology) in STORAGE_TECHS


_PREFIX = re.compile(
    r"^\s*(\d{3}\s*kV\s*/\s*\d{2,3}\s*kV|\d{3}\s*/\s*\d{2,3}\s*kV|\d{3}\s*kV)\s*", re.I
)


def clean_name(raw: str) -> str:
    return _PREFIX.sub("", raw).strip() or raw


@dataclass
class Graph:
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)
    edge_members: dict[str, list[str]] = field(default_factory=dict)  # bundled id -> osm ids
    bus_of: dict[str, str] = field(default_factory=dict)  # node id -> grid node it hangs off
    zone_anchor: dict[str, tuple[float, float]] = field(default_factory=dict)

    def add_node(self, **n) -> None:
        self.nodes.append(n)

    def add_edge(
        self,
        id: str,
        from_: str,
        to: str,
        kind: str,
        rating_mw: float | None,
        length_km: float | None = None,
    ) -> None:
        self.edges.append(
            {
                "id": id,
                "from": from_,
                "to": to,
                "kind": kind,
                "rating_mw": rating_mw,
                "length_km": length_km,
            }
        )


def _haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def _node(
    g: Graph,
    id: str,
    kind: str,
    name: str,
    zone: str,
    lat: float,
    lon: float,
    *,
    capacity_mw=None,
    fuel=None,
    co2_intensity=None,
    **extra,
) -> None:
    g.add_node(
        id=id,
        kind=kind,
        name=name,
        zone=zone,
        lat=float(lat),
        lon=float(lon),
        capacity_mw=capacity_mw,
        fuel=fuel,
        co2_intensity=co2_intensity,
        cluster={},
        **extra,
    )


def build_graph(
    osm: dict[str, pd.DataFrame],
    plants: pd.DataFrame,
    polygons: dict[str, BaseGeometry],
    names: dict[str, str],
    params: BuildParams = PARAMS,
) -> Graph:
    g = Graph()
    buses = osm["buses"].copy()
    buses["zone"] = assign_zones(buses, polygons)
    buses = buses[buses.zone.notna()]
    detail_zones = {z.id for z in ZONES.values() if z.detail}
    dlon, dlat = params.satellite_offset_deg

    # ---- DK grid buses (AC only) + one consumption node per bus ---------------------------
    dk_ac = buses[(buses.zone.isin(detail_zones)) & (~buses.dc)]
    for bid, r in dk_ac.iterrows():
        raw = next((names[t] for t in str(r.tags).split(";") if t in names), None)
        nm = (
            clean_name(raw)
            if raw
            else f"Substation {int(r.voltage)} kV #{bid.split('/')[-1].split(':')[0][-6:]}"
        )
        _node(g, f"bus:{bid}", "grid", nm, r.zone, r.y, r.x, voltage_kv=int(r.voltage))
        g.bus_of[f"bus:{bid}"] = f"bus:{bid}"
        _node(g, f"load:{bid}", "consumption", f"Load @ {nm}", r.zone, r.y + dlat, r.x + dlon)
        g.bus_of[f"load:{bid}"] = f"bus:{bid}"
        g.add_edge(f"feed:{bid}", f"bus:{bid}", f"load:{bid}", "ac_line", None)

    # ---- neighbour zones: hub node (interconnectors land here) ------------------------------
    for z in ZONES.values():
        g.zone_anchor[z.id] = zone_anchor(z.id, polygons)
        if not z.detail:
            lat, lon = g.zone_anchor[z.id]
            _node(g, f"hub:{z.id}", "grid", f"{z.name} ({z.id})", z.id, lat, lon)
            g.bus_of[f"hub:{z.id}"] = f"hub:{z.id}"

    # ---- plants: DK individually (attached to nearest AC bus), neighbours aggregated --------
    pl = plants.copy()
    pl["zone"] = assign_zones(pl, polygons, lon="lon", lat="lat", country="iso")
    pl = pl[pl.zone.notna()]
    pl = pl[~(pl.DateOut.notna() & (pl.DateOut < params.as_of_year))]  # retired units
    pl["storage"] = pl.apply(is_storage, axis=1)
    gen = pl[(~pl.storage) & (pl.Set.isin(["PP", "CHP"]) | pl.Set.isna())]
    sto = pl[pl.storage]

    for zid in sorted(detail_zones):
        zb = dk_ac[dk_ac.zone == zid]
        for src, is_store in ((gen[gen.zone == zid], False), (sto[sto.zone == zid], True)):
            thr = params.storage_min_mw if is_store else params.plant_min_mw
            for pid, r in src[src.Capacity >= thr].iterrows():
                d = _haversine_km(r.lat, r.lon, zb.y.to_numpy(), zb.x.to_numpy())
                bus = f"bus:{zb.index[int(d.argmin())]}"
                fuel = fuel_of(r.Fueltype, r.Technology)
                nid = f"{'store' if is_store else 'plant'}:{pid}"
                emax = (
                    r.StorageCapacity_MWh
                    if pd.notna(r.StorageCapacity_MWh)
                    else r.Capacity * r.Duration
                    if pd.notna(r.Duration)
                    else None
                )
                _node(
                    g,
                    nid,
                    "storage" if is_store else "source",
                    str(r.Name),
                    zid,
                    r.lat,
                    r.lon,
                    capacity_mw=float(r.Capacity),
                    fuel=fuel,
                    co2_intensity=None if is_store else CO2.get(fuel, 0.0),
                    energy_mwh=float(emax) if emax else None,
                )
                g.bus_of[nid] = bus
                g.add_edge(f"conn:{pid}", nid, bus, "ac_line", float(r.Capacity), float(d.min()))

    for z in ZONES.values():
        if z.detail:
            continue
        lat, lon = g.zone_anchor[z.id]
        gcap = float(gen[gen.zone == z.id].Capacity.sum())
        scap = float(sto[sto.zone == z.id].Capacity.sum())
        semax = float(sto[sto.zone == z.id].StorageCapacity_MWh.sum())
        _node(
            g,
            f"zgen:{z.id}",
            "source",
            f"{z.id} generation",
            z.id,
            lat - 3 * dlat,
            lon - 3 * dlon,
            capacity_mw=gcap,
            fuel="mixed",
        )
        _node(
            g, f"zload:{z.id}", "consumption", f"{z.id} load", z.id, lat + 3 * dlat, lon + 3 * dlon
        )
        g.bus_of[f"zgen:{z.id}"] = g.bus_of[f"zload:{z.id}"] = f"hub:{z.id}"
        g.add_edge(f"zgen-conn:{z.id}", f"zgen:{z.id}", f"hub:{z.id}", "ac_line", gcap)
        g.add_edge(f"zfeed:{z.id}", f"hub:{z.id}", f"zload:{z.id}", "ac_line", None)
        if scap >= params.storage_min_mw:
            _node(
                g,
                f"zstore:{z.id}",
                "storage",
                f"{z.id} storage",
                z.id,
                lat - 3 * dlat,
                lon + 3 * dlon,
                capacity_mw=scap,
                fuel="mixed",
                energy_mwh=semax or None,
            )
            g.bus_of[f"zstore:{z.id}"] = f"hub:{z.id}"
            g.add_edge(f"zstore-conn:{z.id}", f"zstore:{z.id}", f"hub:{z.id}", "ac_line", scap)

    _add_branches(g, osm, buses, detail_zones)
    return g


def _add_branches(
    g: Graph, osm: dict[str, pd.DataFrame], buses: pd.DataFrame, detail_zones: set[str]
) -> None:
    """Lines / transformers / HVDC links → edges. DC converter buses collapse onto their AC
    side; endpoints outside DK collapse onto their zone hub; corridors between different
    endpoint *nodes* that touch a hub are bundled into one `ic:` edge (rating = Σ)."""
    zone_of = buses.zone.to_dict()
    is_dc = buses.dc.to_dict()
    dc_to_ac: dict[str, str] = {}
    for r in osm["converters"].itertuples():
        if is_dc.get(r.bus0, False) and not is_dc.get(r.bus1, False):
            dc_to_ac[r.bus0] = r.bus1
        elif is_dc.get(r.bus1, False) and not is_dc.get(r.bus0, False):
            dc_to_ac[r.bus1] = r.bus0

    def endpoint(b: str) -> str | None:
        b = dc_to_ac.get(b, b)
        z = zone_of.get(b)
        if z is None:
            return None
        if z in detail_zones and not is_dc.get(b, False):
            return f"bus:{b}"
        return f"hub:{z}"

    bundles: dict[tuple[str, str], dict] = {}

    def branch(id_: str, b0: str, b1: str, kind: str, rating: float, length_km: float | None):
        n0, n1 = endpoint(b0), endpoint(b1)
        if n0 is None or n1 is None or n0 == n1:
            return
        z0, z1 = g_zone(g, n0), g_zone(g, n1)
        cross_zone = z0 != z1
        if n0.startswith("bus:") and n1.startswith("bus:"):
            g.add_edge(id_, n0, n1, "interconnector" if cross_zone else kind, rating, length_km)
            return
        a, b = sorted((n0, n1))
        entry = bundles.setdefault((a, b), {"rating": 0.0, "members": [], "kinds": set()})
        entry["rating"] += rating
        entry["members"].append(id_)
        entry["kinds"].add(kind)

    lines = osm["lines"]
    for lid, r in lines[~lines.under_construction].iterrows():
        branch(f"line:{lid}", r.bus0, r.bus1, "ac_line", float(r.s_nom), float(r.length) / 1000)
    for tid, r in osm["transformers"].iterrows():
        branch(f"xfmr:{tid}", r.bus0, r.bus1, "ac_line", float(r.s_nom), None)
    links = osm["links"]
    for kid, r in links[~links.under_construction].iterrows():
        branch(f"link:{kid}", r.bus0, r.bus1, "hvdc_link", float(r.p_nom), float(r.length) / 1000)

    for (a, b), e in sorted(bundles.items()):
        za, zb = g_zone(g, a), g_zone(g, b)
        kind = (
            "interconnector"
            if za != zb
            else ("hvdc_link" if e["kinds"] == {"hvdc_link"} else "ac_line")
        )
        eid = f"ic:{a}--{b}"
        g.add_edge(eid, a, b, kind, round(e["rating"], 3), None)
        g.edge_members[eid] = e["members"]


def g_zone(g: Graph, node_id: str) -> str:
    if node_id.startswith("hub:"):
        return node_id[4:]
    if not hasattr(g, "_zone_index"):
        g._zone_index = {n["id"]: n["zone"] for n in g.nodes}  # type: ignore[attr-defined]
    return g._zone_index[node_id]  # type: ignore[attr-defined]
