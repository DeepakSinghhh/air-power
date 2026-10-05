"""Readiness-backward planning: "N mission-capable aircraft at squadron S from D+a to D+b".

Levers are added one at a time and each is scored by Monte-Carlo in the Fleet Twin with the same
random seeds (common random numbers), so the gain attributed to every action is a like-for-like
difference in P(meet requirement):

    0. current practice
    1. flight & maintenance plan (CP-SAT, requirement-aware, engine risk caps) + phase-flow flying
    2. predictive spares transfers into the squadron ahead of the window (+ fast lateral)
    3. depot repair expedite for the parts most likely to ground the squadron
    4. consolidated cannibalisation + No-Fault-Found screening + scheduled work while AOG
"""
from __future__ import annotations

import time

from ..domain.catalog import SQUADRONS
from ..twin.montecarlo import forecast
from ..twin.policies import BASELINE, TATPAR
from ..twin.simulator import Scenario, day_to_date
from ..twin.state import SQN_IDS, FleetState
from .advisors import apply_expedite, apply_transfers, expedite_candidates, transfer_plan
from .fmp import Requirement, plan_fleet


def plan_requirement(st: FleetState, belief, sqn: int, start: int, end: int, min_mc: int, surge: float = 1.0,
                     reps: int = 80, nff_tpr: float = 0.47, nff_fpr: float = 0.08, seed0: int = 4242) -> dict:
    t0 = time.time()
    horizon = end + 6
    scen = Scenario(surges=[(sqn, st.day + start, st.day + end, surge)] if surge != 1.0 else [])
    base_pol = BASELINE.with_(nff_tpr=nff_tpr, nff_fpr=nff_fpr)
    steps = []

    def score(state, pol, label, lever, details):
        f = forecast(state, pol, horizon, reps, belief, scen, mode="belief", seed0=seed0)
        p = f.p_meet(sqn, start, end, min_mc)
        win = f.mc_sq[:, start:end + 1, sqn]
        steps.append({"lever": lever, "label": label, "p_meet": p, "mean_mc_window": float(win.mean()),
                      "p10_window": float(min(f.bands(sqn)["p10"][start:end + 1])),
                      "daily_p_meet": f.p_meet_daily(sqn, min_mc), "bands": f.bands(sqn), "details": details})
        return f

    score(st, base_pol, "Current practice", "baseline", [])

    # 1 — requirement-aware flight & maintenance plan
    req = Requirement(sqn, start, end, min_mc, surge)
    plan = plan_fleet(st, horizon, belief, req, time_limit=5.0)
    sp = next(p for p in plan["squadrons"] if p["squadron"] == SQN_IDS[sqn])
    pol1 = base_pol.with_(dispatch="plan", plan=plan, bundling=True, risk_fn=belief.risk_fn)
    phase_moves = [{"tail": r["tail"], "phase_start": f"D+{r['phase_start']}"} for r in sp["tails"] if r["phase_start"] is not None]
    held = [{"tail": r["tail"], "reason": f"engine lower-bound RUL {r['engine_cap_fh']:.0f} FH"} for r in sp["tails"]
            if r["engine_cap_fh"] is not None and r["engine_cap_fh"] < r["residual_fh"]]
    score(st, pol1, "Requirement-aware flying & maintenance plan", "plan",
          [{"type": "phase", **m} for m in phase_moves] + [{"type": "engine_protect", **h} for h in held])

    # 2 — predictive spares into the squadron base
    st2 = st.copy()
    base = SQUADRONS[SQN_IDS[sqn]].base
    moves = transfer_plan(st2, belief, horizon_days=end + 3, z=1.28, bases=[base])
    apply_transfers(st2, moves)
    pol2 = pol1.with_(proactive_spares=True, lateral_after_days=1)
    score(st2, pol2, "Pre-position spares at " + base.title(), "spares",
          [{"type": "transfer", **m} for m in moves])

    # 3 — depot expedite
    st3 = st2.copy()
    exp = expedite_candidates(st3, belief, sqn, horizon_days=end + 3, k=6)
    apply_expedite(st3, exp)
    score(st3, pol2, "Expedite critical repairs at BRD / HAL", "expedite", [{"type": "expedite", **e} for e in exp])

    # 4 — logistics leaks
    pol4 = pol2.with_(cann="consolidated", nff_screen=True, overlap_checks_with_nmcs=True)
    score(st3, pol4, "Consolidated cannibalisation + NFF screening", "leaks",
          [{"type": "policy", "text": "Rob only aircraft already grounded longest; never a serviceable one"},
           {"type": "policy", "text": "Ground re-test before removing units with high No-Fault-Found probability"}])

    for i, s in enumerate(steps):
        s["gain"] = 0.0 if i == 0 else s["p_meet"] - steps[i - 1]["p_meet"]
    return {
        "squadron": SQN_IDS[sqn], "squadron_name": SQUADRONS[SQN_IDS[sqn]].name, "base": base,
        "window": {"start": start, "end": end, "start_date": str(day_to_date(st.day + start)),
                   "end_date": str(day_to_date(st.day + end))},
        "min_mc": min_mc, "surge": surge, "reps": reps, "horizon": horizon,
        "steps": steps, "plan": sp, "elapsed_s": time.time() - t0,
    }
