"""Fetch the pinned upstream files into work/ and fingerprint them for the artifact's provenance."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

from .config import (
    ENTSOE_GEO_BASE,
    ENTSOE_PY_VERSION,
    OSM_BASE,
    OSM_FILES,
    OSM_VERSION,
    PPM_URL,
    PPM_VERSION,
    WORK,
    ZONES,
)


def osm_dir() -> Path:
    return WORK / f"osm-{OSM_VERSION}"


def ppm_path() -> Path:
    return WORK / f"powerplants-{PPM_VERSION}.csv"


def zones_dir() -> Path:
    return WORK / "bidding_zones"


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    req = urllib.request.Request(url, headers={"User-Agent": "energymap-topology-build/0.1"})
    with urllib.request.urlopen(req, timeout=600) as r, dest.open("wb") as f:  # noqa: S310
        while chunk := r.read(1 << 20):
            f.write(chunk)


def fetch_all() -> list[Path]:
    got: list[Path] = []
    for name in OSM_FILES:
        p = osm_dir() / f"{name}.csv"
        _download(f"{OSM_BASE}/{name}.csv", p)
        got.append(p)
    _download(PPM_URL, ppm_path())
    got.append(ppm_path())
    for z in ZONES.values():
        if z.geojson:
            p = zones_dir() / f"{z.geojson}.geojson"
            _download(f"{ENTSOE_GEO_BASE}/{z.geojson}.geojson", p)
            got.append(p)
    return got


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def provenance() -> list[dict[str, str]]:
    """One record per input file: dataset, version, url, sha256 — embedded in topology.json."""
    rows: list[dict[str, str]] = []
    for name in OSM_FILES:
        p = osm_dir() / f"{name}.csv"
        rows.append(
            {
                "dataset": f"pypsa-eur osm-prebuilt {name}",
                "version": OSM_VERSION,
                "license": "ODbL-1.0",
                "url": f"{OSM_BASE}/{name}.csv",
                "sha256": sha256(p),
            }
        )
    rows.append(
        {
            "dataset": "powerplantmatching powerplants.csv",
            "version": PPM_VERSION,
            "license": "GPL-3.0 (data: see powerplantmatching)",
            "url": PPM_URL,
            "sha256": sha256(ppm_path()),
        }
    )
    for z in ZONES.values():
        if z.geojson:
            p = zones_dir() / f"{z.geojson}.geojson"
            rows.append(
                {
                    "dataset": f"entsoe-py bidding zone {z.geojson}",
                    "version": ENTSOE_PY_VERSION,
                    "license": "MIT (entsoe-py)",
                    "url": f"{ENTSOE_GEO_BASE}/{z.geojson}.geojson",
                    "sha256": sha256(p),
                }
            )
    return rows


if __name__ == "__main__":
    for p in fetch_all():
        print(p)
    print(json.dumps(provenance(), indent=1))
