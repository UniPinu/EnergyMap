"""Zone assignment: polygon containment, capped nearest-polygon snapping, override boxes."""

from __future__ import annotations

import pandas as pd
import pytest
from shapely.geometry import box

from emap_topology import zones as Z
from emap_topology.zones import assign_zone, assign_zones

# two unit squares standing in for DK1 (west) and DK2 (east) with a 1° gap between them
POLYS = {"DK1": box(8, 55, 10, 57), "DK2": box(11, 55, 13, 57), "NL": box(3, 51, 7, 54)}


def test_inside_polygon_wins():
    assert assign_zone(9.0, 56.0, "DK", POLYS) == "DK1"
    assert assign_zone(12.0, 56.0, "DK", POLYS) == "DK2"


def test_single_candidate_country_needs_no_polygon():
    assert assign_zone(100.0, 0.0, "NL", POLYS) == "NL"  # far away, still NL
    assert assign_zone(5.0, 52.0, "LU", POLYS) == "DE_LU"  # LU folds into DE_LU


def test_offshore_point_snaps_to_nearest_within_cap():
    # 0.3° west of the DK1 square (Horns Rev-like) -> DK1
    assert assign_zone(7.7, 56.0, "DK", POLYS) == "DK1"
    # in the gap, closer to DK2
    assert assign_zone(10.7, 56.0, "DK", POLYS) == "DK2"


def test_far_point_is_not_modelled():
    assert assign_zone(-6.8, 62.0, "DK", POLYS) is None  # Faroe Islands


def test_override_box_beats_polygons(monkeypatch):
    monkeypatch.setattr(Z, "ZONE_OVERRIDE_BOXES", [("DK", "DK2", (14.55, 54.95, 15.25, 55.35))])
    assert assign_zone(14.9, 55.1, "DK", POLYS) == "DK2"  # Bornholm, > cap from both squares
    assert assign_zone(14.9, 55.1, "SE", POLYS) is None  # box is country-scoped


def test_unmodelled_country():
    assert assign_zone(2.0, 48.0, "FR", POLYS) is None


def test_vectorised_matches_scalar(monkeypatch):
    monkeypatch.setattr(Z, "ZONE_OVERRIDE_BOXES", [("DK", "DK2", (14.55, 54.95, 15.25, 55.35))])
    pts = pd.DataFrame(
        {
            "x": [9.0, 12.0, 7.7, 10.7, -6.8, 14.9, 5.0, 2.0],
            "y": [56.0, 56.0, 56.0, 56.0, 62.0, 55.1, 52.0, 48.0],
            "country": ["DK", "DK", "DK", "DK", "DK", "DK", "NL", "FR"],
        }
    )
    got = assign_zones(pts, POLYS).tolist()
    want = [assign_zone(x, y, c, POLYS) for x, y, c in zip(pts.x, pts.y, pts.country, strict=True)]
    assert got == want == ["DK1", "DK2", "DK1", "DK2", None, "DK2", "NL", None]


@pytest.mark.parametrize("cap", [0.1, 0.75])
def test_cap_is_respected(monkeypatch, cap):
    monkeypatch.setattr(Z, "MAX_SNAP_DEG", cap)
    got = assign_zone(7.7, 56.0, "DK", POLYS)  # 0.3° outside DK1
    assert (got == "DK1") == (cap >= 0.3)
