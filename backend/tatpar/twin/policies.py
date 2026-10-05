"""Sustainment policies the Fleet Twin can run.

``BASELINE`` approximates current reactive practice. ``TATPAR`` switches on every lever the
platform recommends. Individual levers can be toggled to measure their marginal effect.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Optional

import numpy as np


@dataclass
class Policy:
    name: str
    dispatch: str = "max_residual"          # max_residual | flow | plan
    lateral_after_days: int = 7             # reactive lateral transfer after N days AOG
    cann: str = "adhoc"                     # none | adhoc | consolidated
    cann_after_days: int = 2
    adhoc_rob_mc_prob: float = 0.35         # ad-hoc practice sometimes robs a serviceable aircraft
    overlap_checks_with_nmcs: bool = False  # do scheduled work while awaiting spares
    bundling: bool = False                  # pull predicted replacements into planned checks
    bundle_threshold: float = 0.5
    proactive_spares: bool = False          # weekly pre-positioning from predicted demand
    nff_screen: bool = False                # re-test before removal when P(NFF) is high
    nff_tpr: float = 0.0                    # measured classifier sensitivity on NFF
    nff_fpr: float = 0.0                    # measured false-positive rate on true failures
    early_phase: bool = False               # start a phase early when a bay is idle and residual is small
    plan: Optional[dict] = None             # FMP plan: {"hours": {tail: [h per day]}, "checks": [(tail, check, day)]}
    risk_fn: Optional[Callable] = field(default=None, repr=False)   # (state, horizon_days) -> risk per position

    def with_(self, **kw) -> "Policy":
        return replace(self, **kw)


BASELINE = Policy("Current practice")

TATPAR = Policy(
    "TATPAR",
    dispatch="flow",
    lateral_after_days=1,
    cann="consolidated",
    overlap_checks_with_nmcs=True,
    bundling=True,
    proactive_spares=True,
    nff_screen=True,
    nff_tpr=0.47,          # measured on held-out snags (see artifacts/metrics.json)
    nff_fpr=0.08,
    early_phase=False,     # ablation: no benefit once the phase-flow plan is in place
)

LEVERS = {
    "flow": dict(dispatch="flow"),
    "overlap": dict(overlap_checks_with_nmcs=True),
    "bundling": dict(bundling=True),
    "spares": dict(proactive_spares=True, lateral_after_days=1),
    "cann": dict(cann="consolidated"),
    "nff": dict(nff_screen=True),
}
LEVER_LABELS = {
    "flow": "Phase-flow flying plan (staggered checks)",
    "overlap": "Scheduled work while awaiting spares",
    "bundling": "Bundle predicted replacements into checks",
    "spares": "Predictive spares positioning + fast lateral",
    "cann": "Consolidated cannibalisation",
    "nff": "No-Fault-Found screening before removal",
}


def demand_profile(sorties_weekday: int, sorties_saturday: int, weekday: int) -> int:
    if weekday < 5:
        return sorties_weekday
    if weekday == 5:
        return sorties_saturday
    return 0


def no_risk(state, horizon_days) -> np.ndarray:  # pragma: no cover - trivial
    return np.zeros(len(state.pos_tail))
