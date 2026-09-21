"""Zone-level reconciliation (MVP.md §2.3: balance enforced at the zonal level).

For a DK zone the measured terms of gen − load − X = 0 are the five 5-min production classes,
the (hourly, lagged) gross consumption and the metered corridor flows. Each carries a trust
weight (inverse variance) by quantity and freshness; the weighted projection in
analytics/balance.py closes the identity by adjusting the least-trusted terms most.
"""

from __future__ import annotations

from emap.analytics.balance import Measurement, reconcile
from emap.analytics.models import ReconciledZone
from emap.schema import Edge, Node, Quality

# Trust w (inverse variance). Metered interconnector flows > SCADA-upscaled production >
# settlement-grade but lagged consumption; a held (carried-forward) value is trusted less.
TRUST: dict[str, dict[str, float]] = {
    "flow": {"measured": 4.0, "held": 1.0},
    "p_gen": {"measured": 1.0, "held": 0.5},
    "demand": {"measured": 0.5, "held": 0.1},
}


def trust(quantity: str, quality: Quality) -> float:
    return TRUST[quantity]["measured" if quality == "measured" else "held"]


def reconcile_zone(
    zone: str,
    classes: dict[str, float],
    gen_quality: Quality,
    demand: float | None,
    demand_quality: Quality,
    flows: dict[str, tuple[float | None, Quality]],
    edges_by_id: dict[str, Edge],
    nodes_by_id: dict[str, Node],
) -> ReconciledZone | None:
    """None when the identity cannot be formed (no production, no load or no corridor flow)."""
    known_flows = {e: (f, q) for e, (f, q) in flows.items() if f is not None}
    if not classes or demand is None or not known_flows:
        return None
    ms: list[Measurement] = []
    for c, v in classes.items():
        ms.append(Measurement(f"class:{c}", v, +1.0, trust("p_gen", gen_quality)))
    ms.append(Measurement("demand", demand, -1.0, trust("demand", demand_quality)))
    for eid, (f, q) in known_flows.items():
        # flow is signed from->to; leaving the zone is export (enters the identity with −1)
        coef = -1.0 if nodes_by_id[edges_by_id[eid].from_].zone == zone else +1.0
        ms.append(Measurement(f"flow:{eid}", f, coef, trust("flow", q)))
    rec = reconcile(ms)
    by_class = {c: rec.values[f"class:{c}"] for c in classes}
    rflows = {eid: rec.values[f"flow:{eid}"] for eid in known_flows}
    exchange = 0.0
    for eid, f in rflows.items():
        exchange += f if nodes_by_id[edges_by_id[eid].from_].zone == zone else -f
    return ReconciledZone(
        p_gen=sum(by_class.values()),
        by_class=by_class,
        demand=rec.values["demand"],
        exchange=exchange,
        flows=rflows,
        adjustments=rec.adjustments,
        weights={m.key: m.weight for m in ms},
    )
