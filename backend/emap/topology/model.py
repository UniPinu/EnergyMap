"""The static topology artifact (service A output) as validated pydantic models.

`nodes`/`edges` are the canonical MVP.md §5.1 shapes at the finest level Π_L; `views[ℓ]`
holds the precomputed *structure* of coarser levels (membership, positions, bundled corridors).
Referential integrity is enforced here so the API can never serve a dangling edge.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from emap.schema import Edge, EdgeKind, Node, NodeKind


class ZoneInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    country: str
    detail: bool
    lat: float
    lon: float


class LevelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level: int
    name: str
    description: str


class TopologyMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    builder: str
    built_at_utc: str
    params: dict[str, Any]
    sources: list[dict[str, str]]
    levels: list[LevelInfo]
    finest_level: int
    distribution_rule: dict[str, str] = Field(default_factory=dict)


class ClusterNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    level: int
    zone: str
    name: str
    lat: float
    lon: float
    members: list[str]
    counts: dict[NodeKind, int]
    capacity_mw: dict[str, float]


class BundledEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)
    id: str
    from_: str = Field(alias="from")
    to: str
    kind: EdgeKind
    rating_mw: float | None
    length_km: float | None
    members: list[str]


class LevelView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nodes: list[ClusterNode]
    edges: list[BundledEdge]


class Topology(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meta: TopologyMeta
    zones: list[ZoneInfo]
    nodes: list[Node]
    edges: list[Edge]
    edge_members: dict[str, list[str]]
    load_key_detail: dict[str, dict[str, float]] = Field(default_factory=dict)
    views: dict[str, LevelView]

    @model_validator(mode="after")
    def _integrity(self) -> Topology:
        ids = {n.id for n in self.nodes}
        if len(ids) != len(self.nodes):
            raise ValueError("duplicate node ids")
        eids = {e.id for e in self.edges}
        if len(eids) != len(self.edges):
            raise ValueError("duplicate edge ids")
        for e in self.edges:
            if e.from_ not in ids or e.to not in ids:
                raise ValueError(f"edge {e.id} references unknown node")
        levels = {str(lv.level) for lv in self.meta.levels if lv.level < self.meta.finest_level}
        if set(self.views) != levels:
            raise ValueError(f"views {sorted(self.views)} != coarse levels {sorted(levels)}")
        for lvl, view in self.views.items():
            members = sorted(m for c in view.nodes for m in c.members)
            if members != sorted(ids):
                raise ValueError(f"view {lvl} members do not partition the node set")
            cids = {c.id for c in view.nodes}
            for be in view.edges:
                if be.from_ not in cids or be.to not in cids:
                    raise ValueError(f"bundled edge {be.id} references unknown cluster")
                if any(m not in eids for m in be.members):
                    raise ValueError(f"bundled edge {be.id} lists unknown member edges")
        for n in self.nodes:
            for lvl in levels | {str(self.meta.finest_level)}:
                if int(lvl) not in n.cluster:
                    raise ValueError(f"node {n.id} lacks cluster level {lvl}")
        return self

    def node_index(self) -> dict[str, Node]:
        return {n.id: n for n in self.nodes}


def load_topology(path: Path) -> Topology:
    return Topology.model_validate(json.loads(path.read_text(encoding="utf-8")))
