"""API-facing state shapes (pipeline stage ④ output). Optional fields are None when the
quantity is not defined for the node kind or no live data exists (never 0)."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel

from emap.schema import NodeKind, Quality


class NodeState(BaseModel):
    id: str
    kind: NodeKind
    quality: Quality
    # source (§3.2): P_gen, u, δ(1h)
    p_gen: float | None = None
    u: float | None = None
    delta_1h: float | None = None
    # consumption: D, ρ (needs D_ref, Phase 4), δ^D(1h)
    demand: float | None = None
    rho: float | None = None
    # grid: T_g (known corridor flows only until internal flows exist), λ, sgn(n_g)
    t_flow: float | None = None
    loading: float | None = None
    net_injection: float | None = None
    net_sign: int | None = None
    # storage: P_b, SoC, duration — no live storage feed yet
    p_store: float | None = None
    soc: float | None = None
    duration_h: float | None = None


class EdgeState(BaseModel):
    id: str
    flow: float | None = None  # signed from -> to (MVP.md §3.3)
    loading: float | None = None  # |F| / rating
    quality: Quality


class ZoneState(BaseModel):
    id: str
    live: bool
    p_gen: float | None = None
    by_class: dict[str, float] = {}
    demand: float | None = None
    demand_quality: Quality = "missing"
    demand_age_min: float | None = None
    exchange: float | None = None  # net export X (Σ corridor flows away from the zone)
    price: float | None = None
    co2_intensity: float | None = None
    residual: float | None = None  # r = Σgen - Σload - X   (L = 0 until Phase 3)
    residual_hat: float | None = None  # r / Σload


class ClusterState(BaseModel):
    id: str
    level: int
    p_gen: float | None = None
    demand: float | None = None
    net_injection: float | None = None
    quality: Quality


class State(BaseModel):
    t_utc: AwareDatetime
    computed_at_utc: AwareDatetime
    step: Literal["PT5M"] = "PT5M"
    nodes: dict[str, NodeState]
    edges: dict[str, EdgeState]
    zones: dict[str, ZoneState]
    clusters: dict[str, dict[str, ClusterState]]  # level -> cluster id -> state
