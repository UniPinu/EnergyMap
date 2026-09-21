"""The balance invariant and its reconciliation (MVP.md §3.4) — pure numerics, no I/O.

Network N = (V, E) with the node–edge incidence matrix A ∈ {-1, 0, +1}^{|V|×|E|}:
    A[i, e] = +1 if e leaves i, -1 if e enters i, 0 otherwise.
Nodal conservation (KCL):  A·F = n,  hence 1ᵀn = 0 for a lossless system.

Measured data never satisfies this. The reconciliation residual of a set of measurements
x_k entering the identity with coefficients a_k (Σ_k a_k x_k should be 0) is
    r = Σ_k a_k x_k                       (raw)
and the MVP reconciliation is the weighted projection onto the constraint,
    x* = argmin ‖W^{1/2}(x − x̃)‖²  s.t.  aᵀx = 0,
whose closed form is
    x* = x̃ − W⁻¹a · (aᵀx̃) / (aᵀW⁻¹a),
i.e. −r is redistributed across the measurements in proportion to their inverse trust
weights 1/w_k (a single measurement with all the inverse weight is the "slack node").
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import numpy as np


def incidence_matrix(
    node_ids: Sequence[str], edges: Iterable[tuple[str, str, str]]
) -> tuple[np.ndarray, list[str]]:
    """A (|V|×|E|) for edges given as (edge_id, from_node, to_node); returns (A, edge ids)."""
    index = {nid: i for i, nid in enumerate(node_ids)}
    edge_ids: list[str] = []
    cols: list[np.ndarray] = []
    for eid, u, v in edges:
        col = np.zeros(len(node_ids))
        col[index[u]] += 1.0  # e leaves u
        col[index[v]] -= 1.0  # e enters v
        cols.append(col)
        edge_ids.append(eid)
    A = np.column_stack(cols) if cols else np.zeros((len(node_ids), 0))
    return A, edge_ids


def nodal_residual(A: np.ndarray, flows: np.ndarray, injections: np.ndarray) -> np.ndarray:
    """A·F − n per node: zero everywhere iff the flows satisfy KCL for these injections."""
    return A @ flows - injections


@dataclass(frozen=True)
class Measurement:
    """One term of a balance identity: `coef · value` (coef = +1 generation, −1 load / export)."""

    key: str
    value: float
    coef: float
    weight: float  # trust w_k > 0 (inverse variance); higher = adjusted less

    def __post_init__(self) -> None:
        if not (self.weight > 0) or not np.isfinite(self.weight):
            raise ValueError(f"weight must be positive and finite for {self.key}")
        if self.coef not in (-1.0, 1.0):
            raise ValueError(f"coef must be ±1 for {self.key}")


@dataclass(frozen=True)
class Reconciliation:
    residual: float  # r = Σ coef·value on the raw measurements
    values: dict[str, float]  # reconciled x*
    adjustments: dict[str, float]  # x* − x̃


def residual(measurements: Iterable[Measurement]) -> float:
    return float(sum(m.coef * m.value for m in measurements))


def reconcile(measurements: Sequence[Measurement]) -> Reconciliation:
    """Weighted projection of the measurements onto Σ coef·x = 0 (closed form above)."""
    if not measurements:
        return Reconciliation(0.0, {}, {})
    a = np.array([m.coef for m in measurements])
    x = np.array([m.value for m in measurements])
    w_inv = np.array([1.0 / m.weight for m in measurements])
    r = float(a @ x)
    # x* = x − W⁻¹a (aᵀx) / (aᵀW⁻¹a)
    delta = -w_inv * a * r / float(a @ (w_inv * a))
    x_star = x + delta
    return Reconciliation(
        residual=r,
        values={m.key: float(v) for m, v in zip(measurements, x_star, strict=True)},
        adjustments={m.key: float(d) for m, d in zip(measurements, delta, strict=True)},
    )


def reconcile_nodal(
    injections: Mapping[str, float], weights: Mapping[str, float]
) -> Reconciliation:
    """MVP nodal form: n* = argmin ‖W^{1/2}(n − ñ)‖² s.t. 1ᵀn = 0 (every node enters with +1)."""
    ms = [Measurement(k, v, 1.0, weights[k]) for k, v in injections.items()]
    return reconcile(ms)


def residual_hat(r: float, total_load: float | None) -> float | None:
    """r̂ = r / Σ_j D_j — the residual as a fraction of load (MVP.md §3.4)."""
    if total_load is None or total_load <= 0:
        return None
    return r / total_load
