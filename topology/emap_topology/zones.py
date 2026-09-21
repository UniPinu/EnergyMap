"""Bus/plant → bidding-zone assignment.

Rule: a point's ISO country selects the candidate zones (COUNTRY_ZONES); with one candidate the
answer is immediate; otherwise the containing polygon wins; a point in no candidate polygon
(offshore wind farms, coastal substations) goes to the *nearest* candidate polygon, provided it
lies within MAX_SNAP_DEG of it — anything farther (Faroe Islands, Greenland, Svalbard, which
the plant DB files under their sovereign country) is not modelled.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import shapely
from shapely.geometry.base import BaseGeometry

from .config import COUNTRY_ZONES, ZONE_OVERRIDE_BOXES, ZONES

MAX_SNAP_DEG = 0.75  # ~50-80 km at these latitudes; the farthest DK offshore farm is ~45 km out


def assign_zone(
    lon: float, lat: float, country: str, polygons: dict[str, BaseGeometry]
) -> str | None:
    cands = COUNTRY_ZONES.get(country)
    if not cands:
        return None
    for ctry, zone, (x0, y0, x1, y1) in ZONE_OVERRIDE_BOXES:
        if ctry == country and x0 <= lon <= x1 and y0 <= lat <= y1:
            return zone
    if len(cands) == 1:
        return cands[0]
    pt = shapely.Point(lon, lat)
    for z in cands:
        if z in polygons and polygons[z].contains(pt):
            return z
    with_poly = [z for z in cands if z in polygons]
    if not with_poly:
        return None
    best = min(with_poly, key=lambda z: polygons[z].distance(pt))
    return best if polygons[best].distance(pt) <= MAX_SNAP_DEG else None


def assign_zones(
    df: pd.DataFrame, polygons: dict[str, BaseGeometry], *, lon="x", lat="y", country="country"
) -> pd.Series:
    """Vectorised over a frame with lon/lat/country columns; NaN where no zone is modelled."""
    out = pd.Series(index=df.index, dtype="object")
    for ctry, sub in df.groupby(country):
        cands = COUNTRY_ZONES.get(str(ctry))
        if not cands:
            continue
        if len(cands) == 1:
            out.loc[sub.index] = cands[0]
            continue
        xs, ys = sub[lon].to_numpy(float), sub[lat].to_numpy(float)
        chosen = np.full(len(sub), None, dtype=object)
        for octry, ozone, (x0, y0, x1, y1) in ZONE_OVERRIDE_BOXES:
            if octry == ctry:
                box = (xs >= x0) & (xs <= x1) & (ys >= y0) & (ys <= y1)
                chosen[(chosen == None) & box] = ozone  # noqa: E711
        for z in cands:
            if z not in polygons:
                continue
            inside = shapely.contains_xy(polygons[z], xs, ys)
            chosen[(chosen == None) & inside] = z  # noqa: E711 — first containing zone wins
        missing = chosen == None  # noqa: E711
        if missing.any():
            with_poly = [z for z in cands if z in polygons]
            pts = shapely.points(xs[missing], ys[missing])
            dists = np.column_stack([polygons[z].distance(pts) for z in with_poly])
            best = np.array(with_poly, dtype=object)[dists.argmin(axis=1)]
            best[dists.min(axis=1) > MAX_SNAP_DEG] = None
            chosen[missing] = best
        out.loc[sub.index] = chosen
    return out.astype(object).where(out.notna(), None)


def zone_anchor(zone_id: str, polygons: dict[str, BaseGeometry]) -> tuple[float, float]:
    """(lat, lon) for the zone super-node: a point guaranteed inside the polygon, else the
    configured centroid."""
    z = ZONES[zone_id]
    if zone_id in polygons:
        p = polygons[zone_id].representative_point()
        return (float(p.y), float(p.x))
    if z.centroid is None:
        raise ValueError(f"zone {zone_id} has neither polygon nor centroid")
    return z.centroid
