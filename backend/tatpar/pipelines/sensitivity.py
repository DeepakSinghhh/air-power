"""Sensitivity of the headline result to the Fleet Twin's assumptions.

The +20-point gain is measured on a *notional* fleet whose failure rates, repair times, stock,
bays and flying task are assumptions. This study changes one assumption at a time (and the
prognostic models' accuracy) and re-measures current practice vs the full TATPAR policy over one
year of hidden-truth futures with common random numbers. The analytics are *not* refitted to the
changed world, so the models are also mis-specified in every row — a conservative test.

    python -m tatpar.pipelines.sensitivity            # ~3 min on a 4-core laptop
    python -m tatpar.pipelines.sensitivity --quick
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np

from ..config import ARTIFACTS_DIR
from ..datagen import history
from ..optimize.sparing import recommend, stock_override_from
from ..prognostics.belief import Belief
from ..twin.montecarlo import forecast
from ..twin.policies import BASELINE, TATPAR
from ..twin.simulator import Scenario

BENCH_DIR = ARTIFACTS_DIR / "bench"

# (key, group, label, scenario kwargs, policy kwargs applied to TATPAR only)
CASES: list[tuple[str, str, str, dict, dict]] = [
    ("reference", "Reference", "As modelled", {}, {}),
    ("fail_up", "LRU failure rate", "+30 % failures", {"life_mult": 1 / 1.3}, {}),
    ("fail_down", "LRU failure rate", "−30 % failures", {"life_mult": 1 / 0.7}, {}),
    ("tat_up", "Repair turnaround (BRD / HAL)", "+30 % slower", {"tat_mult": 1.3}, {}),
    ("tat_down", "Repair turnaround (BRD / HAL)", "−30 % faster", {"tat_mult": 0.7}, {}),
    ("stock_down", "Spares inventory", "−40 % stock", {"stock_mult": 0.6}, {}),
    ("stock_up", "Spares inventory", "+40 % stock", {"stock_mult": 1.4}, {}),
    ("task_up", "Flying task", "+20 % sorties", {"task_mult": 1.2}, {}),
    ("task_down", "Flying task", "−20 % sorties", {"task_mult": 0.8}, {}),
    ("bays", "Hangar capacity", "2 bays per squadron", {"extra_bays": 1}, {}),
    ("risk_low", "Prognostic model error", "risk under-predicted ×0.6", {"risk_mult": 0.6}, {}),
    ("risk_high", "Prognostic model error", "risk over-predicted ×1.5", {"risk_mult": 1.5}, {}),
    ("nff_weak", "Prognostic model error", "NFF classifier half as sensitive", {}, {"nff_tpr_mult": 0.5}),
    ("risk_off", "Prognostic model error", "no prognostics at all (risk = 0)", {"risk_mult": 0.0}, {}),
    ("rbs_hist", "Prognostic model error", "spares sized on last year's demand", {}, {"rbs": "historical"}),
]


def _ci(x: np.ndarray) -> tuple[float, float]:
    return float(x.mean()), float(1.96 * x.std(ddof=1) / np.sqrt(len(x)))


def run(quick: bool = False, reps: int | None = None) -> dict:
    t0 = time.time()
    st = history.load_state()
    belief = Belief.load()
    nff = json.loads((ARTIFACTS_DIR / "metrics.json").read_text())["nff"]
    base = BASELINE.with_(risk_fn=belief.risk_fn, nff_tpr=nff["tpr"], nff_fpr=nff["fpr"])
    tat = TATPAR.with_(risk_fn=belief.risk_fn, nff_tpr=nff["tpr"], nff_fpr=nff["fpr"])
    ov = stock_override_from(st, recommend(st, belief, "prognostic"))
    ov_hist = stock_override_from(st, recommend(st, belief, "historical"))
    reps = reps or (8 if quick else 24)
    rows = []
    for key, group, label, sc_kw, pol_kw in CASES:
        sc = Scenario(**sc_kw)
        t_pol = tat.with_(nff_tpr=nff["tpr"] * pol_kw["nff_tpr_mult"]) if "nff_tpr_mult" in pol_kw else tat
        fb = forecast(st, base, 365, reps, belief, scenario=sc, mode="truth_resampled", seed0=9000)
        ft = forecast(st, t_pol, 365, reps, belief, scenario=sc, mode="truth_resampled", seed0=9000,
                      stock_override=ov_hist if pol_kw.get("rbs") == "historical" else ov)
        xb = fb.mc_total.mean(1) / st.n_tails
        xt = ft.mc_total.mean(1) / st.n_tails
        d, ci = _ci(xt - xb)
        rows.append({"key": key, "group": group, "label": label, "baseline_mc": float(xb.mean()), "tatpar_mc": float(xt.mean()),
                     "delta": d, "delta_ci": ci, "aircraft": d * st.n_tails,
                     "baseline_share": fb.state_share(), "tatpar_share": ft.state_share()})
        print(f"{label:38s} {xb.mean():6.1%} -> {xt.mean():6.1%}  {d * 100:+5.1f} ± {ci * 100:.1f} pts")
    ref = rows[0]["delta"]
    others = [r["delta"] for r in rows[1:]] or [ref]
    out = {"days": 365, "reps": reps, "mode": "truth_resampled", "rows": rows,
           "min_delta": float(min(others)), "max_delta": float(max(others)), "reference_delta": ref,
           "all_positive": bool(all(r["delta"] - r["delta_ci"] > 0 for r in rows)),
           "elapsed_s": time.time() - t0}
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    (BENCH_DIR / "sensitivity.json").write_text(json.dumps(out))
    return out


def doc_lines() -> list[str]:
    """Markdown section for docs/04-evaluation.md (empty if the study has not been run)."""
    p = BENCH_DIR / "sensitivity.json"
    if not p.exists():
        return []
    s = json.loads(p.read_text())
    lines = [
        "", f"## 5b. Does the gain survive different assumptions? (one year, {s['reps']} hidden-truth futures each)", "",
        "Each row changes one assumption of the notional fleet and re-measures current practice against the full "
        "TATPAR policy on the same random futures. The models are **not** refitted to the changed world, so they are "
        "also mis-specified in every row.", "",
        "| Assumption | Change | Current practice | With TATPAR | Gain (95 % CI) | ≈ aircraft / day |",
        "|---|---|---|---|---|---|",
    ]
    for r in s["rows"]:
        lines.append(f"| {r['group']} | {r['label']} | {r['baseline_mc'] * 100:.1f} % | {r['tatpar_mc'] * 100:.1f} % | "
                     f"**{r['delta'] * 100:+.1f} ± {r['delta_ci'] * 100:.1f} pts** | {r['aircraft']:.1f} |")
    lines += ["", f"Across every change the gain stays between **{s['min_delta'] * 100:+.1f}** and "
                  f"**{s['max_delta'] * 100:+.1f}** points (reference {s['reference_delta'] * 100:+.1f})"
                  + (", and its 95 % interval excludes zero in every row." if s["all_positive"] else "."),
              "", "Reading the prognostic rows: over a whole year almost all of the gain comes from readiness-based sparing and "
                  "the phase-flow plan, so biased or missing risk scores barely move the *average*. The models earn their keep "
                  "in the short-horizon decisions instead — which aircraft to protect, which engine to change at the next "
                  "phase, and P(meet) for a specific requirement (sections 1, 6)."]
    return lines


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    run(a.quick)
