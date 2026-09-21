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
from emap.config import Settings, get_settings
from emap.schema import Quantity, Sample, Source
from emap.store import Store, open_store, query_samples


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


def create_app(settings: Settings | None = None, store: Store | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owned = store is None
        app.state.store = store or open_store(settings.emap_db_path)
        try:
            yield
        finally:
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
