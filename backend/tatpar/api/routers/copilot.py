"""'Ask TATPAR' — an offline copilot that answers only from the platform's own tools.

A deterministic intent router calls the same functions the UI uses and cites the records. If a
local LLM is configured (``TATPAR_LLM_URL`` pointing at an Ollama-compatible ``/api/chat`` and
``TATPAR_LLM_MODEL``), the tool output is passed to it purely for phrasing; on any failure the
template answer is returned. Nothing leaves the machine.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request

from fastapi import APIRouter
from pydantic import BaseModel

from ...domain.catalog import SQUADRONS
from ...twin.simulator import day_to_date
from ...twin.state import SQN_IDS
from ..context import get_ctx
from .fleet import _tail_rows, aircraft

router = APIRouter(prefix="/api", tags=["copilot"])
TAIL_RE = re.compile(r"\b(HF|LF)[- ]?(\d{3})\b", re.I)


class Q(BaseModel):
    question: str


def _sqn_from(q: str) -> int | None:
    m = re.search(r"\bsq(?:n|uadron)?[- ]?([abcd])\b", q, re.I)
    if m:
        return "ABCD".index(m.group(1).upper())
    for k, s in enumerate(SQUADRONS.values()):
        if s.base in q.lower():
            return k
    return None


def _days_from(q: str) -> int:
    m = re.search(r"d\+?\s?(\d+)", q, re.I) or re.search(r"(\d+)\s*day", q, re.I)
    if m:
        return min(59, int(m.group(1)))
    m = re.search(r"(\d+)\s*week", q, re.I)
    if m:
        return min(59, 7 * int(m.group(1)))
    if "week" in q.lower():
        return 7
    if "month" in q.lower():
        return 30
    return 14


def route(q: str) -> dict:
    ctx = get_ctx()
    ql = q.lower()
    m = TAIL_RE.search(q)
    if m:
        tail = f"{m.group(1).upper()}-{m.group(2)}"
        if tail in ctx.state.tail_ids:
            a = aircraft(tail)
            top = sorted(a["lrus"], key=lambda l: -l["p_fail_30d"])[:3]
            eng = "; ".join(f"engine {i+1} RUL {e['rul_fh']['med']:.0f} FH (90 %: {e['rul_fh']['lo']:.0f}–{e['rul_fh']['hi']:.0f})"
                            for i, e in enumerate(a["engines"]))
            txt = (f"{tail} ({a['squadron']}, {a['base'].title()}) is {a['state']}. {a['to_phase']:.0f} FH to phase check, "
                   f"{a['to_overhaul']:.0f} FH to depot overhaul. P(snag in 7 days) {a['p_snag_7d']:.0%}. {eng}.\n"
                   f"Highest 30-day risks: " + ", ".join(f"{l['name']} {l['p_fail_30d']:.0%}" for l in top) + ".")
            if a["chronic"]:
                txt += f"\nChronic defect flagged in ATA {', '.join(str(c['ata']) for c in a['chronic'])}."
            return {"answer": txt, "links": [{"label": f"Open {tail}", "to": f"/aircraft/{tail}"}], "tool": "aircraft"}
    if any(w in ql for w in ("how many", "forecast", "will", "available", "ready")) and "why" not in ql:
        fc = ctx.bench("forecast")
        d = _days_from(q)
        k = _sqn_from(q)
        if k is None:
            b, tt = fc["baseline"]["fleet"], fc["tatpar"]["fleet"]
            who, n = "the fleet", ctx.state.n_tails
        else:
            b, tt = fc["baseline"]["squadrons"][SQN_IDS[k]], fc["tatpar"]["squadrons"][SQN_IDS[k]]
            who, n = SQUADRONS[SQN_IDS[k]].name, SQUADRONS[SQN_IDS[k]].n_aircraft
        date = day_to_date(ctx.state.day + d)
        return {"answer": f"On D+{d} ({date}) {who} is forecast to have {b['p50'][d]:.0f} of {n} aircraft mission-capable "
                          f"(80 % range {b['p10'][d]:.0f}–{b['p90'][d]:.0f}) under current practice, or {tt['p50'][d]:.0f} "
                          f"({tt['p10'][d]:.0f}–{tt['p90'][d]:.0f}) with TATPAR's recommendations. "
                          f"The 80 % band has contained {fc['calibration']['coverage_p10_p90']:.0%} of hidden-truth outcomes in simulated back-tests (notional fleet).",
                "links": [{"label": "Readiness planner", "to": "/planner"}, {"label": "Overview", "to": "/"}], "tool": "forecast"}
    if any(w in ql for w in ("snag", "risk", "likely to fail", "fail")):
        rows = sorted(_tail_rows(ctx), key=lambda r: -r["p_snag_7d"])[:5]
        return {"answer": "Aircraft most likely to raise a snag in the next 7 days (survival models with base environment and mission severity):",
                "table": [{"Tail": r["tail"], "Sqn": r["squadron"], "P(snag 7d)": f"{r['p_snag_7d']:.0%}", "Status": r["state"]} for r in rows],
                "links": [{"label": "Aircraft health", "to": "/aircraft"}], "tool": "risk"}
    if "engine" in ql:
        rows = sorted([r for r in _tail_rows(ctx) if r["engine_rul_fh_min"] is not None], key=lambda r: r["engine_rul_fh_min"])[:5]
        return {"answer": "Engines with the lowest calibrated remaining life (median, flight hours) from HUMS:",
                "table": [{"Tail": r["tail"], "Engine RUL (FH)": int(r["engine_rul_fh_min"]), "To phase (FH)": int(r["to_phase"])} for r in rows],
                "links": [{"label": "Fleet flow & engine protection", "to": "/flow"}], "tool": "engines"}
    if any(w in ql for w in ("spare", "move", "transfer", "stock")):
        adv = ctx.bench("advisors")
        rows = adv["transfers"][:6]
        return {"answer": f"{len(adv['transfers'])} predictive transfers recommended for the next 14 days. Top moves:",
                "table": [{"Part": r["name"], "From": r["from"], "To": r["to"], "Qty": r["qty"]} for r in rows],
                "links": [{"label": "Sustainment", "to": "/sustainment"}], "tool": "transfers"}
    if any(w in ql for w in ("aog", "cannibal", "grounded", "awaiting")):
        from ...optimize.advisors import cannibalisation_advice

        rows = cannibalisation_advice(ctx.state)[:6]
        return {"answer": f"{len(ctx.state.backorders)} aircraft positions are awaiting parts. Recommendations:",
                "table": [{"Tail": r["tail"], "Part": r["name"], "Down": f"{r['down_days']} d", "Action": r["recommendation"]} for r in rows],
                "links": [{"label": "Sustainment", "to": "/sustainment"}], "tool": "aog"}
    if any(w in ql for w in ("why", "loss", "low", "lever", "improve")):
        wf = ctx.bench("waterfall")["history"]
        lv = ctx.bench("levers")
        losses = sorted([r for r in wf["rows"] if r["value"] < 0], key=lambda r: r["value"])
        txt = (f"Over the last 12 months the fleet was mission-capable {wf['mc_rate']:.0%} of possessed aircraft-days. "
               f"Biggest losses: " + ", ".join(f"{r['label'].lower()} {-r['value']:,} aircraft-days" for r in losses[:3]) + ". "
               f"In the twin, readiness-based sparing (same budget) adds {lv['rows'][1]['delta']*100:+.1f} pts and the phase-flow "
               f"flying plan another {lv['rows'][2]['delta']*100:+.1f} pts; the full policy {lv['total_delta']*100:+.1f} ± {lv['total_ci']*100:.1f} pts.")
        return {"answer": txt, "links": [{"label": "Readiness loss", "to": "/loss"}], "tool": "waterfall"}
    if any(w in ql for w in ("plan", "requirement", "surge", "need")):
        r = ctx.bench("requirement_demo")
        s0, s1 = r["steps"][0], r["steps"][-1]
        return {"answer": f"Example: for ≥{r['min_mc']} mission-capable at {r['squadron_name']} from D+{r['window']['start']} to "
                          f"D+{r['window']['end']} with a {r['surge']:.0%} task, P(meet) rises from {s0['p_meet']:.0%} to {s1['p_meet']:.0%} "
                          f"with the recommended actions. Set your own requirement in the planner.",
                "links": [{"label": "Readiness planner", "to": "/planner"}], "tool": "planner"}
    if len(q.split()) >= 4:
        res = ctx.nlp.classify(q, 1)[0]
        sim = ctx.nlp.similar(q, 3)
        txt = f"That reads like a snag: ATA {res['ata']} {res['name']} ({res['p']:.0%}). Similar past cases:\n" + \
              "\n".join(f"• {s['problem']} → {s['action']}" for s in sim)
        return {"answer": txt, "links": [{"label": "Snag intelligence", "to": "/snags"}], "tool": "snag"}
    return {"answer": "I can answer: readiness forecasts (\"how many aircraft will Sqn A have in 2 weeks\"), a tail's status (\"HF-114\"), "
                      "snag risk, engines near removal, spares to move, aircraft awaiting parts, why readiness is low, or analyse a snag text.",
            "tool": "help"}


def _llm(question: str, tool: dict) -> str | None:
    url, model = os.environ.get("TATPAR_LLM_URL"), os.environ.get("TATPAR_LLM_MODEL")
    if not url or not model:
        return None
    body = {"model": model, "stream": False, "messages": [
        {"role": "system", "content": "You are TATPAR, an air-fleet readiness assistant. Answer ONLY from the tool result. "
                                      "Be brief, keep every number exactly as given, say when data is notional."},
        {"role": "user", "content": f"Question: {question}\nTool result (JSON): {json.dumps(tool, default=str)[:6000]}"}]}
    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["message"]["content"]
    except Exception:  # noqa: BLE001 — offline / no model: fall back to the template answer
        return None


@router.post("/copilot")
def copilot(q: Q):
    res = route(q.question)
    phrased = _llm(q.question, res)
    res["engine"] = (f"Local LLM ({os.environ.get('TATPAR_LLM_MODEL')}) over TATPAR tools" if phrased
                     else "Deterministic tool router · offline")
    if phrased:
        res["answer"] = phrased
    return res
