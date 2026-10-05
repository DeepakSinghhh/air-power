"""Decision-engine benchmark and UI cache.

Runs the Monte-Carlo experiments behind every headline number and stores them as JSON under
``artifacts/bench`` (served by the API), then writes ``docs/04-evaluation.md``.

    python -m tatpar.pipelines.bench            # ~12 min on a 4-core laptop (incl. sensitivity)
    python -m tatpar.pipelines.bench --quick    # fewer replications (does not rewrite the docs)
"""
from __future__ import annotations

import argparse
import json
import time

import numpy as np

from ..config import ARTIFACTS_DIR, REPO_DIR
from ..datagen import history
from ..domain.environment import base_table
from ..optimize.advisors import cannibalisation_advice, expedite_candidates, transfer_plan
from ..optimize.fmp import phase_ladder, plan_fleet
from ..optimize.requirement import plan_requirement
from ..optimize.sparing import recommend, stock_override_from
from ..federated import fedavg
from . import sensitivity
from ..prognostics.belief import Belief
from ..twin.kpis import forecast_waterfall, history_waterfall, monthly_mc, pareto_causes
from ..twin.montecarlo import forecast
from ..twin.policies import BASELINE, TATPAR
from ..twin.simulator import Simulator
from ..twin.state import SQN_IDS

BENCH_DIR = ARTIFACTS_DIR / "bench"
DEMO_REQ = {"sqn": 0, "start": 14, "end": 17, "min_mc": 9, "surge": 1.2}


def _save(name: str, obj) -> None:
    BENCH_DIR.mkdir(parents=True, exist_ok=True)
    (BENCH_DIR / f"{name}.json").write_text(json.dumps(obj, default=_default))


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(type(o))


def _ci(x: np.ndarray) -> tuple[float, float]:
    return float(x.mean()), float(1.96 * x.std(ddof=1) / np.sqrt(len(x)))


