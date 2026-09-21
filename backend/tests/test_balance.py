"""MVP.md §3.4 on toy networks: A·F = n, Σn = 0 after reconciliation, residual, weighting."""

from __future__ import annotations

import numpy as np
import pytest

from emap.analytics.balance import (
    Measurement,
    Reconciliation,
    incidence_matrix,
    nodal_residual,
    reconcile,
    reconcile_nodal,
    residual,
    residual_hat,
)


def test_incidence_matrix_signs_and_shape():
    A, eids = incidence_matrix(["a", "b", "c"], [("e1", "a", "b"), ("e2", "b", "c")])
    assert eids == ["e1", "e2"]
    # +1 where the edge leaves, −1 where it enters (MVP.md §3.1)
    assert A.tolist() == [[1.0, 0.0], [-1.0, 1.0], [0.0, -1.0]]
    # every column sums to zero: an edge moves power, it never creates it
    assert np.allclose(A.sum(axis=0), 0.0)


def test_kcl_holds_for_consistent_flows_and_fails_otherwise():
    A, _ = incidence_matrix(["a", "b", "c"], [("e1", "a", "b"), ("e2", "b", "c")])
    F = np.array([10.0, 4.0])  # a→b 10, b→c 4
    n = np.array([10.0, -6.0, -4.0])  # a injects 10, b withdraws 6, c withdraws 4
    assert np.allclose(nodal_residual(A, F, n), 0.0)
    assert np.allclose(nodal_residual(A, F, np.array([10.0, -5.0, -4.0])), [0.0, -1.0, 0.0])
    assert np.isclose(n.sum(), 0.0)  # lossless system balance 1ᵀn = 0


def test_residual_from_imbalanced_measurements():
    ms = [
        Measurement("gen", 3700.0, +1.0, 1.0),
        Measurement("load", 2800.0, -1.0, 1.0),
        Measurement("export_de", 900.0, -1.0, 1.0),
        Measurement("export_no", -400.0, -1.0, 1.0),  # an import
    ]
    assert residual(ms) == pytest.approx(3700.0 - 2800.0 - 900.0 + 400.0)
    assert residual_hat(400.0, 2800.0) == pytest.approx(400.0 / 2800.0)
    assert residual_hat(400.0, 0.0) is None and residual_hat(400.0, None) is None


def test_reconciliation_closes_the_identity_with_equal_weights():
    ms = [
        Measurement("gen", 3700.0, +1.0, 1.0),
        Measurement("load", 2800.0, -1.0, 1.0),
        Measurement("export", 500.0, -1.0, 1.0),
    ]
    rec = reconcile(ms)
    assert isinstance(rec, Reconciliation) and rec.residual == pytest.approx(400.0)
    # Σ coef · x* = 0
    closed = sum(m.coef * rec.values[m.key] for m in ms)
    assert closed == pytest.approx(0.0, abs=1e-9)
    # equal weights: |adjustment| equal, r/3 each, signed so each term moves toward closure
    assert rec.adjustments["gen"] == pytest.approx(-400.0 / 3)
    assert rec.adjustments["load"] == pytest.approx(+400.0 / 3)
    assert rec.adjustments["export"] == pytest.approx(+400.0 / 3)


def test_adjustments_are_proportional_to_inverse_weights():
    ms = [
        Measurement("gen", 1000.0, +1.0, 1.0),  # trust 1
        Measurement("load", 800.0, -1.0, 4.0),  # trusted 4x more → adjusted 4x less
        Measurement("export", 100.0, -1.0, 1e9),  # metered: effectively fixed
    ]
    rec = reconcile(ms)
    assert rec.residual == pytest.approx(100.0)
    assert abs(rec.adjustments["gen"]) == pytest.approx(4 * abs(rec.adjustments["load"]), rel=1e-6)
    assert abs(rec.adjustments["export"]) < 1e-6
    assert sum(m.coef * rec.values[m.key] for m in ms) == pytest.approx(0.0, abs=1e-6)


def test_slack_node_absorbs_everything():
    inj = {"dk1": 500.0, "dk2": -350.0, "slack": 0.0}
    rec = reconcile_nodal(inj, {"dk1": 1e9, "dk2": 1e9, "slack": 1e-9})
    assert rec.residual == pytest.approx(150.0)
    assert rec.values["dk1"] == pytest.approx(500.0, abs=1e-3)
    assert rec.values["dk2"] == pytest.approx(-350.0, abs=1e-3)
    assert rec.values["slack"] == pytest.approx(-150.0, abs=1e-3)
    assert sum(rec.values.values()) == pytest.approx(0.0, abs=1e-6)


def test_nodal_form_conserves_and_leaves_balanced_input_untouched():
    balanced = {"a": 100.0, "b": -60.0, "c": -40.0}
    rec = reconcile_nodal(balanced, dict.fromkeys(balanced, 1.0))
    assert rec.residual == 0.0 and all(abs(d) < 1e-12 for d in rec.adjustments.values())
    skewed = {"a": 100.0, "b": -60.0, "c": -30.0}
    rec = reconcile_nodal(skewed, dict.fromkeys(skewed, 1.0))
    assert sum(rec.values.values()) == pytest.approx(0.0, abs=1e-9)  # Σ nᵢ = 0
    assert all(d == pytest.approx(-10.0 / 3) for d in rec.adjustments.values())


def test_invalid_weights_and_coefficients_are_rejected():
    with pytest.raises(ValueError):
        Measurement("x", 1.0, 1.0, 0.0)
    with pytest.raises(ValueError):
        Measurement("x", 1.0, 0.5, 1.0)
    assert reconcile([]).values == {}
