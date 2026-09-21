"""Boundary invariants of the canonical schema (MVP.md §5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from emap.schema import Edge, Node, Sample

CPH = timezone(timedelta(hours=2))  # CEST


def _sample(**over):
    base = dict(
        entity_id="DK1",
        entity_kind="node",
        quantity="demand",
        t_utc=datetime(2026, 9, 21, 12, 0, tzinfo=CPH),
        value=2500.0,
        unit="MW",
        source="energinet",
        resolution="PT5M",
        quality="measured",
    )
    base.update(over)
    return Sample(**base)


def test_sample_normalizes_to_utc():
    s = _sample()
    assert s.t_utc == datetime(2026, 9, 21, 10, 0, tzinfo=UTC)
    assert s.t_utc.utcoffset() == timedelta(0)


def test_sample_rejects_naive_timestamp():
    with pytest.raises(ValidationError):
        _sample(t_utc=datetime(2026, 9, 21, 12, 0))


def test_sample_rejects_unknown_vocabulary():
    for bad in (
        dict(quantity="megawatts"),
        dict(unit="kW"),
        dict(source="csv"),
        dict(quality="ok"),
    ):
        with pytest.raises(ValidationError):
            _sample(**bad)


def test_sample_rejects_non_finite_value():
    with pytest.raises(ValidationError):
        _sample(value=float("nan"))
    with pytest.raises(ValidationError):
        _sample(value=float("inf"))


def test_sample_missing_iff_none():
    assert _sample(value=None, quality="missing").value is None
    with pytest.raises(ValidationError):
        _sample(value=None, quality="measured")
    with pytest.raises(ValidationError):
        _sample(value=1.0, quality="missing")


def test_node_shape_and_bounds():
    n = Node(id="b1", kind="grid", name="Bus 1", zone="DK1", lat=56.0, lon=9.5, cluster={0: "DK1"})
    assert n.cluster[0] == "DK1" and n.capacity_mw is None
    with pytest.raises(ValidationError):
        Node(id="b1", kind="grid", name="x", zone="DK1", lat=95.0, lon=0.0)
    with pytest.raises(ValidationError):
        Node(id="b1", kind="plant", name="x", zone="DK1", lat=0.0, lon=0.0)


def test_edge_uses_from_alias_in_json():
    e = Edge(**{"id": "l1", "from": "a", "to": "b", "kind": "ac_line", "rating_mw": 100.0})
    assert e.from_ == "a"
    assert e.model_dump()["from"] == "a"
    assert Edge.model_validate_json(e.model_dump_json()) == e
