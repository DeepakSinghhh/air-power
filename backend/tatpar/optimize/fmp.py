"""Prognostics-aware Flight & Maintenance Planning (FMP) with OR-Tools CP-SAT.

For each squadron over a rolling horizon (default 30 days) decide sorties per tail per day and
the start day of each phase check, in the spirit of Kozanidis (Hellenic AF) and Peschiera et al.
(French AF), extended with:

* a readiness requirement (minimum *capable* aircraft on given days),
* a phase-flow objective that keeps tails staggered along an even ladder of residual hours,
* an engine risk cap: a tail may not fly past the conformal lower bound of its engine's RUL
  unless the engine change is bundled into a phase check first.

Units: flying time in half-hours so every quantity is integer.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from ortools.sat.python import cp_model

from ..config import FH_PER_CYCLE
from ..domain.catalog import AIRCRAFT_TYPES, SQUADRONS
from ..twin.policies import demand_profile
from ..twin.simulator import day_to_date
from ..twin.state import CHECKS, ED, ENGINE_IDX, LRU_IDS, SQN_IDS, TYPE_IDS, FleetState


@dataclass
class Requirement:
    sqn: int
    start: int          # day offset from plan start
    end: int
    min_capable: int
    surge: float = 1.0  # flying-task multiplier inside the window


def _ready_day(st: FleetState, t: int) -> int:
    """Earliest day offset the tail can fly (estimate from jobs, checks and part ETAs)."""
    d0 = st.day
    ready = 0
    if st.check_kind[t]:
        ready = max(ready, int(st.check_end[t] - d0))
    if st.unsched_end[t] > d0:
        ready = max(ready, int(st.unsched_end[t] - d0))
    if st.missing[t] > 0:
        eta = 0
        for b in st.backorders:
            if int(st.pos_tail[b["pos"]]) != t:
                continue
            li = b["li"]
            inbound = [arr for (arr, _, _, p) in st.shipments if p == b["pos"]]
            if inbound:
                e = min(inbound) - d0 + 1
            elif st.stock.get((ED, li)):
                e = 4
            else:
                rets = [r for (r, ser, c) in st.pipeline if int(st.ser_type[ser]) == li and not c]
                e = (min(rets) - d0 + 4) if rets else 30
            eta = max(eta, e)
        ready = max(ready, eta)
    return max(0, ready)


# CP-SAT settings. One worker with a deterministic work budget gives the same plan on every machine and
# every run (the plans have many equally optimal solutions; parallel workers picked one by thread timing).
# Measured: all four squadrons still solve to OPTIMAL, in 0.3–3.5 s each.
SOLVER = {"workers": 1, "interleave": False, "det_per_s": 1.0}


def plan_squadron(st: FleetState, sq: int, horizon: int = 30, belief=None, req: Requirement | None = None,
                  time_limit: float = 6.0) -> dict:
    sqd = SQUADRONS[SQN_IDS[sq]]
    ty = AIRCRAFT_TYPES[sqd.type]
    ph = ty.check("phase")
    sh = int(round(ty.sortie_hours * 2))          # half-hours per sortie
    I = int(ph.interval_fh * 2)
    D = ph.duration_days
    m = ty.max_sorties_per_day
    tails = [int(t) for t in np.flatnonzero(st.tail_sqn == sq)]
    n = len(tails)
    H = horizon

    demand = []
    for d in range(H):
        wd = day_to_date(st.day + d).weekday()
        k = demand_profile(sqd.sorties_weekday, sqd.sorties_saturday, wd)
        if req and req.sqn == sq and req.start <= d <= req.end:
            k = int(round(k * req.surge))
        demand.append(k)

    # residual hours (half-hours) to phase; caps from minor/overhaul limits
    resid, cap_other, ready, busy_until, in_depot = [], [], [], [], []
    for t in tails:
        r = int(np.floor((ph.interval_fh - st.hrs_since["phase"][t]) * 2))
        resid.append(max(0, r))
        ov = ty.check("overhaul")
        cap_other.append(max(0, int(np.floor((ov.interval_fh - st.hrs_since["overhaul"][t]) * 2))))
        ready.append(min(H, _ready_day(st, t)))
        busy_until.append(int(st.check_end[t] - st.day) if st.check_kind[t] else 0)
        in_depot.append(st.check_kind[t] == "overhaul")

    # engine risk caps (half-hours) from calibrated HUMS lower bound
    eng_cap = [None] * n
    eng_info = [None] * n
    if belief is not None:
        for k, t in enumerate(tails):
            for p in st.positions_of(t):
                if st.pos_type[p] != ENGINE_IDX or st.pos_serial[p] < 0:
                    continue
                lo, med, hi = belief.engine_quantiles(st, int(st.pos_serial[p]))
                lo_h = int(lo * FH_PER_CYCLE * 2)
                if lo_h < resid[k] + 120:
                    eng_cap[k] = lo_h if eng_cap[k] is None else min(eng_cap[k], lo_h)
                    eng_info[k] = {"lo_fh": lo * FH_PER_CYCLE, "med_fh": med * FH_PER_CYCLE}

    mdl = cp_model.CpModel()
    x, xpre, xpost, b, down, cap = {}, {}, {}, {}, {}, {}
    for k in range(n):
        for d in range(H):
            x[k, d] = mdl.NewIntVar(0, m, f"x{k}_{d}")
            xpre[k, d] = mdl.NewIntVar(0, m, f"xp{k}_{d}")
            xpost[k, d] = mdl.NewIntVar(0, m, f"xq{k}_{d}")
            b[k, d] = mdl.NewBoolVar(f"b{k}_{d}")
            cap[k, d] = mdl.NewBoolVar(f"c{k}_{d}")
            mdl.Add(x[k, d] == xpre[k, d] + xpost[k, d])
            mdl.Add(xpre[k, d] <= m * (1 - b[k, d]))
            mdl.Add(xpost[k, d] <= m * b[k, d])
            if d > 0:
                mdl.Add(b[k, d] >= b[k, d - 1])
        for d in range(H):
            prev = b[k, d - D] if d - D >= 0 else 0
            down[k, d] = mdl.NewBoolVar(f"dn{k}_{d}")
            mdl.Add(down[k, d] == b[k, d] - prev) if not isinstance(prev, int) else mdl.Add(down[k, d] == b[k, d])
            mdl.Add(x[k, d] <= m * (1 - down[k, d]))
            if d < ready[k]:
                mdl.Add(x[k, d] == 0)
        t = tails[k]
        if in_depot[k] or st.check_kind[t] == "phase":
            for d in range(H):
                mdl.Add(b[k, d] == 0)          # no new phase while one is running / at depot
        elif st.check_kind[t]:
            for d in range(min(H, busy_until[k])):
                mdl.Add(b[k, d] == 0)
        mdl.Add(sum(xpre[k, d] for d in range(H)) * sh <= resid[k])
        mdl.Add(sum(x[k, d] for d in range(H)) * sh <= cap_other[k])
        if eng_cap[k] is not None and eng_cap[k] < resid[k]:
            mdl.Add(sum(xpre[k, d] for d in range(H)) * sh <= max(0, eng_cap[k]))
        # capable: available, not in check, and either post-phase or >= 2 sorties of residual left
        for d in range(H):
            mdl.Add(cap[k, d] <= 1 - down[k, d])
            if d < ready[k]:
                mdl.Add(cap[k, d] == 0)
            z = mdl.NewBoolVar(f"z{k}_{d}")
            mdl.Add(cap[k, d] <= b[k, d] + z)
            flown = sum(xpre[k, dd] for dd in range(d)) * sh
            limit = resid[k] if eng_cap[k] is None else min(resid[k], max(0, eng_cap[k]))
            mdl.Add(flown <= limit - 2 * sh).OnlyEnforceIf(z)

    # bays (tails already in phase outside the model occupy capacity until they finish)
    for d in range(H):
        occupied = sum(1 for k, t in enumerate(tails) if st.check_kind[t] == "phase" and busy_until[k] > d)
        mdl.Add(sum(down[k, d] for k in range(n)) <= max(0, sqd.bays - occupied))

    short = [mdl.NewIntVar(0, 100, f"s{d}") for d in range(H)]
    for d in range(H):
        mdl.Add(sum(x[k, d] for k in range(n)) + short[d] >= demand[d])

    req_short = []
    if req and req.sqn == sq:
        for d in range(max(0, req.start), min(H, req.end + 1)):
            rs = mdl.NewIntVar(0, n, f"rs{d}")
            mdl.Add(sum(cap[k, d] for k in range(n)) + rs >= req.min_capable)
            req_short.append(rs)

    # phase-flow ladder: desired hours per tail from surplus over an even ladder of residuals
    order = np.argsort(resid)
    target_res = (I * (np.arange(n) + 0.5) / n).astype(int)
    surplus = np.zeros(n)
    for rank, k in enumerate(order):
        surplus[k] = resid[k] - target_res[rank]
    tot = sum(demand) * sh
    avail_days = np.array([max(0, H - ready[k]) for k in range(n)])
    base = tot / max(1, (avail_days > 0).sum())
    want = np.clip(base + 0.6 * surplus, 0, None) * (avail_days > 0)
    want = want * (tot / max(1, want.sum()))
    dev = []
    for k in range(n):
        hk = sum(x[k, d] for d in range(H)) * sh
        e = mdl.NewIntVar(0, 10 * I, f"dev{k}")
        mdl.Add(e >= hk - int(want[k]))
        mdl.Add(e >= int(want[k]) - hk)
        dev.append(e)

    mdl.Minimize(1000 * sum(short) + 3000 * sum(req_short) + 2 * sum(dev)
                 - 20 * sum(cap[k, d] for k in range(n) for d in range(H))
                 + 5 * sum(down[k, d] for k in range(n) for d in range(H)))
    solver = cp_model.CpSolver()
    # stop on the deterministic work budget, not wall-clock time, so CPU speed cannot change the plan
    solver.parameters.num_workers = SOLVER["workers"]
    solver.parameters.interleave_search = SOLVER["interleave"]
    solver.parameters.random_seed = 0
    solver.parameters.max_deterministic_time = SOLVER["det_per_s"] * time_limit
    solver.parameters.max_time_in_seconds = 60.0   # safety cap only
    res = solver.Solve(mdl)
    ok = res in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    hours, starts, rows = {}, [], []
    for k, t in enumerate(tails):
        tail = st.tail_ids[t]
        hv = [solver.Value(x[k, d]) * ty.sortie_hours if ok else 0.0 for d in range(H)]
        hours[tail] = hv
        sday = next((d for d in range(H) if ok and solver.Value(b[k, d])), None)
        if sday is not None:
            starts.append((tail, "phase", st.day + sday))
        rows.append({"tail": tail, "residual_fh": resid[k] / 2, "ready_day": ready[k], "phase_start": sday,
                     "hours_planned": float(sum(hv)), "target_hours": float(want[k] / 2),
                     "engine_risk": eng_info[k], "engine_cap_fh": (eng_cap[k] / 2 if eng_cap[k] is not None else None),
                     "days": [("phase" if ok and solver.Value(down[k, d]) else
                               ("down" if d < ready[k] else ("fly" if hv[d] > 0 else "idle"))) for d in range(H)]})
    capable = [int(sum(solver.Value(cap[k, d]) for k in range(n))) if ok else 0 for d in range(H)]
    return {
        "squadron": SQN_IDS[sq], "status": solver.StatusName(res), "objective": solver.ObjectiveValue() if ok else None,
        "wall_s": solver.WallTime(), "start_day": st.day, "horizon": H, "demand": demand,
        "short": [solver.Value(v) if ok else None for v in short], "capable": capable,
        "hours": hours, "checks": starts, "tails": rows,
        "requirement": None if not req or req.sqn != sq else {"start": req.start, "end": req.end, "min": req.min_capable},
    }


def plan_fleet(st: FleetState, horizon: int = 30, belief=None, req: Requirement | None = None,
               time_limit: float = 6.0) -> dict:
    plans = [plan_squadron(st, k, horizon, belief, req, time_limit) for k in range(len(SQN_IDS))]
    hours, checks = {}, []
    for p in plans:
        hours.update(p["hours"])
        checks += p["checks"]
    return {"start_day": st.day, "horizon": horizon, "hours": hours, "checks": checks, "squadrons": plans}


def phase_ladder(st: FleetState) -> list[dict]:
    """Residual hours to phase per tail vs the ideal evenly staggered ladder (for the flow chart)."""
    out = []
    for k, q in enumerate(SQN_IDS):
        tails = np.flatnonzero(st.tail_sqn == k)
        ty = AIRCRAFT_TYPES[TYPE_IDS[st.tail_type[tails[0]]]]
        iv = ty.check("phase").interval_fh
        res = sorted(((iv - st.hrs_since["phase"][t], st.tail_ids[t], st.check_kind[t]) for t in tails), reverse=True)
        n = len(res)
        for rank, (r, tail, ck) in enumerate(res):
            out.append({"squadron": q, "tail": tail, "residual_fh": float(r), "ideal_fh": float(iv * (n - rank - 0.5) / n),
                        "in_check": ck, "interval_fh": iv})
    return out