def run(quick: bool = False) -> dict:
    t0 = time.time()
    st = history.load_state()
    belief = Belief.load()
    metrics = json.loads((ARTIFACTS_DIR / "metrics.json").read_text())
    nff = metrics["nff"]
    tat = TATPAR.with_(risk_fn=belief.risk_fn, nff_tpr=nff["tpr"], nff_fpr=nff["fpr"])
    reps = 60 if quick else 150
    ab_reps = 12 if quick else 24

    # ---------------------------------------------------------------- forecasts
    fb = forecast(st, BASELINE, 60, reps, belief)
    ft = forecast(st, tat, 60, reps, belief)
    truth = forecast(st, BASELINE, 60, reps, belief, mode="truth_resampled", seed0=5000)
    bands = fb.bands()
    cov80 = float(((truth.mc_total >= np.array(bands["p10"])) & (truth.mc_total <= np.array(bands["p90"]))).mean())
    cov50 = float(((truth.mc_total >= np.array(bands["p25"])) & (truth.mc_total <= np.array(bands["p75"]))).mean())
    _save("forecast", {
        "start_day": st.day, "days": 60, "reps": reps,
        "baseline": {"fleet": fb.bands(), "squadrons": {q: fb.bands(k) for k, q in enumerate(SQN_IDS)},
                     "state_share": fb.state_share(), "mc_rate": fb.mc_rate()},
        "tatpar": {"fleet": ft.bands(), "squadrons": {q: ft.bands(k) for k, q in enumerate(SQN_IDS)},
                   "state_share": ft.state_share(), "mc_rate": ft.mc_rate()},
        "calibration": {"coverage_p10_p90": cov80, "coverage_p25_p75": cov50, "truth_mc_rate": truth.mc_rate(),
                        "belief_mc_rate": fb.mc_rate()},
    })

    # ---------------------------------------------------------------- RBS
    rbs_p = recommend(st, belief, "prognostic")
    rbs_h = recommend(st, belief, "historical")
    ov = stock_override_from(st, rbs_p)
    _save("rbs", {"prognostic": {k: v for k, v in rbs_p.items() if not k.startswith("_")},
                  "historical": {k: v for k, v in rbs_h.items() if not k.startswith("_")}})

    # ---------------------------------------------------------------- lever study (1 year, CRN)
    base_pol = BASELINE.with_(risk_fn=belief.risk_fn, nff_tpr=nff["tpr"], nff_fpr=nff["fpr"])
    steps = [
        ("Current practice", None, None),
        ("+ Readiness-based sparing (same budget)", None, ov),
        ("+ Phase-flow flying plan", dict(dispatch="flow"), ov),
        ("+ Consolidated cannibalisation", dict(dispatch="flow", cann="consolidated"), ov),
        ("+ Predictive spares & fast lateral", dict(dispatch="flow", cann="consolidated", proactive_spares=True, lateral_after_days=1), ov),
        ("+ Bundle engine changes into checks", dict(dispatch="flow", cann="consolidated", proactive_spares=True, lateral_after_days=1, bundling=True), ov),
        ("+ No-Fault-Found screening", dict(dispatch="flow", cann="consolidated", proactive_spares=True, lateral_after_days=1, bundling=True, nff_screen=True), ov),
        ("+ Scheduled work while awaiting spares", dict(dispatch="flow", cann="consolidated", proactive_spares=True, lateral_after_days=1, bundling=True, nff_screen=True, overlap_checks_with_nmcs=True), ov),
    ]
    lever_rows, prev, first, shares = [], None, None, {}
    for label, kw, o in steps:
        pol = base_pol if kw is None else base_pol.with_(**kw)
        f = forecast(st, pol, 365, ab_reps, belief, mode="truth_resampled", stock_override=o, seed0=9000)
        x = f.mc_total.mean(1) / st.n_tails
        row = {"label": label, "mc": _ci(x)[0], "mc_ci": _ci(x)[1], "state_share": f.state_share(),
               "sortie_shortfall": float(f.short.sum((1, 2)).mean())}
        if prev is not None:
            row["delta"], row["delta_ci"] = _ci(x - prev)
        else:
            first = x
        lever_rows.append(row)
        shares[label] = f.state_share()
        prev = x
    total = prev - first
    _save("levers", {"days": 365, "reps": ab_reps, "mode": "truth_resampled", "rows": lever_rows,
                     "total_delta": _ci(total)[0], "total_ci": _ci(total)[1],
                     "aircraft_equivalent": float(_ci(total)[0] * st.n_tails)})

    # ---------------------------------------------------------------- sensitivity to the twin's assumptions
    sens = sensitivity.run(quick)

    # ---------------------------------------------------------------- waterfall
    status = history.load("status")
    _save("waterfall", {
        "history": history_waterfall(status, st.n_tails),
        "forward": forecast_waterfall(shares[steps[0][0]], shares[steps[-1][0]], st.n_tails, 365),
        "monthly": monthly_mc(status),
        "pareto": pareto_causes(history.load("snags")),
    })

    # ---------------------------------------------------------------- phase flow (bunching) demo
    ladders = {"now": phase_ladder(st)}
    for name, pol in (("baseline_180d", BASELINE), ("flow_180d", BASELINE.with_(dispatch="flow"))):
        s2 = st.copy()
        sim = Simulator(s2, pol, seed=11).run(180)
        ladders[name] = phase_ladder(s2)
        ladders[name + "_wait_share"] = float((sim.status_array() == 5).mean())
    _save("ladder", ladders)

    # ---------------------------------------------------------------- plans & advisors
    plan = plan_fleet(st, 30, belief)
    _save("plan", plan)
    _save("advisors", {"transfers": transfer_plan(st, belief, 14), "cannibalisation": cannibalisation_advice(st),
                       "expedite": expedite_candidates(st, belief, None, 30, 10)})
    req = plan_requirement(st, belief, DEMO_REQ["sqn"], DEMO_REQ["start"], DEMO_REQ["end"], DEMO_REQ["min_mc"],
                           DEMO_REQ["surge"], reps=80 if quick else 120, nff_tpr=nff["tpr"], nff_fpr=nff["fpr"])
    _save("requirement_demo", req)
    _save("environment", base_table())
    fed = fedavg.run(rounds=80 if quick else 200, verbose=True)

    summary = {
        "elapsed_s": time.time() - t0,
        "forecast_calibration": {"p10_p90": cov80, "p25_p75": cov50},
        "levers": [(r["label"], round(r["mc"] * 100, 1), round(r.get("delta", 0) * 100, 1)) for r in lever_rows],
        "requirement": [(s["label"], round(s["p_meet"], 2)) for s in req["steps"]],
        "rbs": {"budget_lakh": rbs_p["budget_lakh"], "A_current": rbs_p["availability_current"],
                "A_rbs": rbs_p["availability_rbs"]},
        "federated": {r["regime"]: round(r["rmse"], 2) for r in fed["results"]},
        "sensitivity": {"min_delta": sens["min_delta"], "max_delta": sens["max_delta"], "all_positive": sens["all_positive"]},
    }
    _save("summary", summary)
    if not quick:   # the published numbers come from the full run; --quick (CI, smoke) leaves the docs alone
        write_evaluation_doc(metrics)
    print(json.dumps(summary, indent=1, default=_default))
    return summary


