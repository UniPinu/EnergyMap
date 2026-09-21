"""Backfill DK history from Energinet into the store.

python -m emap.ingest.backfill --days 35 --weeks 12
"""

from __future__ import annotations

import argparse
import logging

from emap.config import get_settings
from emap.ingest.energinet import EnerginetClient
from emap.ingest.jobs import backfill
from emap.store import open_store
from emap.topology import load_topology


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--days", type=int, default=35, help="days of 5-min history (production, exchange, CO2)"
    )
    ap.add_argument("--weeks", type=int, default=12, help="weeks of hourly load and 15-min prices")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = get_settings()
    store = open_store(settings.emap_db_path)
    topo = load_topology(settings.emap_topology_path)
    client = EnerginetClient()
    try:
        written = backfill(client, store, topo, days_5min=args.days, weeks_hourly=args.weeks)
    finally:
        client.close()
        store.close()
    print({k: v for k, v in written.items()})


if __name__ == "__main__":
    main()
