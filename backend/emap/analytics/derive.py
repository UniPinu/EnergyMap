"""Stage ⑤ derived series: the reconciliation residual r(t) and r̂(t) per DK zone as canonical
`derived` samples (MVP.md §3.4), so the gauge has history and the calendar (Phase 4) can replay
it. Computed set-based in DuckDB for every 5-min instant at which production, consumption and
all corridor flows of the zone exist — where the identity cannot be formed no row is written.

    python -m emap.analytics.derive --days 35     # backfill history
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

import duckdb

from emap.normalize.energinet import corridor_map
from emap.schema import Sample
from emap.store import upsert_samples
from emap.topology import Topology

DK_ZONES = ("DK1", "DK2")


def derive_residuals(
    cur: duckdb.DuckDBPyConnection, topology: Topology, start: datetime, end: datetime
) -> list[Sample]:
    nodes_by_id = topology.node_index()
    edges_by_id = {e.id: e for e in topology.edges}
    corridors = corridor_map(topology)
    out: list[Sample] = []
    for zone in DK_ZONES:
        # (edge id, sign) so that Σ sign·flow = net export X of this zone
        terms = []
        for (dk, _nb), (eid, _o) in corridors.items():
            if dk != zone and nodes_by_id[edges_by_id[eid].to].zone != zone:
                continue
            if dk == zone or nodes_by_id[edges_by_id[eid].from_].zone == zone:
                terms.append((eid, 1.0))
            else:
                terms.append((eid, -1.0))
        if not terms:
            continue
        values = ", ".join(f"('{eid}', {sign})" for eid, sign in terms)
        rows = cur.execute(
            f"""
            WITH g AS (
                SELECT t_utc, value AS p_gen, quality = 'measured' AS fresh
                FROM samples WHERE entity_id = ? AND quantity = 'p_gen' AND value IS NOT NULL
            ), d AS (
                SELECT t_utc, value AS demand, quality = 'measured' AS fresh
                FROM samples WHERE entity_id = ? AND quantity = 'demand' AND value IS NOT NULL
            ), c(edge_id, sign) AS (VALUES {values}), f AS (
                SELECT s.t_utc, sum(c.sign * s.value) AS x, count(*) AS n,
                       bool_and(s.quality = 'measured') AS fresh
                FROM samples s JOIN c ON s.entity_id = c.edge_id
                WHERE s.quantity = 'flow' AND s.value IS NOT NULL
                GROUP BY s.t_utc
            )
            SELECT g.t_utc, g.p_gen - d.demand - f.x AS r,
                   CASE WHEN d.demand > 0 THEN (g.p_gen - d.demand - f.x) / d.demand END AS r_hat,
                   g.fresh AND d.fresh AND f.fresh AS fresh
            FROM g JOIN d USING (t_utc) JOIN f USING (t_utc)
            WHERE f.n = ? AND g.t_utc >= ? AND g.t_utc < ?
            ORDER BY g.t_utc
            """,
            [zone, zone, len(terms), start, end],
        ).fetchall()
        for t, r, r_hat, fresh in rows:
            q = "measured" if fresh else "interpolated"
            out.append(
                Sample(
                    entity_id=zone,
                    entity_kind="node",
                    quantity="residual",
                    t_utc=t,
                    value=r,
                    unit="MW",
                    source="derived",
                    resolution="PT5M",
                    quality=q,
                )  # fmt: skip
            )
            if r_hat is not None:
                out.append(
                    Sample(
                        entity_id=zone,
                        entity_kind="node",
                        quantity="residual_hat",
                        t_utc=t,
                        value=r_hat,
                        unit="ratio",
                        source="derived",
                        resolution="PT5M",
                        quality=q,
                    )  # fmt: skip
                )
    return out


def derive_and_store(cur, topology: Topology, hours: float = 6.0) -> int:
    end = datetime.now(UTC) + timedelta(minutes=5)
    return upsert_samples(cur, derive_residuals(cur, topology, end - timedelta(hours=hours), end))


def main() -> None:
    from emap.config import get_settings
    from emap.store import open_store
    from emap.topology import load_topology

    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=35)
    args = ap.parse_args()
    settings = get_settings()
    store = open_store(settings.emap_db_path)
    topo = load_topology(settings.emap_topology_path)
    with store.cursor() as cur:
        n = derive_and_store(cur, topo, hours=args.days * 24)
    store.close()
    print(f"residual rows written: {n}")


if __name__ == "__main__":
    main()
