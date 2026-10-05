"""Quality gates for the prognostic models (run `python -m tatpar.pipelines.build_all` first)."""
import json

import numpy as np
import pytest

from tatpar.config import ARTIFACTS_DIR

METRICS = ARTIFACTS_DIR / "metrics.json"
pytestmark = pytest.mark.skipif(not METRICS.exists(), reason="artifacts not built")


@pytest.fixture(scope="module")
def metrics():
    return json.loads(METRICS.read_text())


def test_engine_rul_accuracy_and_calibration(metrics):
    test = metrics["engine_rul"]["test"]
    for fd in ("FD001", "FD002", "FD003", "FD004"):
        assert test[fd]["rmse"] < 18, fd
    assert abs(test["ALL"]["picp90"] - 0.90) <= 0.03          # conformal coverage on NASA test sets
    assert test["ALL"]["picp90"] > test["ALL"]["picp90_uncalibrated"]


def test_survival_recovers_truth(metrics):
    s = metrics["survival"]
    assert s["shape_mae"] < 0.35
    assert s["life_recovery"]["r2_log"] > 0.4
    assert s["mean_c_index"] > 0.55


def test_nff_and_rogue_detectors(metrics):
    assert metrics["nff"]["auc"] > 0.7
    assert metrics["nff"]["fpr"] <= 0.09
    assert metrics["rogue"]["precision"] >= 0.7


def test_survival_closed_form_matches_lifelines_shape():
    from tatpar.prognostics.survival import SurvivalModels

    m = SurvivalModels.load()
    lru = next(iter(m.params))
    X = np.zeros((3, 4))
    p0 = m.cond_fail_prob(lru, np.array([0.0, 0.0, 0.0]), np.array([10.0, 100.0, 1000.0]), X)
    assert np.all(np.diff(p0) > 0) and np.all((p0 >= 0) & (p0 <= 1))
    u = np.full(3, 0.5)
    r = m.sample_remaining(lru, np.zeros(3), X, u)
    # median remaining life from age 0 equals the Weibull median
    p = m.params[lru]
    assert np.allclose(r, np.exp(p["b0"]) * np.log(2) ** (1 / p["rho"]))
