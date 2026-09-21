"""The bus->zone distribution rule (decided in Phase 2, MVP.md §10). Pure functions.

Generation, per zone and production class c with measured zonal total P_c:
    modelled plant i in class c:  P_i = min(cap_i, P_c · cap_i / Σ_j cap_j)
    remainder R_c = P_c - Σ_i P_i (= max(0, P_c - Σ cap)) goes to the distributed-generation
    node of every bus in proportion to its demand key:  P_dg(b) = Σ_c R_c · key_b
Demand, per zone with measured D_z:  D_load(b) = D_z · key_b.
Both conserve by construction: Σ_i P_i + Σ_b P_dg(b) = Σ_c P_c and Σ_b D_load(b) = D_z.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from emap.schema import Node

CLASS_IDS = ("wind_offshore", "wind_onshore", "solar", "thermal_ge100", "thermal_lt100")
THERMAL_FUELS = {
    "coal",
    "lignite",
    "gas",
    "oil",
    "biomass",
    "waste",
    "hydro",
    "nuclear",
    "geothermal",
    "other",
}
THERMAL_SPLIT_MW = 100.0  # Energinet's ProductionGe100MW / ProductionLt100MW boundary


def class_of(node: Node) -> str | None:
    """Production class a modelled plant belongs to, or None for dg:/zone aggregates."""
    if node.kind != "source" or node.fuel in (None, "distributed", "mixed"):
        return None
    if node.fuel in ("wind_offshore", "wind_onshore", "solar"):
        return node.fuel
    if node.fuel in THERMAL_FUELS:
        return "thermal_ge100" if (node.capacity_mw or 0) >= THERMAL_SPLIT_MW else "thermal_lt100"
    return "thermal_lt100"


@dataclass(frozen=True)
class ZonePlan:
    """Static per-zone structure the rule needs (built once from the topology)."""

    zone: str
    plants: dict[str, list[tuple[str, float]]]  # class -> [(node id, capacity)]
    dg_keys: dict[str, float]  # dg node id -> key
    load_keys: dict[str, float]  # load node id -> key

    @property
    def class_capacity(self) -> dict[str, float]:
        return {c: sum(cap for _, cap in ps) for c, ps in self.plants.items()}


def plan_zone(zone: str, nodes: Iterable[Node]) -> ZonePlan:
    plants: dict[str, list[tuple[str, float]]] = {c: [] for c in CLASS_IDS}
    dg: dict[str, float] = {}
    loads: dict[str, float] = {}
    for n in nodes:
        if n.zone != zone:
            continue
        if n.id.startswith("dg:"):
            dg[n.id] = n.dist_key or 0.0
        elif n.kind == "consumption" and n.dist_key is not None:
            loads[n.id] = n.dist_key
        else:
            c = class_of(n)
            if c and n.capacity_mw:
                plants[c].append((n.id, float(n.capacity_mw)))
    # keys are stored rounded in the artifact; renormalize so the rule conserves exactly
    for keys in (dg, loads):
        tot = sum(keys.values())
        if tot > 0:
            for k in keys:
                keys[k] /= tot
    return ZonePlan(zone, plants, dg, loads)


def distribute_generation(plan: ZonePlan, class_totals: Mapping[str, float]) -> dict[str, float]:
    """node id -> MW for every plant and dg node of the zone (classes missing from
    `class_totals` are left out entirely, not zeroed)."""
    out: dict[str, float] = {}
    remainder = 0.0
    any_class = False
    for c, total in class_totals.items():
        ps = plan.plants.get(c, [])
        cap_sum = sum(cap for _, cap in ps)
        any_class = True
        assigned = 0.0
        for nid, cap in ps:
            p = min(cap, total * cap / cap_sum) if cap_sum > 0 else 0.0
            out[nid] = p
            assigned += p
        rem = total - assigned
        remainder += rem if rem > 1e-6 else 0.0  # fully absorbed classes leave 1e-13 noise
    if any_class:
        for nid, key in plan.dg_keys.items():
            out[nid] = remainder * key
    return out


def distribute_demand(plan: ZonePlan, demand: float) -> dict[str, float]:
    return {nid: demand * key for nid, key in plan.load_keys.items()}
