"""Pinned inputs, zone registry and build parameters."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work"
DATA = ROOT / "data"
ARTIFACTS = ROOT / "artifacts"

# --- Pinned upstream datasets (URLs taken from PyPSA-Eur data/versions.csv) -----------------
OSM_VERSION = "0.7"
OSM_BASE = f"https://data.pypsa.org/workflows/eur/osm/{OSM_VERSION}"
OSM_FILES = ("buses", "lines", "links", "converters", "transformers")
PPM_VERSION = "0.8.1"
PPM_URL = (
    "https://raw.githubusercontent.com/PyPSA/powerplantmatching/"
    f"refs/tags/v{PPM_VERSION}/powerplants.csv"
)
ENTSOE_PY_VERSION = "V0.6.18"
ENTSOE_GEO_BASE = (
    f"https://raw.githubusercontent.com/EnergieID/entsoe-py/{ENTSOE_PY_VERSION}/entsoe/geo/geojson"
)


@dataclass(frozen=True)
class Zone:
    id: str
    name: str
    country: str
    geojson: str | None  # entsoe-py file stem, None when no polygon is shipped
    detail: bool = False  # True → buses/plants/loads are modelled (DK); False → one super-node
    centroid: tuple[float, float] | None = None  # (lat, lon) fallback when no polygon


# MVP.md §2.3: DK1 + DK2 at bus granularity; neighbours as single zone super-nodes.
# All NO/SE bidding zones are included so the Nordic corridor is connected end-to-end.
ZONES: dict[str, Zone] = {
    z.id: z
    for z in (
        Zone("DK1", "Denmark West", "DK", "DK_1", detail=True),
        Zone("DK2", "Denmark East", "DK", "DK_2", detail=True),
        Zone("DE_LU", "Germany / Luxembourg", "DE", "DE_LU"),
        Zone("NL", "Netherlands", "NL", "NL"),
        Zone("GB", "Great Britain", "GB", None, centroid=(52.6, -1.5)),  # no polygon in entsoe-py
        Zone("NO1", "Norway East", "NO", "NO_1"),
        Zone("NO2", "Norway South", "NO", "NO_2"),
        Zone("NO3", "Norway Mid", "NO", "NO_3"),
        Zone("NO4", "Norway North", "NO", "NO_4"),
        Zone("NO5", "Norway West", "NO", "NO_5"),
        Zone("SE1", "Sweden North", "SE", "SE_1"),
        Zone("SE2", "Sweden North-Mid", "SE", "SE_2"),
        Zone("SE3", "Sweden South-Mid", "SE", "SE_3"),
        Zone("SE4", "Sweden South", "SE", "SE_4"),
        Zone("PL", "Poland", "PL", "PL"),
        Zone("FI", "Finland", "FI", "FI"),
        Zone("EE", "Estonia", "EE", "EE"),
        Zone("LV", "Latvia", "LV", "LV"),
        Zone("LT", "Lithuania", "LT", "LT"),
    )
}

# Bornholm is bidding zone DK2 but the entsoe-py DK_2 polygon stops at Zealand; points of
# country DK inside this (lon_min, lat_min, lon_max, lat_max) box are forced to DK2.
ZONE_OVERRIDE_BOXES: list[tuple[str, str, tuple[float, float, float, float]]] = [
    ("DK", "DK2", (14.55, 54.95, 15.25, 55.35)),
]

# ISO country of a bus → candidate zones (LU is part of DE_LU).
COUNTRY_ZONES: dict[str, list[str]] = {}
for _z in ZONES.values():
    COUNTRY_ZONES.setdefault(_z.country, []).append(_z.id)
COUNTRY_ZONES["LU"] = ["DE_LU"]

# powerplantmatching country names
PPM_COUNTRY: dict[str, str] = {
    "DK": "Denmark",
    "DE": "Germany",
    "LU": "Luxembourg",
    "NL": "Netherlands",
    "GB": "United Kingdom",
    "NO": "Norway",
    "SE": "Sweden",
    "PL": "Poland",
    "FI": "Finland",
    "EE": "Estonia",
    "LV": "Latvia",
    "LT": "Lithuania",
}


@dataclass(frozen=True)
class BuildParams:
    plant_min_mw: float = 20.0  # DK plants below this are not modelled individually
    storage_min_mw: float = 1.0
    as_of_year: int = 2026  # plants with DateOut < as_of_year are treated as retired
    dk_clusters: dict[str, int] = field(default_factory=lambda: {"DK1": 6, "DK2": 4})  # Π₁
    kmeans_seed: int = 0
    satellite_offset_deg: tuple[float, float] = (0.22, -0.14)  # (dlon, dlat) for load nodes


PARAMS = BuildParams()

# Storage classification in powerplantmatching (Set == 'Store'): bidirectional technologies only.
STORAGE_FUELTYPES = {"Battery", "Hydrogen Storage", "Mechanical Storage"}
STORAGE_TECHS = {("Hydro", "Pumped Storage")}
