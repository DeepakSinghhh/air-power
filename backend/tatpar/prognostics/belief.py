"""Belief layer: turns the prognostic models into what the Fleet Twin and optimisers consume.

* ``risk_fn(state, horizon_days)`` -> P(failure within the horizon) for every installed position
  (survival models for LRUs, calibrated HUMS RUL for engines, rogue flags as a multiplier).
* ``sample_beliefs(state, rng)`` -> a copy of the twin state whose hidden life budgets are
  replaced by draws from the models, so Monte-Carlo forecasts never read the ground truth.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import joblib
import numpy as np
import pandas as pd

from ..config import ARTIFACTS_DIR, FH_PER_CYCLE
from ..data import cmapss
from ..domain.catalog import LRU_TYPES
from ..twin.simulator import ENV_MULT, G_SENS, day_to_date
from ..twin.state import ENGINE_IDX, LRU_IDS, TYPE_IDS, FleetState
from .engine_rul import ALPHA, EngineRUL
from .survival import COVS, SurvivalModels

BELIEF_PATH = ARTIFACTS_DIR / "belief.joblib"
COV_IDX = [0, 1, 2, 5]           # dust, heat, hum, g columns of ser_cov
FH_PER_DAY = {"HF": 0.76, "LF": 0.65}


@dataclass
class Belief:
    surv: SurvivalModels
    engine_table: dict = field(default_factory=dict)   # uid -> array[cycle] of (lo, med, hi) in cycles
    rogue_serials: set = field(default_factory=set)

    @classmethod
    def build(cls, surv: SurvivalModels, rul: EngineRUL, rogue_serials: set) -> "Belief":
        df = cmapss.load_train()
        fleet = df[df["uid"].isin(cmapss.split_units()["fleet"])]
        F = rul.featurize(fleet)
        P = rul.predict_features(F)
        P["uid"] = F["uid"].to_numpy()
        P["cycle"] = F["cycle"].to_numpy()
        table = {}
        for uid, g in P.groupby("uid"):
            g = g.sort_values("cycle")
            arr = np.zeros((int(g["cycle"].max()) + 1, 3))
            arr[g["cycle"].to_numpy()] = g[["rul_lo", "rul_med", "rul_hi"]].to_numpy()
            arr[0] = arr[1]
            table[uid] = arr
        return cls(surv=surv, engine_table=table, rogue_serials=set(int(s) for s in rogue_serials))

    # ------------------------------------------------------------------ engines
    def engine_quantiles(self, st: FleetState, ser: int) -> tuple[float, float, float]:
        uid = st.engine_units[int(st.ser_unit[ser])]
        arr = self.engine_table[uid]
        cyc = int(min(len(arr) - 1, max(1, st.ser_age[ser] // FH_PER_CYCLE)))
        lo, med, hi = arr[cyc]
        return float(lo), float(med), float(hi)

    @staticmethod
    def _cdf(x: np.ndarray, lo: float, med: float, hi: float) -> np.ndarray:
        xs = np.maximum.accumulate(np.array([0.0, lo, med, hi, hi + 0.6 * (hi - med) + 1e-6]))
        ps = np.array([0.0, ALPHA / 2, 0.5, 1 - ALPHA / 2, 1.0])
        return np.interp(x, xs, ps)

    # ------------------------------------------------------------------ risk
    def risk_fn(self, st: FleetState, horizon_days: float) -> np.ndarray:
        n = len(st.pos_tail)
        out = np.zeros(n)
        ser = st.pos_serial
        ok = ser >= 0
        util = np.array([FH_PER_DAY[TYPE_IDS[t]] for t in st.tail_type])[st.pos_tail]
        horizon_fh = util * horizon_days
        for li, lid in enumerate(LRU_IDS):
            m = ok & (st.pos_type == li)
            if not m.any():
                continue
            idx = np.flatnonzero(m)
            s = ser[idx]
            if li == ENGINE_IDX:
                for j, sj in zip(idx, s):
                    lo, med, hi = self.engine_quantiles(st, int(sj))
                    out[j] = float(self._cdf(np.array([horizon_fh[j] / FH_PER_CYCLE]), lo, med, hi)[0])
                continue
            if lid not in self.surv.params:
                continue
            hrs = np.maximum(st.ser_hrs[s], 1e-3)
            X = st.ser_cov[s][:, COV_IDX] / hrs[:, None]
            X[st.ser_hrs[s] <= 0] = 0.0
            p = self.surv.cond_fail_prob(lid, hrs, horizon_fh[idx], X)
            rogue = np.array([int(x) in self.rogue_serials for x in s])
            p = np.where(rogue, 1 - (1 - p) ** 10, p)
            out[idx] = p
        return out

    # ------------------------------------------------------------------ belief sampling
    def sample_beliefs(self, st: FleetState, rng: np.random.Generator) -> FleetState:
        b = st.copy()
        month = day_to_date(b.day).month - 1
        pos_of = {int(s): p for p, s in enumerate(b.pos_serial) if s >= 0}
        for s in range(b.n_ser):
            li = int(b.ser_type[s])
            lid = LRU_IDS[li]
            p = pos_of.get(s)
            if li == ENGINE_IDX:
                if p is None:
                    continue
                lo, med, hi = self.engine_quantiles(b, s)
                xs = np.maximum.accumulate(np.array([0.0, lo, med, hi, hi + 0.6 * (hi - med)]))
                r = float(np.interp(rng.random(), [0.0, ALPHA / 2, 0.5, 1 - ALPHA / 2, 1.0], xs))
                # HUMS RUL is capped at 125 cycles; healthy engines keep their life beyond the cap
                if med >= 115:
                    r = max(r, 125 + rng.exponential(60))
                b.ser_L[s] = b.ser_age[s] + r * FH_PER_CYCLE
                continue
            if lid not in self.surv.params:
                continue
            hrs = max(float(b.ser_hrs[s]), 1e-3)
            X = (b.ser_cov[s, COV_IDX] / hrs)[None, :] if b.ser_hrs[s] > 0 else np.zeros((1, 4))
            rem = float(self.surv.sample_remaining(lid, np.array([hrs]), X, np.array([max(rng.random(), 1e-9)]))[0])
            if s in self.rogue_serials:
                rem *= 0.1
            if p is not None:
                t = int(b.pos_tail[p])
                sp = int(b.tail_sp[t])
                mult = ENV_MULT[month, sp, li] * np.exp(G_SENS[li] * 0.15)
            else:
                mult = 1.3
            b.ser_L[s] = b.ser_age[s] + rem * mult
        return b

    def save(self, path=BELIEF_PATH) -> None:
        joblib.dump(self, path)

    @staticmethod
    def load(path=BELIEF_PATH) -> "Belief":
        return joblib.load(path)
