"""DuckDB store: connection lifecycle + versioned SQL migrations.

Design notes
------------
* One process owns the database file (DuckDB is single-writer). API and the
  scheduled ingesters therefore run inside the same uvicorn worker.
* Every cursor runs with `TimeZone='UTC'`, so TIMESTAMPTZ values round-trip as
  timezone-aware UTC datetimes — the only representation that crosses this
  boundary (MVP.md §5: "UTC everywhere").
* Migrations are plain SQL files `migrations/NNNN_name.sql`, applied in order
  and recorded in `schema_migrations`; re-running is a no-op.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb

MIGRATIONS_DIR = Path(__file__).with_name("migrations")
_MIGRATION_RE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path


def discover_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    found: list[Migration] = []
    for p in sorted(directory.glob("*.sql")):
        m = _MIGRATION_RE.match(p.name)
        if not m:
            raise ValueError(f"migration file name not in NNNN_name.sql form: {p.name}")
        found.append(Migration(int(m.group(1)), m.group(2), p))
    versions = [m.version for m in found]
    if len(versions) != len(set(versions)):
        raise ValueError(f"duplicate migration versions in {directory}")
    return found


def _configure(cur: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyConnection:
    cur.execute("SET TimeZone = 'UTC'")
    return cur


def applied_migrations(cur: duckdb.DuckDBPyConnection) -> list[tuple[int, str, datetime]]:
    cur.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL)"
    )
    return cur.execute(
        "SELECT version, name, applied_at FROM schema_migrations ORDER BY version"
    ).fetchall()


def migrate(cur: duckdb.DuckDBPyConnection, directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Apply every migration not yet recorded. Returns the ones applied this call."""
    done = {v for v, _, _ in applied_migrations(cur)}
    applied: list[Migration] = []
    for m in discover_migrations(directory):
        if m.version in done:
            continue
        cur.execute("BEGIN")
        try:
            cur.execute(m.path.read_text(encoding="utf-8"))
            cur.execute(
                "INSERT INTO schema_migrations VALUES (?, ?, ?)",
                [m.version, m.name, datetime.now(UTC)],
            )
            cur.execute("COMMIT")
        except Exception:
            cur.execute("ROLLBACK")
            raise
        applied.append(m)
    return applied


class Store:
    """Owns the root connection; hands out per-request cursors (thread-safe in DuckDB)."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path) if str(path) != ":memory:" else path
        if isinstance(self.path, Path):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._root = _configure(duckdb.connect(str(self.path)))

    @contextmanager
    def cursor(self) -> Iterator[duckdb.DuckDBPyConnection]:
        cur = _configure(self._root.cursor())
        try:
            yield cur
        finally:
            cur.close()

    def migrate(self) -> list[Migration]:
        with self.cursor() as cur:
            return migrate(cur)

    def applied(self) -> list[tuple[int, str, datetime]]:
        with self.cursor() as cur:
            return applied_migrations(cur)

    def close(self) -> None:
        self._root.close()


def open_store(path: Path | str, *, run_migrations: bool = True) -> Store:
    store = Store(path)
    if run_migrations:
        store.migrate()
    return store
