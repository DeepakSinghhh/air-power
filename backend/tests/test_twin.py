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
