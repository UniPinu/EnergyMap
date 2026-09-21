"""Stage ⑥ time-series reads. Stored entities (zones, classes, corridors) come straight from
the canonical table; DK plant / dg / load nodes are *derived* on the fly by applying the
distribution rule to their zone's series at every grid instant (the same rule as the live
state, so a node's history and its face agree)."""

from __future__ import annotations

from datetime import datetime

import duckdb
from pydantic import AwareDatetime, BaseModel

from emap.analytics.distribution import CLASS_IDS, class_of, plan_zone
from emap.normalize.energinet import class_entity
from emap.schema import Quality, Quantity, Unit
from emap.store import query_samples
from emap.topology import Topology


class SeriesPoint(BaseModel):
    t: AwareDatetime
    v: float
    q: Quality


class SeriesResponse(BaseModel):
    entity_id: str
    quantity: Quantity
    unit: Unit
    derived_from: str | None = None  # rule applied, for derived node series
    points: list[SeriesPoint]


def _stored(
    cur, entity_id: str, quantity: str, start: datetime, end: datetime
) -> list[SeriesPoint]:
    rows = query_samples(cur, entity_id=entity_id, quantity=quantity, start=start, end=end)
    return [SeriesPoint(t=r.t_utc, v=r.value, q=r.quality) for r in rows if r.value is not None]


def _unit(quantity: str) -> Unit:
    return {
        "price": "EUR/MWh",
        "co2_intensity": "tCO2/MWh",
        "soc": "ratio",
        "strain": "ratio",
        "residual": "MW",
    }.get(quantity, "MW")  # type: ignore[return-value]


def series(
    topology: Topology,
    cur: duckdb.DuckDBPyConnection,
    entity_id: str,
    quantity: Quantity,
    start: datetime,
    end: datetime,
) -> SeriesResponse:
    node = topology.node_index().get(entity_id)
    unit = _unit(quantity)
    if node is None or not node.zone.startswith("DK") or quantity not in ("p_gen", "demand"):
        return SeriesResponse(
            entity_id=entity_id,
            quantity=quantity,
            unit=unit,
            points=_stored(cur, entity_id, quantity, start, end),
        )

    plan = plan_zone(node.zone, topology.nodes)
    if quantity == "demand" and node.kind == "consumption":
        key = plan.load_keys.get(node.id)
        if key is None:
            return SeriesResponse(entity_id=entity_id, quantity=quantity, unit=unit, points=[])
        pts = _stored(cur, node.zone, "demand", start, end)
        return SeriesResponse(
            entity_id=entity_id,
            quantity=quantity,
            unit=unit,
            derived_from=f"{node.zone} demand × key {key:.4f}",
            points=[SeriesPoint(t=p.t, v=p.v * key, q=p.q) for p in pts],
        )

    if quantity == "p_gen" and node.kind == "source":
        if node.id.startswith("dg:"):
            key = plan.dg_keys.get(node.id, 0.0)
            caps = plan.class_capacity
            remainder: dict[datetime, tuple[float, Quality]] = {}
            for c in CLASS_IDS:
                for p in _stored(cur, class_entity(node.zone, c), "p_gen", start, end):
                    rem = max(0.0, p.v - caps.get(c, 0.0))
                    prev = remainder.get(p.t, (0.0, p.q))
                    remainder[p.t] = (prev[0] + rem, p.q)
            return SeriesResponse(
                entity_id=entity_id,
                quantity=quantity,
                unit=unit,
                derived_from=f"{node.zone} class remainders × key {key:.4f}",
                points=[
                    SeriesPoint(t=t, v=r * key, q=q) for t, (r, q) in sorted(remainder.items())
                ],
            )
        cls = class_of(node)
        cap = node.capacity_mw or 0.0
        cap_sum = plan.class_capacity.get(cls or "", 0.0)
        if not cls or cap_sum <= 0:
            return SeriesResponse(entity_id=entity_id, quantity=quantity, unit=unit, points=[])
        pts = _stored(cur, class_entity(node.zone, cls), "p_gen", start, end)
        return SeriesResponse(
            entity_id=entity_id,
            quantity=quantity,
            unit=unit,
            derived_from=f"{node.zone}|{cls} × min(1, {cap:.0f}/{cap_sum:.0f}) capped at nameplate",
            points=[SeriesPoint(t=p.t, v=min(cap, p.v * cap / cap_sum), q=p.q) for p in pts],
        )

    return SeriesResponse(
        entity_id=entity_id,
        quantity=quantity,
        unit=unit,
        points=_stored(cur, entity_id, quantity, start, end),
    )
