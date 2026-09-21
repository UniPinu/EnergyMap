"""Apply pending migrations to the configured store and print the result.

python scripts/migrate.py
"""

from __future__ import annotations

from emap.config import get_settings
from emap.store import open_store

settings = get_settings()
store = open_store(settings.emap_db_path, run_migrations=False)
applied = store.migrate()
print(f"db: {store.path}")
print(f"applied now: {[f'{m.version:04d}_{m.name}' for m in applied] or 'nothing (up to date)'}")
print(f"all applied: {[f'{v:04d}_{n}' for v, n, _ in store.applied()]}")
store.close()
