"""Read/write the canonical `samples` table with `Sample` models at the boundary."""

from __future__ import annotations

import os
import tempfile
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
    """Insert-or-replace on the uniqueness key. Duplicates within the batch: last wins.

    Rows are staged through a temporary newline-delimited JSON file and loaded with
    DuckDB's vectorised reader: ~1000x faster than `executemany` (which runs one prepared
    statement per row) and dependency-free."""
    dedup: dict[tuple[str, str, datetime, str], Sample] = {}
    for s in samples:
        dedup[(s.entity_id, s.quantity, s.t_utc, s.source)] = s
    if not dedup:
        return 0
    fd, path = tempfile.mkstemp(suffix=".ndjson")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for s in dedup.values():
                f.write(s.model_dump_json() + "\n")
        cols = ", ".join(_COLS)
        select = ", ".join("CAST(t_utc AS TIMESTAMPTZ)" if c == "t_utc" else c for c in _COLS)
        schema = ", ".join(f"'{c}': '{'DOUBLE' if c == 'value' else 'VARCHAR'}'" for c in _COLS)
        src = path.replace(chr(92), "/")
        cur.execute(
            f"INSERT OR REPLACE INTO samples ({cols}) SELECT {select} "
            f"FROM read_json('{src}', format='newline_delimited', columns={{{schema}}})"
        )
    finally:
        os.remove(path)
    return len(dedup)


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
