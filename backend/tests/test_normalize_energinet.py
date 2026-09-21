"""Energinet rows -> canonical samples: entities, grid expansion, units, corridor signs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from emap.ingest.energinet import CO2EmisRow, DayAheadPriceRow, GenProdTypeRow, ProdexRow
from emap.normalize.energinet import (
    corridor_map,
    normalize_co2,
    normalize_dayahead,
    normalize_genprodtype,
    normalize_prodex,
)
from emap.normalize.grid import expand, floor_to_grid

T0 = datetime(2026, 9, 21, 17, 0, tzinfo=UTC)

CORRIDORS = {  # as corridor_map() derives them from the artifact
    ("DK1", "DE_LU"): ("ic:dk1-de", -1.0),
    ("DK1", "DK2"): ("link:greatbelt", -1.0),
    ("DK2", "SE4"): ("ic:dk2-se4", -1.0),
    ("DK2", "DE_LU"): ("ic:dk2-de", -1.0),
}


def _prodex(zone: str, **over) -> ProdexRow:
    base = dict(
        Minutes5UTC="2026-09-21T17:00:00", PriceArea=zone, ProductionLt100MW=100.0,
        ProductionGe100MW=200.0, OffshoreWindPower=300.0, OnshoreWindPower=400.0, SolarPower=50.0,
        ExchangeGreatBelt=-15.0, ExchangeGermany=-900.0, ExchangeSweden=600.0, BornholmSE4=None,
    )  # fmt: skip
    base.update(over)
    return ProdexRow.model_validate(base)


def test_grid_helpers():
    assert floor_to_grid(datetime(2026, 1, 1, 10, 7, 30, tzinfo=UTC)) == datetime(
        2026, 1, 1, 10, 5, tzinfo=UTC
    )
    slots = list(expand(T0, "PT60M"))
    assert len(slots) == 12 and slots[0] == (T0, "measured") and slots[1][1] == "interpolated"
    assert slots[-1][0] == T0 + timedelta(minutes=55)
    assert [q for _, q in expand(T0, "PT15M")] == ["measured", "interpolated", "interpolated"]
    assert list(expand(T0, "PT5M")) == [(T0, "measured")]


def test_prodex_classes_total_and_corridor_signs():
    out = normalize_prodex([_prodex("DK1")], CORRIDORS)
    by = {(s.entity_id, s.quantity): s for s in out}
    assert by[("DK1|wind_offshore", "p_gen")].value == 300.0
    assert by[("DK1|thermal_lt100", "p_gen")].value == 100.0
    assert by[("DK1", "p_gen")].value == pytest.approx(1050.0)  # Σ classes
    # import-positive -900 (export to DE) -> corridor DK bus -> DE hub carries +900
    assert (
        by[("ic:dk1-de", "flow")].value == 900.0 and by[("ic:dk1-de", "flow")].entity_kind == "edge"
    )
    # Great Belt: DK1 import -15 -> DK1 exports 15 toward DK2 -> +15 on the Funen->Zealand link
    assert by[("link:greatbelt", "flow")].value == 15.0
    assert all(
        s.source == "energinet" and s.resolution == "PT5M" and s.quality == "measured" for s in out
    )
    assert all(s.t_utc == T0 for s in out)


def test_prodex_dk2_folds_bornholm_and_skips_great_belt():
    out = normalize_prodex(
        [_prodex("DK2", ExchangeSweden=300.0, BornholmSE4=-20.0, ExchangeGreatBelt=15.0)], CORRIDORS
    )
    by = {(s.entity_id, s.quantity): s for s in out}
    assert by[("ic:dk2-se4", "flow")].value == -(300.0 - 20.0)
    assert ("link:greatbelt", "flow") not in by  # only DK1's column feeds the Great Belt
    assert by[("ic:dk2-de", "flow")].value == 900.0


def test_prodex_missing_columns_are_skipped_not_zeroed():
    out = normalize_prodex([_prodex("DK1", SolarPower=None, ExchangeGermany=None)], CORRIDORS)
    ids = {(s.entity_id, s.quantity) for s in out}
    assert ("DK1|solar", "p_gen") not in ids and ("ic:dk1-de", "flow") not in ids
    assert next(s for s in out if s.entity_id == "DK1").value == 1000.0


def test_genprodtype_expands_hourly_demand():
    row = GenProdTypeRow.model_validate(
        {"TimeUTC": "2026-09-21T17:00:00", "PriceArea": "DK1", "GrossCon": 2799.0}
    )
    out = normalize_genprodtype([row])
    assert len(out) == 12 and {s.quantity for s in out} == {"demand"}
    assert out[0].quality == "measured" and out[1].quality == "interpolated"
    assert all(s.resolution == "PT60M" and s.value == 2799.0 and s.unit == "MW" for s in out)
    assert (
        normalize_genprodtype(
            [GenProdTypeRow.model_validate({"TimeUTC": "2026-09-21T17:00:00", "PriceArea": "DK1"})]
        )
        == []
    )


def test_dayahead_keeps_only_requested_zones_and_expands_15min():
    rows = [
        DayAheadPriceRow.model_validate(
            {"TimeUTC": "2026-09-21T17:00:00", "PriceArea": a, "DayAheadPriceEUR": 100.0}
        )
        for a in ("DK1", "DE", "NO2")
    ]
    out = normalize_dayahead(rows, {"DK1", "DK2"})
    assert len(out) == 3 and {s.entity_id for s in out} == {"DK1"}
    assert out[0].unit == "EUR/MWh" and out[0].resolution == "PT15M"


def test_co2_converts_g_per_kwh_to_t_per_mwh():
    out = normalize_co2(
        [
            CO2EmisRow.model_validate(
                {"Minutes5UTC": "2026-09-21T17:05:00", "PriceArea": "DK2", "CO2Emission": 28.0}
            )
        ]
    )
    assert (
        out[0].value == pytest.approx(0.028)
        and out[0].unit == "tCO2/MWh"
        and out[0].quantity == "co2_intensity"
    )


def test_corridor_map_from_real_artifact():
    from emap.config import get_settings
    from emap.topology import load_topology

    cm = corridor_map(load_topology(get_settings().emap_topology_path))
    assert set(cm) == {
        ("DK1", "DE_LU"),
        ("DK1", "DK2"),
        ("DK1", "GB"),
        ("DK1", "NL"),
        ("DK1", "NO2"),
        ("DK1", "SE3"),
        ("DK2", "DE_LU"),
        ("DK2", "SE4"),
    }
    assert all(sign == -1.0 for _, sign in cm.values())
