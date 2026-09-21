"""API shell: health reports migrations; /api/samples reads the canonical table."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from emap.api import create_app
from emap.config import Settings
from emap.schema import Sample
from emap.store import upsert_samples
from emap.store.db import Store

T0 = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)


@pytest.fixture
def client(store: Store):
    app = create_app(settings=Settings(_env_file=None), store=store)
    with TestClient(app) as c:
        yield c


def _price(i: int) -> Sample:
    return Sample(
        entity_id="DK1",
        entity_kind="node",
        quantity="price",
        t_utc=T0 + timedelta(hours=i),
        value=50.0 + i,
        unit="EUR/MWh",
        source="energinet",
        resolution="PT60M",
        quality="measured",
    )


def test_health_lists_migrations(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert [m["version"] for m in body["db"]["migrations"]] == [1]
    assert body["time_utc"].endswith("Z") or "+00:00" in body["time_utc"]


def test_samples_endpoint_round_trips(client: TestClient, store: Store):
    with store.cursor() as cur:
        upsert_samples(cur, [_price(i) for i in range(3)])
    params = {
        "entity_id": "DK1",
        "quantity": "price",
        "start": T0.isoformat(),
        "end": (T0 + timedelta(hours=2)).isoformat(),
    }
    r = client.get("/api/samples", params=params)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert [x["value"] for x in rows] == [50.0, 51.0]
    assert rows[0]["t_utc"].startswith("2026-09-21T10:00:00")
    assert all(x["t_utc"].endswith("Z") for x in rows)


def test_samples_rejects_bad_vocab_and_naive_time(client: TestClient):
    bad_vocab = {"entity_id": "DK1", "quantity": "nope"}
    assert client.get("/api/samples", params=bad_vocab).status_code == 422
    naive = {"entity_id": "DK1", "quantity": "price", "start": "2026-09-21T10:00:00"}
    assert client.get("/api/samples", params=naive).status_code == 422


def test_samples_rejects_inverted_window(client: TestClient):
    params = {
        "entity_id": "DK1",
        "quantity": "price",
        "start": (T0 + timedelta(hours=1)).isoformat(),
        "end": T0.isoformat(),
    }
    assert client.get("/api/samples", params=params).status_code == 422
