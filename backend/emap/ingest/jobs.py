"""Ingestion jobs: fetch (rate-limit aware) -> normalize -> upsert, with a status registry that
the API exposes at /api/ingest/status. One module per source; scheduling lives in scheduler.py.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from emap.ingest.energinet import EnerginetClient
from emap.normalize.energinet import (
    corridor_map,
    normalize_co2,
    normalize_dayahead,
    normalize_genprodtype,
    normalize_prodex,
)
from emap.store import Store, upsert_samples
from emap.topology import Topology

log = logging.getLogger(__name__)
DK_ZONES = ("DK1", "DK2")


@dataclass
class JobStatus:
    name: str
    dataset: str
    interval_s: int
    last_started_utc: datetime | None = None
    last_ok_utc: datetime | None = None
    last_rows: int = 0
    last_error: str | None = None
    runs: int = 0
    failures: int = 0


@dataclass
class Registry:
    jobs: dict[str, JobStatus] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def snapshot(self) -> list[JobStatus]:
        with self.lock:
            return [JobStatus(**vars(j)) for j in self.jobs.values()]


@dataclass
class Job:
    name: str
    dataset: str
    interval_s: int
    run: Callable[[], int]  # returns rows written


def build_jobs(client: EnerginetClient, store: Store, topology: Topology) -> list[Job]:
    corridors = corridor_map(topology)
    zones = set(DK_ZONES)

    def write(samples) -> int:
        with store.cursor() as cur:
            return upsert_samples(cur, samples)

    def prodex() -> int:  # 5-min dataset: poll every 5 min with a 30-min dynamic window
        rows = client.fetch(
            "ElectricityProdex5MinRealtime", start="now-PT30M", price_areas=DK_ZONES
        )
        return write(normalize_prodex(rows, corridors))

    def genprodtype() -> int:  # hourly, ~2 h lag, values get revised: 6-h window every 20 min
        rows = client.fetch("GenerationProdTypeExchange", start="now-PT6H", price_areas=DK_ZONES)
        return write(normalize_genprodtype(rows))

    def dayahead() -> int:  # daily publication of 15-min prices: hourly poll, D-1..D+2 window
        rows = client.fetch("DayAheadPrices", start="now-P1D", end="now+P2D", price_areas=DK_ZONES)
        return write(normalize_dayahead(rows, zones))

    def co2() -> int:
        rows = client.fetch("CO2Emis", start="now-PT30M", price_areas=DK_ZONES)
        return write(normalize_co2(rows))

    return [
        Job("energinet.prodex", "ElectricityProdex5MinRealtime", 300, prodex),
        Job("energinet.genprodtype", "GenerationProdTypeExchange", 1200, genprodtype),
        Job("energinet.dayahead", "DayAheadPrices", 3600, dayahead),
        Job("energinet.co2", "CO2Emis", 300, co2),
    ]


def run_job(job: Job, registry: Registry) -> int:
    st = registry.jobs.setdefault(job.name, JobStatus(job.name, job.dataset, job.interval_s))
    with registry.lock:
        st.last_started_utc = datetime.now(UTC)
        st.runs += 1
    try:
        n = job.run()
    except Exception as exc:  # noqa: BLE001 — a failing source must never take the API down
        log.exception("job %s failed", job.name)
        with registry.lock:
            st.failures += 1
            st.last_error = f"{type(exc).__name__}: {exc}"[:300]
        return 0
    with registry.lock:
        st.last_ok_utc = datetime.now(UTC)
        st.last_rows = n
        st.last_error = None
    return n


def backfill(
    client: EnerginetClient,
    store: Store,
    topology: Topology,
    *,
    days_5min: int,
    weeks_hourly: int,
    pause_s: float = 0.5,
) -> dict[str, int]:
    """One-off history load: 5-min datasets in daily chunks, hourly/15-min in weekly chunks."""
    corridors = corridor_map(topology)
    now = datetime.now(UTC)
    written: dict[str, int] = {}

    def write(key: str, samples) -> None:
        with store.cursor() as cur:
            written[key] = written.get(key, 0) + upsert_samples(cur, samples)
        time.sleep(pause_s)

    for d in range(days_5min, -1, -1):
        s, e = now - timedelta(days=d + 1), now - timedelta(days=d)
        write(
            "prodex",
            normalize_prodex(
                client.fetch("ElectricityProdex5MinRealtime", start=s, end=e, price_areas=DK_ZONES),
                corridors,
            ),
        )
        write("co2", normalize_co2(client.fetch("CO2Emis", start=s, end=e, price_areas=DK_ZONES)))
    for w in range(weeks_hourly, -1, -1):
        s, e = now - timedelta(weeks=w + 1), now - timedelta(weeks=w) + timedelta(days=2)
        write(
            "genprodtype",
            normalize_genprodtype(
                client.fetch("GenerationProdTypeExchange", start=s, end=e, price_areas=DK_ZONES)
            ),
        )
        write(
            "dayahead",
            normalize_dayahead(
                client.fetch("DayAheadPrices", start=s, end=e, price_areas=DK_ZONES), set(DK_ZONES)
            ),
        )
    return written
