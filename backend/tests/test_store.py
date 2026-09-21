"""Store: migrations are idempotent; samples round-trip in UTC; upsert replaces."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from emap.schema import Sample
from emap.store import query_samples, upsert_samples
from emap.store.db import Store, discover_migrations

T0 = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)
H1 = timedelta(hours=1)


def _s(i: int, value: float | None = 1.0, **over) -> Sample:
    base = dict(
        entity_id="DK1",
        entity_kind="node",
        quantity="demand",
        t_utc=T0 + timedelta(minutes=5 * i),
        value=value,
        unit="MW",
        source="energinet",
        resolution="PT5M",
        quality="measured",
    )
    base.update(over)
    return Sample(**base)


def _q(cur, **kw):
    kw.setdefault("start", T0)
    kw.setdefault("end", T0 + H1)
    return query_samples(cur, entity_id="DK1", quantity="demand", **kw)


def test_migrations_apply_once(store: Store):
    versions = [m.version for m in discover_migrations()]
    assert versions and versions == sorted(versions)
    assert [v for v, _, _ in store.applied()] == versions
    assert store.migrate() == []  # idempotent
    assert [v for v, _, _ in store.applied()] == versions


def test_samples_round_trip_utc(store: Store):
    cph = timezone(timedelta(hours=2))
    rows = [_s(0), _s(1, t_utc=datetime(2026, 9, 21, 12, 5, tzinfo=cph))]
    with store.cursor() as cur:
        assert upsert_samples(cur, rows) == 2
        got = _q(cur)
    assert [g.t_utc for g in got] == [T0, T0 + timedelta(minutes=5)]
    assert all(g.t_utc.tzinfo is not None and g.t_utc.utcoffset() == timedelta(0) for g in got)
    assert got == rows


def test_upsert_replaces_on_key_and_dedupes_batch(store: Store):
    with store.cursor() as cur:
        upsert_samples(cur, [_s(0, 1.0)])
        n = upsert_samples(cur, [_s(0, 2.0), _s(0, 3.0)])  # same key twice in one batch
        assert n == 1
        got = _q(cur)
    assert [g.value for g in got] == [3.0]


def test_two_sources_coexist_and_filter(store: Store):
    with store.cursor() as cur:
        upsert_samples(cur, [_s(0, 10.0, source="energinet"), _s(0, 11.0, source="entsoe")])
        both = _q(cur)
        only = _q(cur, source="entsoe")
    assert sorted(b.value for b in both) == [10.0, 11.0]
    assert [o.value for o in only] == [11.0]


def test_missing_quality_stores_null(store: Store):
    with store.cursor() as cur:
        upsert_samples(cur, [_s(0, None, quality="missing")])
        got = _q(cur)
    assert got[0].value is None and got[0].quality == "missing"


def test_window_is_half_open(store: Store):
    with store.cursor() as cur:
        upsert_samples(cur, [_s(0), _s(1), _s(2)])
        got = _q(cur, end=T0 + timedelta(minutes=10))
    assert len(got) == 2
