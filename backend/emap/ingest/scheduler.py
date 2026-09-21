"""In-process ingestion schedule (APScheduler). Runs inside the single uvicorn worker that owns
the DuckDB file; each job fires at its dataset's update frequency (CONTEXT.md §2.1)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from emap.ingest.jobs import Job, Registry, run_job

log = logging.getLogger(__name__)


def start_scheduler(jobs: list[Job], registry: Registry) -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="UTC", job_defaults={"coalesce": True, "max_instances": 1})
    for i, job in enumerate(jobs):
        # stagger the first runs a few seconds apart instead of hammering the source at boot
        first = datetime.now(UTC) + timedelta(seconds=2 + 3 * i)
        sched.add_job(
            run_job, "interval", seconds=job.interval_s, args=[job, registry], id=job.name,
            next_run_time=first,
        )  # fmt: skip
    sched.start()
    log.info("ingestion scheduler started with %d jobs", len(jobs))
    return sched
