"""Extract the Danish NUTS3 slice of PyPSA-Eur's pinned Eurostat/GISCO inputs into data/.

The full GISCO zip is ~185 MB; only the DK level-3 polygons and the DK rows of
`nama_10r_3popgdp` (population, THS; GDP, MIO_EUR) are needed, so they are committed as small
derived files with their provenance and the builder never touches the big downloads again.

    python -m emap_topology.nuts      # downloads (if missing) and regenerates data/nuts3_dk.*
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import zipfile

from .config import DATA, WORK
from .sources import _download, sha256

NUTS_VERSION = "2021-01-01"
NUTS_URL = (
    f"https://data.pypsa.org/workflows/eur/eu_nuts2021/{NUTS_VERSION}/ref-nuts-2021-01m.geojson.zip"
)
NUTS_MEMBER = "NUTS_RG_01M_2021_4326_LEVL_3.geojson"
POPGDP_VERSION = "13-03-2025"
POPGDP_URL = f"https://data.pypsa.org/workflows/eur/nuts3_population/{POPGDP_VERSION}/nama_10r_3popgdp.tsv.gz"
# GDP by NUTS3 (MIO_EUR) straight from Eurostat's dissemination API (same family as the
# population table PyPSA-Eur pins; PyPSA-Eur itself uses a GDP-per-capita raster for this term).
GDP_URL = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/nama_10r_3gdp?format=TSV&compressed=true"

GEO_OUT = DATA / "nuts3_dk.geojson"
POPGDP_OUT = DATA / "nuts3_dk_popgdp.csv"
COUNTRY = "DK"


def _latest(values: list[str]) -> tuple[int | None, float | None]:
    """(year, value) of the most recent non-missing cell in a Eurostat TSV row."""
    for i in range(len(values) - 1, -1, -1):
        cell = values[i].strip().rstrip("bdepu ").strip()  # drop Eurostat flags like ' e'
        if cell and cell != ":":
            return i, float(cell)
    return None, None


def regenerate() -> None:
    zpath = WORK / "nuts" / "ref-nuts-2021-01m.geojson.zip"
    tpath = WORK / "nuts" / "nama_10r_3popgdp.tsv.gz"
    gpath = WORK / "nuts" / "nama_10r_3gdp.tsv.gz"
    _download(NUTS_URL, zpath)
    _download(POPGDP_URL, tpath)
    _download(GDP_URL, gpath)

    with zipfile.ZipFile(zpath) as z:
        gj = json.load(io.TextIOWrapper(z.open(NUTS_MEMBER), encoding="utf-8"))
    feats = [f for f in gj["features"] if f["properties"].get("CNTR_CODE") == COUNTRY]
    out = {
        "type": "FeatureCollection",
        "provenance": {"url": NUTS_URL, "member": NUTS_MEMBER, "sha256_zip": sha256(zpath)},
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "id": f["properties"]["NUTS_ID"],
                    "name": f["properties"]["NUTS_NAME"],
                },
                "geometry": f["geometry"],
            }
            for f in feats
        ],
    }
    GEO_OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    rows = []
    for path, want_unit in ((tpath, "THS"), (gpath, "MIO_EUR")):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            header = fh.readline().rstrip("\n").split("\t")
            years = [h.strip() for h in header[1:]]
            for line in fh:
                key, *vals = line.rstrip("\n").split("\t")
                _freq, unit, geo = key.split(",")
                if not geo.startswith(COUNTRY) or len(geo) != 5 or unit != want_unit:
                    continue
                i, v = _latest(vals)
                if v is not None:
                    rows.append({"nuts3": geo, "unit": unit, "year": years[i], "value": v})
    with POPGDP_OUT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["nuts3", "unit", "year", "value"])
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["nuts3"], r["unit"])))
    (DATA / "nuts3_dk_popgdp.provenance.json").write_text(
        json.dumps(
            {
                "population": {
                    "url": POPGDP_URL,
                    "sha256": sha256(tpath),
                    "version": POPGDP_VERSION,
                },
                "gdp": {"url": GDP_URL, "sha256": sha256(gpath)},
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"{GEO_OUT.name}: {len(feats)} NUTS3 regions; {POPGDP_OUT.name}: {len(rows)} rows")


def read_nuts3_dk() -> tuple[dict, dict[str, dict[str, float]]]:
    """(geojson FeatureCollection, {nuts3: {'pop_ths': …, 'gdp_meur': …}})."""
    gj = json.loads(GEO_OUT.read_text(encoding="utf-8"))
    stats: dict[str, dict[str, float]] = {}
    with POPGDP_OUT.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            key = "pop_ths" if r["unit"] == "THS" else "gdp_meur"
            stats.setdefault(r["nuts3"], {})[key] = float(r["value"])
    return gj, stats


if __name__ == "__main__":
    regenerate()