def _snag_lines(sn: dict) -> list[str]:
    """Snag-coder results graded against what was repaired, not against the rule that labelled it."""
    va, km = sn.get("maintnet_vs_action"), sn.get("maintnet_keyword_masked")
    if not va:
        return [f"* Real MaintNet logbook problems (held-out): accuracy {sn['maintnet']['accuracy']:.1%} against weak labels."]
    out = [
        f"* Real MaintNet logbook problems ({va['n']} held-out entries whose repair action names a system): the model's chapter "
        f"matches **what was actually repaired {va['model_accuracy']:.0%}** of the time, vs {va['keyword_rule_accuracy']:.0%} for the "
        f"keyword rule on the problem text (which fires on {va['keyword_rule_coverage']:.0%} of entries) and {va['majority_class']:.0%} "
        "for always guessing the most common chapter. The model reads only the problem text; the label comes from the action.",
    ]
    if km:
        out.append(f"* With every rule keyword deleted from the problem text, accuracy is {km['accuracy']:.0%} against a "
                   f"{km['chance_majority']:.0%} majority-class baseline — on this real text the model is not learning much "
                   "beyond the keywords. Its practical value is coverage and robustness to spelling, abbreviations and "
                   "Hinglish; a unit deployment should add a few hundred expert-coded entries (active learning).")
    return out


