"""Read/write the canonical `samples` table with `Sample` models at the boundary."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

import duckdb

from emap.schema import Sample

_COLS = (
    "entity_id",
    "entity_kind",
    "quantity",
    "t_utc",
    "value",
    "unit",
    "source",
    "resolution",
    "quality",
)
_INSERT = (
    f"INSERT OR REPLACE INTO samples ({', '.join(_COLS)}) VALUES ({', '.join('?' for _ in _COLS)})"
)
_SELECT = f"SELECT {', '.join(_COLS)} FROM samples"


def upsert_samples(cur: duckdb.DuckDBPyConnection, samples: Iterable[Sample]) -> int:
    """Insert-or-replace on the uniqueness key. Duplicates within the batch: last wins."""
    dedup: dict[tuple[str, str, datetime, str], Sample] = {}
    for s in samples:
        dedup[(s.entity_id, s.quantity, s.t_utc, s.source)] = s
    rows = [tuple(getattr(s, c) for c in _COLS) for s in dedup.values()]
    if not rows:
        return 0
    cur.executemany(_INSERT, rows)
    return len(rows)


def query_samples(
    cur: duckdb.DuckDBPyConnection,
    *,
    entity_id: str,
    quantity: str,
    start: datetime,
    end: datetime,
    source: str | None = None,
) -> list[Sample]:
    """Samples for one (entity, quantity) in [start, end), ascending by time."""
    sql = f"{_SELECT} WHERE entity_id = ? AND quantity = ? AND t_utc >= ? AND t_utc < ?"
    params: list[object] = [entity_id, quantity, start, end]
    if source is not None:
        sql += " AND source = ?"
        params.append(source)
    sql += " ORDER BY t_utc, source"
    return [
        Sample(**dict(zip(_COLS, row, strict=True))) for row in cur.execute(sql, params).fetchall()
    ]
