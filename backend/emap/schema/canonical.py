"""Canonical schema — the standardization layer (MVP.md §5).

Every external source is normalized into these three shapes *before* it enters
the store. Invariants enforced here, at the boundary:

  * timestamps are timezone-aware and normalized to UTC (`t_utc`);
  * units are SI-consistent (MW, MWh, EUR/MWh, ratio);
  * enumerations are closed — extending `Quantity`/`Unit` is a deliberate,
    reviewed code change, never an ad-hoc string.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

NodeKind = Literal["source", "grid", "consumption", "storage"]  # V_S, V_G, V_C, V_B (§3.1)
EdgeKind = Literal["ac_line", "hvdc_link", "interconnector"]
EntityKind = Literal["node", "edge"]

# §5.2 lists 'p_gen'|'demand'|'flow'|'soc'|'price'|'strain'|'residual'|...
# The trailing '...' is realized by extending this Literal in later phases.
Quantity = Literal["p_gen", "demand", "flow", "soc", "price", "strain", "residual", "co2_intensity"]
Unit = Literal["MW", "MWh", "EUR/MWh", "ratio", "tCO2/MWh"]
Source = Literal["energinet", "entsoe", "pypsa", "derived"]
Resolution = Literal["PT5M", "PT15M", "PT60M"]
Quality = Literal["measured", "interpolated", "estimated", "missing"]


# ---------------------------------------------------------------------------
# §5.1 Static entities
# ---------------------------------------------------------------------------


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, description="stable canonical id")
    kind: NodeKind
    name: str
    zone: str = Field(min_length=1, description="bidding zone, e.g. 'DK1'")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    cluster: dict[int, str] = Field(
        default_factory=dict, description="level -> cluster_id; membership in Π_0..Π_L"
    )
    capacity_mw: float | None = Field(
        default=None, ge=0, description="nameplate power rating (MW); storage: P_max"
    )
    fuel: str | None = None
    co2_intensity: float | None = Field(default=None, ge=0, description="tCO2/MWh")
    # Optional extensions of MVP.md §5.1 (strict superset):
    energy_mwh: float | None = Field(default=None, ge=0, description="storage E_max (MWh)")
    voltage_kv: int | None = Field(default=None, ge=0, description="grid bus nominal voltage")
    dist_key: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="share of the zone aggregate this node receives (bus->zone rule, Phase 2)",
    )


class Edge(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    id: str = Field(min_length=1)
    from_: str = Field(alias="from", min_length=1)
    to: str = Field(min_length=1)
    kind: EdgeKind
    rating_mw: float | None = Field(
        ge=0, description="thermal limit / NTC; null = unrated virtual connection (bus->load)"
    )
    length_km: float | None = Field(default=None, ge=0)


# ---------------------------------------------------------------------------
# §5.2 Time series — long format, one shape for everything
# ---------------------------------------------------------------------------


class Sample(BaseModel):
    """One observation on the canonical time grid.

    Join key is (entity_id, quantity, t_utc); `source` is kept in the store's
    uniqueness key so two providers may report the same quantity side by side.
    A `quality == 'missing'` row carries `value=None` (a dense grid may need an
    explicit gap); every other quality requires a finite value.
    """

    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(min_length=1)
    entity_kind: EntityKind
    quantity: Quantity
    t_utc: AwareDatetime
    value: float | None
    unit: Unit
    source: Source
    resolution: Resolution
    quality: Quality

    @field_validator("t_utc")
    @classmethod
    def _to_utc(cls, v: datetime) -> datetime:
        # AwareDatetime already rejects naive input; normalize the offset to +00:00.
        return v.astimezone(UTC)

    @field_validator("value")
    @classmethod
    def _finite(cls, v: float | None) -> float | None:
        if v is not None and not math.isfinite(v):
            raise ValueError(
                "value must be finite (use quality='missing' with value=None for gaps)"
            )
        return v

    @model_validator(mode="after")
    def _missing_iff_none(self) -> Sample:
        if (self.quality == "missing") != (self.value is None):
            raise ValueError("value is None if and only if quality == 'missing'")
        return self