def write_evaluation_doc(metrics: dict) -> None:
    lv = json.loads((BENCH_DIR / "levers.json").read_text())
    fc = json.loads((BENCH_DIR / "forecast.json").read_text())
    rq = json.loads((BENCH_DIR / "requirement_demo.json").read_text())
    rb = json.loads((BENCH_DIR / "rbs.json").read_text())
    e = metrics["engine_rul"]["test"]
    s = metrics["survival"]
    lines = [
        "# 04 · Evaluation (auto-generated by `python -m tatpar.pipelines.bench`)",
        "",
        "> All fleet numbers come from a **notional fleet** simulated by the Fleet Twin; they are not IAF results. "
        "Engine numbers use NASA's public C-MAPSS test sets.",
        "",
        "## 1. Engine remaining useful life (NASA C-MAPSS official test sets)",
        "",
        "| Subset | Engines | RMSE (cycles) | NASA score | 90 % interval coverage — raw | — conformal | Mean width |",
        "|---|---|---|---|---|---|---|",
    ]
    for fd in ("FD001", "FD002", "FD003", "FD004", "ALL"):
        r = e[fd]
        lines.append(f"| {fd} | {r['n']} | {r['rmse']:.2f} | {r['nasa_score']:.0f} | {r['picp90_uncalibrated']:.1%} | "
                     f"**{r['picp90']:.1%}** | {r['mpiw']:.1f} |")
    lines += [
        "",
        "Conformalised quantile regression lifts interval coverage to the nominal 90 % without retraining.",
        "",
        "## 2. LRU reliability models (recovering the hidden truth)",
        "",
        f"* {len(s['per_lru'])} Weibull AFT models, mean concordance {s['mean_c_index']:.3f}",
        f"* Weibull shape recovered with mean absolute error **{s['shape_mae']:.2f}**",
        f"* Mean life per (LRU, base) recovered with R² **{s['life_recovery']['r2_log']:.2f}** (log scale)",
        "",
        "## 3. Logistics-leak detectors",
        "",
        f"* No-Fault-Found predictor (tail-grouped CV): AUC **{metrics['nff']['auc']:.3f}**; at the operating point "
        f"it catches {metrics['nff']['tpr']:.0%} of NFF removals with {metrics['nff']['fpr']:.0%} false re-tests.",
        f"* Rogue-unit detector: precision **{metrics['rogue']['precision']:.0%}**, recall {metrics['rogue']['recall']:.0%} "
        f"of rogue serials with any removal ({metrics['rogue']['recall_3plus_removals']:.0%} of those with ≥3).",
        f"* Chronic-defect episodes found: {metrics['chronic_defects']}.",
        "",
        "## 3b. Snag intelligence (ATA auto-coding)",
        "",
    ]
    lines += _snag_lines(metrics["snag_nlp"])
    lines += [
        f"* Fleet snags (held-out tails): accuracy {metrics['snag_nlp']['fleet']['accuracy']:.1%} — easy by construction "
        "(templated synthetic text); Hinglish entries included.",
        "",
        "## 4. Readiness forecast calibration",
        "",
        f"Belief-mode forecasts (models only) vs outcomes drawn from the hidden truth: the P10–P90 band "
        f"contains **{fc['calibration']['coverage_p10_p90']:.0%}** of true daily outcomes (nominal 80 %), the P25–P75 band "
        f"{fc['calibration']['coverage_p25_p75']:.0%} (nominal 50 %).",
        "",
        f"## 5. Policy levers — one year, {lv['reps']} hidden-truth futures, common random numbers",
        "",
        "| Policy stack | Mission-capable | Δ vs previous (95 % CI) | Awaiting spares | Awaiting bay |",
        "|---|---|---|---|---|",
    ]
    for r in lv["rows"]:
        d = f"{r['delta']*100:+.1f} ± {r['delta_ci']*100:.1f}" if "delta" in r else "—"
        lines.append(f"| {r['label']} | {r['mc']*100:.1f} % | {d} | {r['state_share']['NMCS']*100:.1f} % | "
                     f"{r['state_share']['WAIT']*100:.1f} % |")
    lines += [
        "",
        f"**Total: {lv['total_delta']*100:+.1f} ± {lv['total_ci']*100:.1f} percentage points ≈ "
        f"{lv['aircraft_equivalent']:.0f} more mission-capable aircraft every day from the same 64-aircraft fleet.**",
        "",
        "Readiness-based sparing reallocates the *same* inventory budget "
        f"(₹{rb['prognostic']['budget_lakh']/100:.0f} crore): modelled supply availability "
        f"{rb['prognostic']['availability_current']:.0%} → {rb['prognostic']['availability_rbs']:.0%}. "
        "Fixing spares alone moves the bottleneck to the hangar (aircraft queue for a bay); the phase-flow plan removes it.",
    ]
    lines += sensitivity.doc_lines()
    lines += [
        "",
        "## 6. Readiness-backward planning (demo requirement)",
        "",
        f"Requirement: ≥{rq['min_mc']} mission-capable aircraft at {rq['squadron_name']} from D+{rq['window']['start']} to "
        f"D+{rq['window']['end']} with a {rq['surge']:.0%} flying task.",
        "",
        "| Action | P(meet requirement) | Gain |",
        "|---|---|---|",
    ]
    for st_ in rq["steps"]:
        lines.append(f"| {st_['label']} | {st_['p_meet']:.0%} | {st_['gain']*100:+.0f} pts |")
    fp = BENCH_DIR / "federated.json"
    if fp.exists():
        fd = json.loads(fp.read_text())
        bases = list(fd["clients"])
        lines += ["", "## 7. Federated learning across bases (engine RUL, NASA C-MAPSS)", "",
                  fd["description"], "",
                  "| Regime | " + " | ".join(bases) + " | Mean RMSE | Raw data leaves base? |",
                  "|---|" + "---|" * len(bases) + "---|---|"]
        for r in fd["results"]:
            lines.append(f"| {r['regime']} | " + " | ".join(f"{r['per_base'][b]:.1f}" for b in bases) +
                         f" | **{r['rmse']:.2f}** | {r['data_moved']} |")
    lines.append("")
    (REPO_DIR / "docs" / "04-evaluation.md").write_text("\n".join(lines))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    run(ap.parse_args().quick)
