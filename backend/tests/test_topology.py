"""The committed artifact validates through the canonical models and is served verbatim."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from emap.api import create_app
from emap.config import Settings, get_settings
from emap.store.db import Store
from emap.topology import Topology, load_topology


@pytest.fixture(scope="module")
def topo() -> Topology:
    return load_topology(get_settings().emap_topology_path)


def test_artifact_validates_and_has_all_kinds(topo: Topology):
    kinds = {n.kind for n in topo.nodes}
    assert kinds == {"source", "grid", "consumption", "storage"}
    assert {z.id for z in topo.zones} >= {"DK1", "DK2", "DE_LU", "NO2", "SE3", "SE4", "NL"}
    assert set(topo.views) == {"0", "1"} and topo.meta.finest_level == 2
    assert all(set(n.cluster) == {0, 1, 2} for n in topo.nodes)


def test_integrity_validator_rejects_dangling_edge(topo: Topology):
    raw = topo.model_dump(by_alias=True)
    raw["edges"][0]["to"] = "nope:missing"
    with pytest.raises(ValidationError, match="unknown node"):
        Topology.model_validate(raw)


def test_integrity_validator_rejects_bad_partition(topo: Topology):
    raw = topo.model_dump(by_alias=True)
    raw["views"]["0"]["nodes"][0]["members"].pop()
    with pytest.raises(ValidationError, match="partition"):
        Topology.model_validate(raw)


def test_endpoint_serves_topology(store: Store, topo: Topology):
    app = create_app(
        settings=Settings(_env_file=None, emap_ingest_enabled=False), store=store, topology=topo
    )
    with TestClient(app) as c:
        r = c.get("/api/topology")
    assert r.status_code == 200
    body = r.json()
    assert len(body["nodes"]) == len(topo.nodes) and len(body["edges"]) == len(topo.edges)
    e = body["edges"][0]
    assert "from" in e and "to" in e  # alias preserved on the wire
    assert body["nodes"][0]["cluster"]["0"] in {z["id"] for z in body["zones"]}
