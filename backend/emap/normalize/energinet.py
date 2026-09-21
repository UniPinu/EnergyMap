"""Energinet rows -> canonical `Sample`s (pipeline stage ③, MVP.md §7).

Entity conventions (documented here, used by analytics and the API):
  <zone>                    zone aggregate (cluster id at Π₀): demand, p_gen, price, co2_intensity
  <zone>|<class>            5-min production class: wind_offshore | wind_onshore | solar |
                            thermal_ge100 | thermal_lt100
  <corridor edge id>        entity_kind 'edge', quantity 'flow', signed from->to (MVP.md §3.3)

Exchange sign: Energinet reports import-positive per price area; corridor edges are oriented
DK bus -> neighbour hub (and Funen -> Zealand for the Great Belt), so F_e = -exchange.
DK2's Bornholm-SE4 cable is folded into the DK2<->SE4 corridor (it is below the ≥220 kV network).
"""

from __future__ import annotations

from collections.abc import Iterable

from emap.ingest.energinet import CO2EmisRow, DayAheadPriceRow, GenProdTypeRow, ProdexRow
from emap.normalize.grid import expand
from emap.schema import Sample
from emap.topology import Topology

CLASSES: dict[str, str] = {  # Energinet column -> class id
    "OffshoreWindPower": "wind_offshore",
    "OnshoreWindPower": "wind_onshore",
    "SolarPower": "solar",
    "ProductionGe100MW": "thermal_ge100",
    "ProductionLt100MW": "thermal_lt100",
}
EXCHANGE_COLUMNS: dict[str, str] = {  # neighbour zone -> Energinet exchange column
    "DE_LU": "ExchangeGermany",
    "NL": "ExchangeNetherlands",
    "GB": "ExchangeGreatBritain",
    "NO2": "ExchangeNorway",
    "SE3": "ExchangeSweden",
    "SE4": "ExchangeSweden",
}
GREAT_BELT_ZONE = "DK1"  # the Great Belt flow is taken from DK1's column (DK2's is its mirror)


def class_entity(zone: str, cls: str) -> str:
    return f"{zone}|{cls}"


def corridor_map(topology: Topology) -> dict[tuple[str, str], tuple[str, float]]:
    """(dk_zone, neighbour_zone) -> (edge id, sign) where flow_from_to = sign * import_value.

    Corridors leave a DK bus toward a hub, or join Funen (DK1) to Zealand (DK2); the sign is
    -1 when the DK zone is the `from` end (export = positive F), +1 otherwise."""
    zone_of = {n.id: n.zone for n in topology.nodes}
    kind_of = {n.id: n.kind for n in topology.nodes}
    out: dict[tuple[str, str], tuple[str, float]] = {}
    for e in topology.edges:
        if e.kind != "interconnector":
            continue
        za, zb = zone_of[e.from_], zone_of[e.to]
        if kind_of[e.from_] != "grid" or kind_of[e.to] != "grid":
            continue
        dk_a, dk_b = za.startswith("DK"), zb.startswith("DK")
        if dk_a and dk_b:  # Great Belt: DK1 -> DK2 orientation
            key = ("DK1", "DK2")
            out[key] = (e.id, -1.0 if za == "DK1" else 1.0)
        elif dk_a:
            out[(za, zb)] = (e.id, -1.0)
        elif dk_b:
            out[(zb, za)] = (e.id, 1.0)
    return out


def _sample(
    entity_id: str, kind: str, quantity: str, t, value, unit, resolution, quality
) -> Sample:
    return Sample(
        entity_id=entity_id, entity_kind=kind, quantity=quantity, t_utc=t, value=value, unit=unit,
        source="energinet", resolution=resolution, quality=quality,
    )  # fmt: skip


def normalize_prodex(
    rows: Iterable[ProdexRow], corridors: dict[tuple[str, str], tuple[str, float]]
) -> list[Sample]:
    out: list[Sample] = []
    for r in rows:
        z, t = r.PriceArea, r.Minutes5UTC
        total = 0.0
        have_any = False
        for col, cls in CLASSES.items():
            v = getattr(r, col)
            if v is None:
                continue
            have_any = True
            total += v
            out.append(
                _sample(class_entity(z, cls), "node", "p_gen", t, v, "MW", "PT5M", "measured")
            )
        if have_any:
            out.append(_sample(z, "node", "p_gen", t, total, "MW", "PT5M", "measured"))
        for (dk, nb), (edge_id, sign) in corridors.items():
            if dk != z:
                continue
            if nb.startswith("DK"):  # Great Belt
                if z != GREAT_BELT_ZONE:
                    continue
                imp = r.ExchangeGreatBelt
            else:
                imp = getattr(r, EXCHANGE_COLUMNS[nb])
                if nb == "SE4" and z == "DK2" and r.BornholmSE4 is not None and imp is not None:
                    imp += r.BornholmSE4
            if imp is None:
                continue
            out.append(_sample(edge_id, "edge", "flow", t, sign * imp, "MW", "PT5M", "measured"))
    return out


def normalize_genprodtype(rows: Iterable[GenProdTypeRow]) -> list[Sample]:
    out: list[Sample] = []
    for r in rows:
        if r.GrossCon is None:
            continue
        for t, q in expand(r.TimeUTC, "PT60M"):
            out.append(_sample(r.PriceArea, "node", "demand", t, r.GrossCon, "MW", "PT60M", q))
    return out


def normalize_dayahead(rows: Iterable[DayAheadPriceRow], zones: set[str]) -> list[Sample]:
    out: list[Sample] = []
    for r in rows:
        if r.DayAheadPriceEUR is None or r.PriceArea not in zones:
            continue
        for t, q in expand(r.TimeUTC, "PT15M"):
            out.append(
                _sample(r.PriceArea, "node", "price", t, r.DayAheadPriceEUR, "EUR/MWh", "PT15M", q)
            )
    return out


def normalize_co2(rows: Iterable[CO2EmisRow]) -> list[Sample]:
    out: list[Sample] = []
    for r in rows:
        if r.CO2Emission is None:
            continue
        # g/kWh == kg/MWh -> tCO2/MWh
        out.append(
            _sample(
                r.PriceArea,
                "node",
                "co2_intensity",
                r.Minutes5UTC,
                r.CO2Emission / 1000.0,
                "tCO2/MWh",
                "PT5M",
                "measured",
            )
        )
    return out
