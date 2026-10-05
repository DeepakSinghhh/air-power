"""Readiness-Based Sparing — two-echelon VARI-METRIC (Sherbrooke 1986) with prognostic demand.

Echelons: squadron base stores (j) resupplied from the central Equipment Depot (0); every
removed unit goes to its repair agency and returns to the depot after the turnaround time.

    depot pipeline   mu0 = lambda_i * T_i                     (Poisson)
    base pipeline    mu_j = lambda_ij * (O + EBO0(s0) / lambda_i)
    base variance    V_j = lambda_ij*O + f(1-f)*EBO0 + f^2*VBO0,  f = lambda_ij / lambda_i
    availability     A_j = prod_i (1 - EBO_ij / (N_j * QPA_ij)) ^ QPA_ij

Greedy marginal analysis adds the unit with the best availability gain per rupee, tracing the
cost-vs-availability frontier. Demand can come from history ("historical") or from the
prognostic models for the planned flying ("prognostic").
"""
from __future__ import annotations

from dataclasses import dataclass
from math import lgamma, log

import numpy as np
import pandas as pd
from scipy.stats import nbinom, poisson

from ..domain.catalog import LRU_TYPES, SQUADRONS, TRANSIT_DAYS
from ..twin.state import ED, ENGINE_IDX, LRU_IDS, SP_IDS, SP_IDX, TYPE_IDS, FleetState

MAX_STOCK = 60


def _ebo_vbo(mean: float, var: float, smax: int = MAX_STOCK) -> tuple[np.ndarray, np.ndarray]:
    """Expected backorders and backorder variance for stock levels 0..smax."""
    x = np.arange(0, int(mean + 12 * np.sqrt(max(var, mean, 1e-6)) + smax + 5))
    if mean <= 0:
        return np.zeros(smax + 1), np.zeros(smax + 1)
    if var > mean * 1.0001:
        p = mean / var
        r = mean * p / (1 - p)
        pmf = nbinom.pmf(x, r, p)
    else:
        pmf = poisson.pmf(x, mean)
    ebo = np.array([((x - s).clip(0) * pmf).sum() for s in range(smax + 1)])
    e2 = np.array([(((x - s).clip(0)) ** 2 * pmf).sum() for s in range(smax + 1)])
    return ebo, e2 - ebo ** 2


