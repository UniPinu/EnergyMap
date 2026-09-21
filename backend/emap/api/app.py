"""FastAPI application — service B's public surface (IMPLEMENTATION_PLAN.md §1).

The browser talks only to this API. Energinet / ENTSO-E are never reached from
the client; they are pulled by server-side ingesters (later phases) into the
store this API reads from.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AwareDatetime, BaseModel

from emap import __version__
from emap.analytics.models import State
from emap.analytics.series import SeriesResponse, series
from emap.analytics.state import compute_state
from emap.config import Settings, get_settings
from emap.ingest.energinet import EnerginetClient
from emap.ingest.jobs import JobStatus, Registry, build_jobs
from emap.ingest.scheduler import start_scheduler
from emap.schema import Quantity, Sample, Source
from emap.store import Store, open_store, query_samples
from emap.topology import Topology, load_topology


class MigrationInfo(BaseModel):
    version: int
    name: str
    applied_at: AwareDatetime


class DbHealth(BaseModel):
    path: str
    migrations: list[MigrationInfo]


class Health(BaseModel):
    status: str
    version: str
    time_utc: AwareDatetime
    db: DbHealth


def _store_dep(request: Request) -> Store:
    return request.app.state.store


StoreDep = Annotated[Store, Depends(_store_dep)]


def _topology_dep(request: Request) -> Topology:
    return request.app.state.topology


TopologyDep = Annotated[Topology, Depends(_topology_dep)]


def create_app(
    settings: Settings | None = None,
    store: Store | None = None,
    topology: Topology | None = None,
) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owned = store is None
        app.state.store = store or open_store(settings.emap_db_path)
        # Validated once at startup: a broken artifact fails the boot, never a request.
        app.state.topology = topology or load_topology(settings.emap_topology_path)
        app.state.registry = Registry()
        scheduler = client = None
        if settings.emap_ingest_enabled:
            client = EnerginetClient()
            jobs = build_jobs(client, app.state.store, app.state.topology)
            scheduler = start_scheduler(jobs, app.state.registry)
        try:
            yield
        finally:
            if scheduler is not None:
                scheduler.shutdown(wait=False)
            if client is not None:
                client.close()
            if owned:
                app.state.store.close()

    app = FastAPI(
        title="Northern European Electricity Balance Terminal — API",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=Health, tags=["meta"])
    def health(store: StoreDep) -> Health:
        return Health(
            status="ok",
            version=__version__,
            time_utc=datetime.now(UTC),
            db=DbHealth(
                path=str(store.path),
                migrations=[
                    MigrationInfo(version=v, name=n, applied_at=t) for v, n, t in store.applied()
                ],
            ),
        )

    @app.get("/api/topology", response_model=Topology, tags=["topology"])
    def get_topology(topo: TopologyDep) -> Topology:
        """The static network: canonical nodes/edges at the finest level plus the precomputed
        cluster views for coarser levels (service A artifact, validated at startup)."""
        return topo

    @app.get("/api/state", response_model=State, tags=["state"])
    def get_state(store: StoreDep, topo: TopologyDep, t: AwareDatetime | None = None) -> State:
        """Per-node state vectors (MVP.md §3.2), corridor flows, zone totals + raw residual and
        cluster aggregates at instant t (default: now, floored to the 5-min grid)."""
        with store.cursor() as cur:
            return compute_state(topo, cur, t)

    @app.get("/api/series", response_model=SeriesResponse, tags=["series"])
    def get_series(
        store: StoreDep,
        topo: TopologyDep,
        entity_id: Annotated[str, Query(min_length=1)],
        quantity: Quantity,
        start: AwareDatetime | None = None,
        end: AwareDatetime | None = None,
    ) -> SeriesResponse:
        """Time series for any entity: stored rows for zones / classes / corridors, derived
        (distribution rule) for DK plant, dg and load nodes. Default window: last 31 days."""
        end = end or datetime.now(UTC)
        start = start or end - timedelta(days=31)
        if start >= end:
            raise HTTPException(status_code=422, detail="start must be before end")
        with store.cursor() as cur:
            return series(topo, cur, entity_id, quantity, start, end)

    @app.get("/api/ingest/status", response_model=list[JobStatus], tags=["meta"])
    def ingest_status(request: Request) -> list[JobStatus]:
        """Last run / rows / error per scheduled ingestion job."""
        return request.app.state.registry.snapshot()

    @app.get("/api/samples", response_model=list[Sample], tags=["series"])
    def samples(
        store: StoreDep,
        entity_id: Annotated[str, Query(min_length=1)],
        quantity: Quantity,
        start: AwareDatetime | None = None,
        end: AwareDatetime | None = None,
        source: Source | None = None,
    ) -> list[Sample]:
        """Canonical `Sample` rows for one (entity, quantity) in [start, end). Default: last 24h."""
        end = end or datetime.now(UTC)
        start = start or end - timedelta(hours=24)
        if start >= end:
            raise HTTPException(status_code=422, detail="start must be before end")
        with store.cursor() as cur:
            return query_samples(
                cur, entity_id=entity_id, quantity=quantity, start=start, end=end, source=source
            )

    return app


app = create_app()
