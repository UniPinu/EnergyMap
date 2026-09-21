"""Readers for the pinned inputs (parsed the way PyPSA-Eur base_network.py reads them)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .config import DATA, PPM_COUNTRY, ZONES
from .sources import osm_dir, ppm_path, zones_dir

_READ = dict(quotechar="'", true_values=["t"], false_values=["f"])


def read_osm(directory: Path | None = None) -> dict[str, pd.DataFrame]:
    d = directory or osm_dir()
    skip_geom = lambda c: c != "geometry"  # noqa: E731 — 20 MB of LINESTRINGs we never use
    return {
        "buses": pd.read_csv(d / "buses.csv", usecols=skip_geom, **_READ).set_index("bus_id"),
        "lines": pd.read_csv(d / "lines.csv", usecols=skip_geom, **_READ).set_index("line_id"),
        "links": pd.read_csv(d / "links.csv", usecols=skip_geom, **_READ).set_index("link_id"),
        "converters": pd.read_csv(d / "converters.csv", usecols=skip_geom, **_READ).set_index(
            "converter_id"
        ),
        "transformers": pd.read_csv(d / "transformers.csv", usecols=skip_geom, **_READ).set_index(
            "transformer_id"
        ),
    }


def read_plants(path: Path | None = None) -> pd.DataFrame:
    """powerplantmatching rows for the modelled countries, with an ISO country column."""
    p = pd.read_csv(path or ppm_path())
    inv = {v: k for k, v in PPM_COUNTRY.items()}
    p = p[p.Country.isin(inv)].copy()
    p["iso"] = p.Country.map(inv)
    p = p.dropna(subset=["lat", "lon"])
    p["id"] = p["id"].astype(int)
    return p.set_index("id")


def read_zone_polygons(directory: Path | None = None) -> dict[str, BaseGeometry]:
    d = directory or zones_dir()
    polys: dict[str, BaseGeometry] = {}
    for z in ZONES.values():
        if not z.geojson:
            continue
        gj = json.loads((d / f"{z.geojson}.geojson").read_text(encoding="utf-8"))
        feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
        polys[z.id] = unary_union([shape(f["geometry"]) for f in feats])
    return polys


def read_bus_names() -> dict[str, str]:
    p = DATA / "osm_bus_names.json"
    return json.loads(p.read_text(encoding="utf-8"))["names"] if p.exists() else {}
