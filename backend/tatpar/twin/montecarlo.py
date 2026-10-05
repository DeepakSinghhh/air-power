"""Monte-Carlo readiness forecasting with the Fleet Twin.

``mode="belief"`` (default) replaces every hidden life budget with a draw from the prognostic
models before each replication — the forecast is what TATPAR can honestly know.
``mode="truth"`` keeps the hidden truth; used only to evaluate policies and forecast calibration.
Replications run in parallel processes; seeds are shared across policies (common random numbers).
"""
from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

import numpy as np

from .policies import Policy
from .simulator import Scenario, Simulator
from .state import MC, SQN_IDS, STATE_NAMES, FleetState

_G: dict = {}


def _init(state, belief, policy, scenario, days, mode, stock_override):
    _G.update(state=state, belief=belief, policy=policy, scenario=scenario, days=days, mode=mode,
              stock_override=stock_override)


def resample_truth(st: FleetState, rng: np.random.Generator) -> FleetState:
    """New hidden realisation: every LRU life redrawn from the *true* distribution conditional on
    its consumed life (engines keep their HUMS trajectory). Used to evaluate policies and forecast
    calibration over many possible futures rather than one."""
    from ..domain.catalog import LRU_TYPES
    from .state import ENGINE_IDX, LRU_IDS

    b = st.copy()
    for s in range(b.n_ser):
        li = int(b.ser_type[s])
        if li == ENGINE_IDX:
            continue
        l = LRU_TYPES[LRU_IDS[li]]
        eta = l.eta_fh * (0.07 if b.ser_rogue[s] else 1.0)
        a = b.ser_age[s]
        u = max(rng.random(), 1e-12)
        b.ser_L[s] = eta * ((a / eta) ** l.beta - np.log(u)) ** (1 / l.beta)
    return b


def _apply_stock(st: FleetState, override: dict | None, seed: int) -> None:
    if not override:
        return
    from .state import ED
    rng = np.random.default_rng(seed)
    for (sp, li), qty in override.items():
        cur = st.stock.get((sp, li), [])
        if qty < len(cur):
            st.stock[(sp, li)] = cur[:qty]
        else:
            st.stock[(sp, li)] = cur + [st.new_serial(li, rng) for _ in range(qty - len(cur))]


def _one(seed: int) -> dict:
    st: FleetState = _G["state"]
    rng = np.random.default_rng([seed, 99])
    if _G["mode"] == "belief" and _G["belief"] is not None:
        s = _G["belief"].sample_beliefs(st, rng)
    elif _G["mode"] == "truth_resampled":
        s = resample_truth(st, rng)
    else:
        s = st.copy()
    _apply_stock(s, _G["stock_override"], seed)
    pol: Policy = _G["policy"]
    if pol.risk_fn is not None and _G["belief"] is not None:
        pol = pol.with_(risk_fn=_G["belief"].risk_fn)
    sim = Simulator(s, pol, _G["scenario"], seed=seed).run(_G["days"])
    A = sim.status_array()
    sq = s.tail_sqn
    mc_sq = np.stack([(A[:, sq == k] == MC).sum(1) for k in range(len(SQN_IDS))], axis=1)  # [days, sqn]
    states = np.stack([(A == k).sum(1) for k in range(len(STATE_NAMES))], axis=1)            # [days, state]
    short = np.array(sim.sortie_short)
    return {"mc_sq": mc_sq, "states": states, "short": short, "counters": sim.counters}


@dataclass
class Forecast:
    days: int
    start_day: int
    mc_sq: np.ndarray          # [reps, days, sqn]
    states: np.ndarray         # [reps, days, state]
    short: np.ndarray          # [reps, days, sqn]
    counters: list

    @property
    def mc_total(self) -> np.ndarray:
        return self.mc_sq.sum(-1)

    def bands(self, sqn: int | None = None) -> dict:
        x = self.mc_total if sqn is None else self.mc_sq[:, :, sqn]
        q = np.percentile(x, [10, 25, 50, 75, 90], axis=0)
        return {"p10": q[0].tolist(), "p25": q[1].tolist(), "p50": q[2].tolist(), "p75": q[3].tolist(),
                "p90": q[4].tolist(), "mean": x.mean(0).tolist()}

    def p_meet(self, sqn: int, start: int, end: int, min_mc: int) -> float:
        """Probability that the squadron has >= min_mc MC aircraft on every day of [start, end] (offsets)."""
        w = self.mc_sq[:, start:end + 1, sqn]
        return float((w >= min_mc).all(axis=1).mean())

    def p_meet_daily(self, sqn: int, min_mc: int) -> list[float]:
        return (self.mc_sq[:, :, sqn] >= min_mc).mean(0).tolist()

    def mc_rate(self) -> float:
        n = self.mc_sq.shape[-1]
        return float(self.mc_total.mean() / 64)

    def state_share(self) -> dict[str, float]:
        tot = self.states.sum(-1, keepdims=True)
        share = (self.states / tot).mean((0, 1))
        return {STATE_NAMES[k]: float(share[k]) for k in range(len(STATE_NAMES))}


def forecast(state: FleetState, policy: Policy, days: int = 60, reps: int = 120, belief=None,
             scenario: Scenario | None = None, mode: str = "belief", seed0: int = 1000,
             stock_override: dict | None = None, workers: int | None = None) -> Forecast:
    seeds = [seed0 + k for k in range(reps)]
    args = (state, belief, policy.with_(risk_fn=None) if policy.risk_fn else policy, scenario or Scenario(),
            days, mode, stock_override)
    # risk_fn is re-bound inside workers (bound methods of large objects pickle slowly)
    needs_risk = policy.risk_fn is not None
    if needs_risk:
        args = (state, belief, policy.with_(risk_fn=_sentinel), scenario or Scenario(), days, mode, stock_override)
    workers = workers or min(4, os.cpu_count() or 1)
    if workers <= 1 or reps < 8:
        _init(*args)
        out = [_one(s) for s in seeds]
    else:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=args) as ex:
            out = list(ex.map(_one, seeds, chunksize=max(1, reps // (workers * 4))))
    return Forecast(days=days, start_day=state.day,
                    mc_sq=np.stack([o["mc_sq"] for o in out]), states=np.stack([o["states"] for o in out]),
                    short=np.stack([o["short"] for o in out]), counters=[o["counters"] for o in out])


def _sentinel(state, horizon_days):  # placeholder; replaced by belief.risk_fn in workers
    raise RuntimeError("risk_fn sentinel should have been replaced")
