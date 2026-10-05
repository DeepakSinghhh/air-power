import numpy as np
import pytest

from tatpar.domain.catalog import AIRCRAFT_TYPES, SQUADRONS
from tatpar.twin.policies import BASELINE, TATPAR
from tatpar.twin.simulator import Simulator
from tatpar.twin.state import CHECKS, NMCM_S, SQN_IDS, TYPE_IDS, build_initial_state


@pytest.fixture(scope="module")
def initial():
    return build_initial_state(seed=11)


def _slots(st):
    installed = int((st.pos_serial >= 0).sum())
    stock = sum(len(v) for v in st.stock.values())
    return installed + stock + len(st.shipments) + len(st.pipeline) + len(st.procurement)


class Checker(Simulator):
    """Simulator that asserts invariants every day."""

    def step(self):
        super().step()
        s = self.s
        # missing-part bookkeeping matches empty positions
        for t in range(s.n_tails):
            assert s.missing[t] == int((s.pos_serial[s.pos_tail == t] < 0).sum())
        # no check interval is overrun
        for c in CHECKS:
            iv = np.array([AIRCRAFT_TYPES[TYPE_IDS[ty]].check(c).interval_fh for ty in s.tail_type])
            assert (s.hrs_since[c] <= iv + 1e-6).all(), c
        # phase bays never exceeded
        st = s.status()
        for i, q in enumerate(SQN_IDS):
            in_phase = sum(1 for t in np.flatnonzero(s.tail_sqn == i) if s.check_kind[t] == "phase")
            assert in_phase <= SQUADRONS[q].bays
        assert ((st >= 0) & (st <= 5)).all()


@pytest.mark.parametrize("policy", [BASELINE, TATPAR], ids=["baseline", "tatpar"])
def test_invariants_and_conservation(initial, policy):
    st = initial.copy()
    before = _slots(st)
    Checker(st, policy, seed=3).run(200)
    assert _slots(st) == before          # every serial accounted for (installed/stock/transit/repair/procurement)
    assert st.n_tails == 64


def test_deterministic(initial):
    a = Simulator(initial.copy(), BASELINE, seed=5).run(120).status_array()
    b = Simulator(initial.copy(), BASELINE, seed=5).run(120).status_array()
    assert (a == b).all()


def test_tatpar_levers_improve_availability(initial):
    base = np.mean([(Simulator(initial.copy(), BASELINE, seed=k).run(240).status_array() == 0).mean() for k in range(3)])
    tat = np.mean([(Simulator(initial.copy(), TATPAR, seed=k).run(240).status_array() == 0).mean() for k in range(3)])
    assert tat > base + 0.05


def test_baseline_in_reported_serviceability_band(initial):
    mc = (Simulator(initial.copy(), BASELINE, seed=1).run(365).status_array() == 0).mean()
    assert 0.45 < mc < 0.68   # reported Su-30MKI serviceability band 48-68 %


def test_reproducible_across_processes():
    """Same seed, different Python hash seeds -> identical history (no set-order dependence)."""
    import os
    import subprocess
    import sys

    code = ("import numpy as np; from tatpar.twin.state import build_initial_state; from tatpar.twin.simulator import Simulator; "
            "from tatpar.twin.policies import TATPAR; from tatpar.prognostics.belief import Belief;"
            "st = build_initial_state(seed=3); rf = lambda s, h: np.full(len(s.pos_tail), 0.2);"
            "sim = Simulator(st, TATPAR.with_(risk_fn=rf), seed=5).run(40); print(int(sim.status_array().sum()), sim.counters)")
    outs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                           env={**os.environ, "PYTHONHASHSEED": h}).stdout for h in ("1", "2", "3")}
    assert len(outs) == 1, outs


def test_sensitivity_knobs_move_the_twin(initial):
    """The knobs used by the sensitivity study change the world in the expected direction."""
    from tatpar.twin.montecarlo import forecast
    from tatpar.twin.simulator import Scenario

    def mc(**kw):
        return forecast(initial, BASELINE, 60, 3, None, Scenario(**kw), mode="truth_resampled", workers=1).mc_rate()

    ref = mc()
    assert mc(life_mult=0.6) < ref           # more failures -> fewer mission-capable aircraft
    assert mc(tat_mult=2.0) < ref            # slower repairs -> fewer
    assert mc(task_mult=0.5) > ref - 0.01    # lighter flying task -> not worse
