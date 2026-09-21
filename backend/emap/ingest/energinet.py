"""Energinet Energi Data Service client (CONTEXT.md §2.1). Server-side only.

* One request per update frequency with a dynamic window (`start=now-PT30M`), never polling
  faster than the dataset updates; HTTP 429 honours `Retry-After`.
* `start`/`end` are interpreted by the API in **Danish local time**; aware datetimes are
  converted to Europe/Copenhagen before formatting. Dynamic strings (`now-PT30M`) pass through.
* Every record is validated into a typed row model before it leaves this module.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, field_validator

log = logging.getLogger(__name__)

BASE_URL = "https://api.energidataservice.dk/dataset"
DK_TZ = ZoneInfo("Europe/Copenhagen")
USER_AGENT = "energymap-balance-terminal/0.1 (server-side ingester)"

PriceArea = Literal["DK1", "DK2"]


def _utc(v: datetime | str) -> datetime:
    """Energinet's *UTC columns are naive ISO strings; attach UTC."""
    dt = datetime.fromisoformat(v) if isinstance(v, str) else v
    return (
        dt.replace(tzinfo=ZoneInfo("UTC")) if dt.tzinfo is None else dt.astimezone(ZoneInfo("UTC"))
    )


class _Row(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ProdexRow(_Row):
    """ElectricityProdex5MinRealtime — 5-min production by class and exchange per neighbour.
    Exchange sign: positive = import into the price area (verified against GrossCon)."""

    Minutes5UTC: datetime
    PriceArea: PriceArea
    ProductionLt100MW: float | None = None
    ProductionGe100MW: float | None = None
    OffshoreWindPower: float | None = None
    OnshoreWindPower: float | None = None
    SolarPower: float | None = None
    ExchangeGreatBelt: float | None = None
    ExchangeGermany: float | None = None
    ExchangeNetherlands: float | None = None
    ExchangeGreatBritain: float | None = None
    ExchangeNorway: float | None = None
    ExchangeSweden: float | None = None
    BornholmSE4: float | None = None

    _t = field_validator("Minutes5UTC")(lambda v: _utc(v))


class GenProdTypeRow(_Row):
    """GenerationProdTypeExchange — hourly gross consumption + production per fuel (~2 h lag)."""

    TimeUTC: datetime
    PriceArea: PriceArea
    Version: str | None = None
    GrossCon: float | None = None
    CO2PerkWh: float | None = None

    _t = field_validator("TimeUTC")(lambda v: _utc(v))


class DayAheadPriceRow(_Row):
    """DayAheadPrices — 15-min day-ahead price; areas include DE/NO2/SE3/SE4 (used in Phase 4)."""

    TimeUTC: datetime
    PriceArea: str
    DayAheadPriceEUR: float | None = None

    _t = field_validator("TimeUTC")(lambda v: _utc(v))


class CO2EmisRow(_Row):
    """CO2Emis — 5-min CO2 intensity of consumption, g/kWh."""

    Minutes5UTC: datetime
    PriceArea: PriceArea
    CO2Emission: float | None = None

    _t = field_validator("Minutes5UTC")(lambda v: _utc(v))


DATASETS: dict[str, type[_Row]] = {
    "ElectricityProdex5MinRealtime": ProdexRow,
    "GenerationProdTypeExchange": GenProdTypeRow,
    "DayAheadPrices": DayAheadPriceRow,
    "CO2Emis": CO2EmisRow,
}


def fmt_local(t: datetime | str) -> str:
    if isinstance(t, str):
        return t
    if t.tzinfo is None:
        raise ValueError("Energinet windows must be built from aware datetimes")
    return t.astimezone(DK_TZ).strftime("%Y-%m-%dT%H:%M")


class EnerginetClient:
    def __init__(self, http: httpx.Client | None = None, *, max_retries: int = 3) -> None:
        self._http = http or httpx.Client(
            base_url=BASE_URL, timeout=httpx.Timeout(60.0), headers={"User-Agent": USER_AGENT}
        )
        self._max_retries = max_retries

    def fetch(
        self,
        dataset: str,
        *,
        start: datetime | str,
        end: datetime | str | None = None,
        price_areas: tuple[str, ...] | None = None,
        columns: tuple[str, ...] | None = None,
        sort: str | None = None,
    ) -> list[_Row]:
        model = DATASETS[dataset]
        params: dict[str, str] = {"start": fmt_local(start), "limit": "0"}
        if end is not None:
            params["end"] = fmt_local(end)
        if price_areas:
            params["filter"] = '{"PriceArea":[' + ",".join(f'"{a}"' for a in price_areas) + "]}"
        if columns:
            params["columns"] = ",".join(columns)
        if sort:
            params["sort"] = sort
        payload = self._get(f"/{dataset}", params)
        rows = payload.get("records", [])
        out = [model.model_validate(r) for r in rows]
        log.info(
            "energinet %s %s..%s -> %d rows", dataset, params["start"], params.get("end"), len(out)
        )
        return out

    def _get(self, path: str, params: dict[str, str]) -> dict:
        for attempt in range(self._max_retries + 1):
            r = self._http.get(path, params=params)
            if r.status_code == 429 and attempt < self._max_retries:
                wait = min(float(r.headers.get("Retry-After", "10")), 120.0)
                log.warning("energinet 429 on %s; sleeping %.0fs", path, wait)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError("unreachable")

    def close(self) -> None:
        self._http.close()