@dataclass
class SparingProblem:
    lam: np.ndarray            # [lru, base] removals/day
    tat: np.ndarray            # [lru] days
    qpa: np.ndarray            # [lru, base]
    n_ac: np.ndarray           # [base]
    cost: np.ndarray           # [lru] lakh ₹
    bases: list[str]

    @property
    def n_lru(self) -> int:
        return self.lam.shape[0]

    def __post_init__(self):
        self._dep: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._base: dict[tuple[int, int, int], np.ndarray] = {}

    # ------------------------------------------------------------ cached pipeline maths
    def _depot(self, i: int) -> tuple[np.ndarray, np.ndarray]:
        if i not in self._dep:
            m = self.lam[i].sum() * self.tat[i]
            self._dep[i] = _ebo_vbo(m, m)
        return self._dep[i]

    def _base_ebo_arr(self, i: int, s0: int, j: int) -> np.ndarray:
        key = (i, min(s0, MAX_STOCK), j)
        if key not in self._base:
            lam_i = self.lam[i].sum()
            lj = self.lam[i, j]
            if lam_i <= 0 or lj <= 0:
                self._base[key] = np.zeros(MAX_STOCK + 1)
            else:
                ebo0, vbo0 = self._depot(i)
                e0, v0 = ebo0[key[1]], vbo0[key[1]]
                f = lj / lam_i
                mean = lj * (TRANSIT_DAYS + e0 / lam_i)
                var = lj * TRANSIT_DAYS + f * (1 - f) * e0 + f * f * v0
                self._base[key] = _ebo_vbo(mean, max(var, mean))[0]
        return self._base[key]

    def c(self, i: int, s0: int, j: int, sj: int) -> float:
        """Contribution of type i to log-availability of base j."""
        z = self.qpa[i, j]
        if z == 0:
            return 0.0
        ebo = self._base_ebo_arr(i, s0, j)[min(sj, MAX_STOCK)]
        return z * log(max(1e-9, 1 - ebo / (self.n_ac[j] * z)))

    def base_ebo(self, i: int, s0: int, s: np.ndarray) -> np.ndarray:
        return np.array([self._base_ebo_arr(i, s0, j)[min(int(s[j]), MAX_STOCK)] for j in range(len(self.bases))])

    def availability(self, s0: np.ndarray, s: np.ndarray) -> tuple[float, np.ndarray]:
        """Fleet supply availability and per-base availabilities."""
        nb = len(self.bases)
        logA = np.zeros(nb)
        for i in range(self.n_lru):
            for j in range(nb):
                logA[j] += self.c(i, int(s0[i]), j, int(s[i, j]))
        A = np.exp(logA)
        return float((A * self.n_ac).sum() / self.n_ac.sum()), A

    # ------------------------------------------------------------ optimisation
    def optimise(self, budget: float, s0_init: np.ndarray | None = None, s_init: np.ndarray | None = None,
                 record_curve: bool = True):
        """Greedy marginal analysis on the aircraft-weighted log-availability (separable by type)."""
        nb = len(self.bases)
        s0 = np.zeros(self.n_lru, int) if s0_init is None else s0_init.copy()
        s = np.zeros((self.n_lru, nb), int) if s_init is None else s_init.copy()
        spent = float((self.cost * (s0 + s.sum(1))).sum())

        def best_option(i):
            if self.lam[i].sum() <= 0:
                return None
            cur = [self.c(i, s0[i], j, s[i, j]) for j in range(nb)]
            # depot +1 affects every base
            g_ed = sum(self.n_ac[j] * (self.c(i, s0[i] + 1, j, s[i, j]) - cur[j]) for j in range(nb))
            best = (g_ed / self.cost[i], "ED", None)
            for j in range(nb):
                if self.qpa[i, j] == 0 or self.lam[i, j] <= 0:
                    continue
                g = self.n_ac[j] * (self.c(i, s0[i], j, s[i, j] + 1) - cur[j]) / self.cost[i]
                if g > best[0]:
                    best = (g, "B", j)
            return best

        opts = {i: best_option(i) for i in range(self.n_lru)}
        curve = [(spent, self.availability(s0, s)[0])] if record_curve else []
        k = 0
        while True:
            cand = [(o[0], i) for i, o in opts.items() if o is not None and spent + self.cost[i] <= budget + 1e-9]
            if not cand:
                break
            g, i = max(cand)
            if g <= 1e-12:
                break
            _, kind, j = opts[i]
            if kind == "ED":
                s0[i] += 1
            else:
                s[i, j] += 1
            spent += self.cost[i]
            opts[i] = best_option(i)
            k += 1
            if record_curve and k % 5 == 0:
                curve.append((spent, self.availability(s0, s)[0]))
        A_now = self.availability(s0, s)[0]
        if record_curve:
            curve.append((spent, A_now))
        return s0, s, A_now, curve


def build_problem(state: FleetState, demand: str = "prognostic", belief=None, horizon_days: int = 90) -> SparingProblem:
    from ..datagen import history

    bases = [sq.base for sq in SQUADRONS.values()]
    nb = len(bases)
    n = len(LRU_IDS)
    lam = np.zeros((n, nb))
    rem = history.load("removals")
    tails = history.load("tails").set_index("tail")
    last = rem[rem["day"] >= rem["day"].max() - 365].copy()
    last["base"] = last["tail"].map(tails["base"])
    hist_rate = last.groupby(["lru", "base"]).size() / 365.0
    nff_rate = last[last["finding"] == "NFF"].groupby(["lru", "base"]).size() / 365.0
    if demand == "prognostic" and belief is not None:
        risk = belief.risk_fn(state, horizon_days)
        for p, r in enumerate(risk):
            if state.pos_serial[p] < 0:
                continue
            j = bases.index(SP_IDS[state.tail_sp[state.pos_tail[p]]])
            lam[state.pos_type[p], j] += r / horizon_days
        for (lru, b), v in nff_rate.items():
            lam[LRU_IDS.index(lru), bases.index(b)] += v
        # replacement units keep failing after the first: blend toward the long-run rate
        long_run = np.zeros_like(lam)
        for (lru, b), v in hist_rate.items():
            long_run[LRU_IDS.index(lru), bases.index(b)] = v
        lam = 0.7 * lam + 0.3 * long_run
    else:
        for (lru, b), v in hist_rate.items():
            lam[LRU_IDS.index(lru), bases.index(b)] = v
    rep = history.load("repairs")
    tat = rep.assign(t=rep["return_day"] - rep["sent_day"]).groupby("lru")["t"].mean()
    tat_arr = np.array([float(tat.get(l, LRU_TYPES[l].tat_days)) for l in LRU_IDS])
    qpa = np.zeros((n, nb), int)
    n_ac = np.zeros(nb)
    for j, sq in enumerate(SQUADRONS.values()):
        n_ac[j] = sq.n_aircraft
        for i, l in enumerate(LRU_IDS):
            qpa[i, j] = LRU_TYPES[l].qpa[sq.type]
    cost = np.array([LRU_TYPES[l].cost_lakh for l in LRU_IDS])
    return SparingProblem(lam=lam, tat=tat_arr, qpa=qpa, n_ac=n_ac, cost=cost, bases=bases)


