"""/api/state, /api/series and /api/ingest/status over the synthetic DK1 sample set."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from emap.api import create_app
from emap.config import Settings, get_settings
from emap.store.db import Store
from emap.topology import load_topology
from tests.test_state import T, seed


@pytest.fixture(scope="module")
def topo():
    return load_topology(get_settings().emap_topology_path)


@pytest.fixture
def client(store: Store, topo):
    seed(store, topo)
    app = create_app(
        settings=Settings(_env_file=None, emap_ingest_enabled=False), store=store, topology=topo
    )
    with TestClient(app) as c:
        yield c


def test_state_endpoint(client: TestClient, topo):
    r = client.get("/api/state", params={"t": T.isoformat()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["t_utc"].startswith("2026-09-21T17:00:00") and body["step"] == "PT5M"
    z = body["zones"]["DK1"]
    assert z["live"] and z["p_gen"] == 3700.0 and z["residual"] == pytest.approx(400.0)
    assert body["zones"]["DK2"]["live"] is False
    horns = next(n for n in topo.nodes if n.name.startswith("Horns Rev"))
    ns = body["nodes"][horns.id]
    assert ns["kind"] == "source" and ns["p_gen"] is not None and 0 <= ns["u"] <= 1
    rec = z["reconciled"]
    assert rec["p_gen"] - rec["demand"] - rec["exchange"] == pytest.approx(0.0, abs=1e-6)
    assert body["clusters"]["0"]["DK1"]["net_injection"] == pytest.approx(rec["exchange"])
    assert client.get("/api/state", params={"t": "2026-09-21T17:00:00"}).status_code == 422  # naive


def test_series_stored_and_derived(client: TestClient, topo):
    win = {
        "start": (T - timedelta(hours=2)).isoformat(),
        "end": (T + timedelta(minutes=5)).isoformat(),
    }
    r = client.get("/api/series", params={"entity_id": "DK1", "quantity": "demand", **win})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["unit"] == "MW" and body["derived_from"] is None
    assert [p["v"] for p in body["points"]] == [2240.0, 2800.0]
    # derived load series = zone demand × key
    load = next(n for n in topo.nodes if n.kind == "consumption" and n.zone == "DK1")
    r = client.get("/api/series", params={"entity_id": load.id, "quantity": "demand", **win})
    body = r.json()
    assert body["derived_from"].startswith("DK1 demand") and len(body["points"]) == 2
    assert body["points"][1]["v"] == pytest.approx(2800.0 * load.dist_key, rel=1e-3)
    # derived plant series is capped at nameplate and proportional otherwise
    horns = next(n for n in topo.nodes if n.name.startswith("Horns Rev"))
    body = client.get(
        "/api/series", params={"entity_id": horns.id, "quantity": "p_gen", **win}
    ).json()
    assert "capped" in body["derived_from"] and all(
        p["v"] <= horns.capacity_mw + 1e-9 for p in body["points"]
    )
    # price series for the zone
    body = client.get("/api/series", params={"entity_id": "DK1", "quantity": "price", **win}).json()
    assert body["unit"] == "EUR/MWh" and body["points"][0]["v"] == 90.0


def test_ingest_status_is_empty_when_disabled(client: TestClient):
    assert client.get("/api/ingest/status").json() == []
