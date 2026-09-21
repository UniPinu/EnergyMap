"""Derived residual rows: only where the identity can be formed; values match §3.4."""

from __future__ import annotations

from datetime import timedelta

import pytest

from emap.analytics.derive import derive_residuals
from emap.config import get_settings
from emap.store import query_samples, upsert_samples
from emap.store.db import Store
from emap.topology import load_topology
from tests.test_state import T, seed


@pytest.fixture(scope="module")
def topo():
    return load_topology(get_settings().emap_topology_path)


def test_residual_rows_match_the_identity(store: Store, topo):
    seed(store, topo)  # DK1 at T−1h (×0.8) and T; DK2 empty
    with store.cursor() as cur:
        rows = derive_residuals(cur, topo, T - timedelta(hours=2), T + timedelta(minutes=5))
        upsert_samples(cur, rows)
        got = query_samples(
            cur,
            entity_id="DK1",
            quantity="residual",
            start=T - timedelta(hours=2),
            end=T + timedelta(minutes=5),
        )
        hat = query_samples(
            cur,
            entity_id="DK1",
            quantity="residual_hat",
            start=T - timedelta(hours=2),
            end=T + timedelta(minutes=5),
        )
        none = query_samples(
            cur,
            entity_id="DK2",
            quantity="residual",
            start=T - timedelta(hours=2),
            end=T + timedelta(minutes=5),
        )
    assert [r.value for r in got] == pytest.approx([400.0 * 0.8, 400.0])  # r = gen − load − X
    assert [r.value for r in hat] == pytest.approx([400.0 / 2800.0, 400.0 / 2800.0])
    assert all(r.source == "derived" and r.quality == "measured" for r in got)
    assert none == []  # DK2 has no inputs → no residual, never a fake zero


def test_missing_flow_prevents_the_row(store: Store, topo):
    seed(store, topo)
    with store.cursor() as cur:
        # remove one corridor flow at T: the identity cannot be formed at T any more
        cur.execute(
            "DELETE FROM samples WHERE quantity = 'flow' AND t_utc = ? AND entity_id LIKE '%NO2'",
            [T],
        )
        rows = derive_residuals(cur, topo, T - timedelta(hours=2), T + timedelta(minutes=5))
    assert [r.t_utc for r in rows if r.quantity == "residual"] == [T - timedelta(hours=1)]