def current_allocation(state: FleetState, prob: SparingProblem) -> tuple[np.ndarray, np.ndarray]:
    """Inventory position per echelon: depot = ED on-hand + repair pipeline; base = on-hand + inbound."""
    n, nb = prob.n_lru, len(prob.bases)
    s0 = np.zeros(n, int)
    s = np.zeros((n, nb), int)
    for (sp, li), lst in state.stock.items():
        if sp == ED:
            s0[li] += len(lst)
        else:
            s[li, prob.bases.index(SP_IDS[sp])] += len(lst)
    for (_, ser, condemned) in state.pipeline:
        s0[int(state.ser_type[ser])] += 1
    for (_, sp, ser, pos) in state.shipments:
        li = int(state.ser_type[ser])
        if pos >= 0:
            continue   # reserved for an open demand; not stock
        s[li, prob.bases.index(SP_IDS[sp])] += 1
    for (_, li) in state.procurement:
        s0[li] += 1
    return s0, s


def recommend(state: FleetState, belief=None, demand: str = "prognostic") -> dict:
    prob = build_problem(state, demand, belief)
    s0c, sc = current_allocation(state, prob)
    budget = float((prob.cost * (s0c + sc.sum(1))).sum())
    A_cur, A_cur_base = prob.availability(s0c, sc)
    s0o, so, A_opt, curve = prob.optimise(budget)
    _, A_opt_base = prob.availability(s0o, so)
    rows = []
    for i, l in enumerate(LRU_IDS):
        row = {"lru": l, "name": LRU_TYPES[l].name, "cost_lakh": LRU_TYPES[l].cost_lakh,
               "demand_per_month": float(prob.lam[i].sum() * 30), "tat_days": float(prob.tat[i]),
               "current_depot": int(s0c[i]), "rbs_depot": int(s0o[i]),
               "current_total": int(s0c[i] + sc[i].sum()), "rbs_total": int(s0o[i] + so[i].sum())}
        for j, b in enumerate(prob.bases):
            row[f"current_{b}"] = int(sc[i, j])
            row[f"rbs_{b}"] = int(so[i, j])
        rows.append(row)
    # thin the curve for the UI
    step = max(1, len(curve) // 80)
    return {
        "demand": demand, "budget_lakh": budget,
        "availability_current": A_cur, "availability_rbs": A_opt,
        "base_current": dict(zip(prob.bases, A_cur_base.tolist())),
        "base_rbs": dict(zip(prob.bases, A_opt_base.tolist())),
        "curve": [{"cost_lakh": c, "availability": a} for c, a in curve[::step]] + [{"cost_lakh": curve[-1][0], "availability": curve[-1][1]}],
        "table": rows, "_s0": s0o.tolist(), "_s": so.tolist(), "bases": prob.bases,
    }


def stock_override_from(state: FleetState, rec: dict) -> dict:
    """Translate an RBS inventory-position target into on-hand stock for a twin experiment.

    Assets already in the repair pipeline or reserved in transit count toward the depot / base
    position; on-hand quantities are set to the remainder (never negative)."""
    prob_bases = rec["bases"]
    s0 = np.array(rec["_s0"])
    s = np.array(rec["_s"])
    pipe = np.zeros(len(LRU_IDS), int)
    for (_, ser, _) in state.pipeline:
        pipe[int(state.ser_type[ser])] += 1
    for (_, li) in state.procurement:
        pipe[li] += 1
    out = {}
    for i in range(len(LRU_IDS)):
        out[(ED, i)] = int(max(0, s0[i] - pipe[i]))
        for j, b in enumerate(prob_bases):
            out[(SP_IDX[b], i)] = int(s[i, j])
    return out
