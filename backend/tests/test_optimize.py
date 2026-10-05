from math import exp

import numpy as np
import pytest

from tatpar.config import ARTIFACTS_DIR
from tatpar.optimize.sparing import SparingProblem, _ebo_vbo

needs_artifacts = pytest.mark.skipif(not (ARTIFACTS_DIR / "belief.joblib").exists(), reason="artifacts not built")


def test_metric_ebo_matches_hand_computed_poisson():
    ebo, vbo = _ebo_vbo(2.0, 2.0, 3)
    p0 = exp(-2)
    p1 = 2 * exp(-2)
    assert ebo[0] == pytest.approx(2.0, abs=1e-6)
    assert ebo[1] == pytest.approx(2.0 - (1 - p0), abs=1e-6)            # E[(X-1)+] = mu - P(X>=1)
    assert ebo[2] == pytest.approx(ebo[1] - (1 - p0 - p1), abs=1e-6)
    assert vbo[0] == pytest.approx(2.0, abs=1e-6)                         # Var(X) for Poisson
    assert np.all(np.diff(ebo) <= 0)


def test_rbs_respects_budget_and_improves_availability():
    prob = SparingProblem(
        lam=np.array([[0.05, 0.02], [0.01, 0.03]]), tat=np.array([30.0, 60.0]),
        qpa=np.array([[2, 2], [1, 1]]), n_ac=np.array([16.0, 16.0]), cost=np.array([1.0, 5.0]), bases=["a", "b"])
    s0c, sc = np.array([1, 1]), np.array([[0, 0], [0, 0]])
    budget = float((prob.cost * (s0c + sc.sum(1))).sum()) + 6
    s0, s, A, curve = prob.optimise(budget)
    assert float((prob.cost * (s0 + s.sum(1))).sum()) <= budget + 1e-9
    assert A >= prob.availability(s0c, sc)[0]
    assert all(b[1] >= a[1] - 1e-12 for a, b in zip(curve, curve[1:]))     # frontier is monotone


@needs_artifacts
def test_fmp_plan_is_feasible():
    from tatpar.datagen.history import load_state
    from tatpar.domain.catalog import AIRCRAFT_TYPES, SQUADRONS
    from tatpar.optimize.fmp import plan_squadron
    from tatpar.prognostics.belief import Belief

    st = load_state()
    p = plan_squadron(st, 0, 30, Belief.load(), time_limit=5)
    assert p["status"] in ("OPTIMAL", "FEASIBLE")
    sq = SQUADRONS[p["squadron"]]
    ty = AIRCRAFT_TYPES[sq.type]
    for d in range(30):
        in_phase = sum(1 for r in p["tails"] if r["days"][d] == "phase")
        assert in_phase <= sq.bays
    for r in p["tails"]:
        hours = p["hours"][r["tail"]]
        for d, kind in enumerate(r["days"]):
            if kind in ("phase", "down"):
                assert hours[d] == 0
        if r["phase_start"] is None:
            assert sum(hours) <= r["residual_fh"] + 1e-6
        assert max(hours) <= ty.max_sorties_per_day * ty.sortie_hours


@needs_artifacts
def test_belief_forecast_is_calibrated():
    import json

    fc = json.loads((ARTIFACTS_DIR / "bench" / "forecast.json").read_text())
    assert 0.7 <= fc["calibration"]["coverage_p10_p90"] <= 0.95
