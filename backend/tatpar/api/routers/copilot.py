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

from ...domain.catalog import BASES, SQUADRONS
from ...twin.simulator import day_to_date
from ...twin.state import SQN_IDS
from ..context import get_ctx
from .fleet import _tail_rows, aircraft

router = APIRouter(prefix="/api", tags=["copilot"])
TAIL_RE = re.compile(r"\b(HF|LF)[- ]?(\d{3})\b", re.I)


class Q(BaseModel):
    question: str


SQN_RE = re.compile(r"\bsq(?:n|uadron)?\.?[- ]?([a-z])\b", re.I)
# A request to the router is scored against each intent's keywords; specific words outweigh generic ones
# ("which tails will fail" is about failure risk, not the forecast, even though it contains "will").
INTENTS = {
    "compare":   (("compare", " vs ", "versus", "which squadron", "lowest", "highest", "worst", "best", "rank"), ()),
    "risk":      (("snag", "likely to fail", "fail", "break", "risk", "unreliable"), ()),
    "engines":   (("engine", "rul", "remaining life", "removal"), ()),
    "aog":       (("aog", "cannibal", "grounded", "awaiting", "robbing"), ()),
    "transfers": (("spare", "transfer", "move", "stock", "inventory", "shortage"), ()),
    "waterfall": (("why", "loss", "lost", "lever", "improve", "bottleneck", "cause"), ("low",)),
    "planner":   (("plan", "requirement", "surge", "must i do", "what should", "what do i need", "how do i get"), ("need",)),
    "forecast":  (("how many", "forecast", "available", "availability", "mission-capable", "mission capable",
                   "serviceab", "readiness", "ready"), ("will",)),
}
PRIORITY = list(INTENTS)        # tie-break order
# words that make a sentence read like a technical-log entry rather than a question about the fleet
FAULT_RE = re.compile(r"\b(leak\w*|pressure|fluctuat\w*|inop\w*|u/s|unserviceable|warning|caution|light|noise|vibrat\w*|"
                      r"crack\w*|intermittent\w*|indicat\w*|reading|smoke|smell|flicker\w*|stuck|jam\w*|chaf\w*|worn|"
                      r"bite|fault\w*|failed|failure|reset|tripped|overheat\w*|low|high|no output|mein|nahi|hai)\b", re.I)


def _sqns_from(q: str) -> tuple[list[int], list[str]]:
    """Squadrons named in the question (by letter or home base), and any letters that are not squadrons."""
    found, unknown = [], []
    for m in SQN_RE.finditer(q):
        letter = m.group(1).upper()
        sid = f"SQN-{letter}"
        if sid in SQN_IDS:
            found.append(SQN_IDS.index(sid))
        else:
            unknown.append(f"Sqn {letter}")
    ql = q.lower()
    for k, s in enumerate(SQUADRONS.values()):
        if s.base in ql:
            found.append(k)
    return sorted(set(found)), unknown


def _base_without_sqn(q: str) -> str | None:
    homes = {s.base for s in SQUADRONS.values()}
    ql = q.lower()
    for bid, b in BASES.items():
        if bid not in homes and re.search(rf"\b{bid}\b", ql):
            return b.name
    return None


def _days_from(q: str) -> int:
    ql = q.lower()
    for pat, mult in ((r"\bd\s*\+\s*(\d+)", 1), (r"\bday\s*(\d+)\b", 1), (r"\b(\d+)\s*days?\b", 1),
                      (r"\b(\d+)\s*weeks?\b", 7), (r"\b(\d+)\s*months?\b", 30)):
        m = re.search(pat, ql)
        if m:
            return mult * int(m.group(1))
    for word, d in (("tomorrow", 1), ("today", 0), ("now", 0), ("fortnight", 14), ("week", 7), ("month", 30)):
        if re.search(rf"\b{word}\b", ql):
            return d
    return 14


def _intent(q: str) -> str | None:
    ql = f" {q.lower()} "
    scores = {k: 2 * sum(w in ql for w in strong) + sum(w in ql for w in weak) for k, (strong, weak) in INTENTS.items()}
    best = max(scores.values())
    return None if best == 0 else min((k for k, v in scores.items() if v == best), key=PRIORITY.index)


def _tail_ranges(ctx) -> str:
    st = ctx.state
    out = []
    for k, sid in enumerate(SQN_IDS):
        tails = [t for i, t in enumerate(st.tail_ids) if st.tail_sqn[i] == k]
        out.append(f"{tails[0]}…{tails[-1]} ({sid})")
    return ", ".join(out)


def _horizon(ctx, d: int) -> tuple[int, str]:
    n = len(ctx.bench("forecast")["baseline"]["fleet"]["p50"])
    if d > n - 1:
        return n - 1, f"The forecast runs to D+{n - 1}, so this answer is for D+{n - 1}, not D+{d}. "
    return d, ""


HELP = ("I answer from TATPAR's own records and models: readiness forecasts (\"how many aircraft will Sqn A have in "
        "2 weeks\"), comparing squadrons (\"which squadron has the lowest readiness\"), a tail's status (\"HF-114\"), "
        "snag risk, engines near removal, spares to move, aircraft awaiting parts, why readiness is lost, the "
        "readiness planner, or a tech-log entry to code (\"HYD PRESSURE LOW ON TAXI\").")


def route(q: str) -> dict:
    ctx = get_ctx()
    st = ctx.state
    m = TAIL_RE.search(q)
    if m:
        tail = f"{m.group(1).upper()}-{m.group(2)}"
        if tail not in st.tail_ids:
            return {"answer": f"{tail} is not in the fleet register. Tails are {_tail_ranges(ctx)}.",
                    "links": [{"label": "Fleet register", "to": "/aircraft"}], "tool": "unknown_tail"}
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

    sqns, unknown = _sqns_from(q)
    if unknown:
        return {"answer": f"There is no {unknown[0]} in this fleet. Squadrons: "
                          + "; ".join(s.name for s in SQUADRONS.values()) + ".", "tool": "unknown_squadron"}
    base = _base_without_sqn(q)
    if base and not sqns:
        return {"answer": f"No squadron is based at {base} in this notional fleet, so there is no readiness to report there. "
                          f"{base} appears only as a data-poor detachment in the federated-learning study (08 PROOF). "
                          f"Squadrons: " + "; ".join(s.name for s in SQUADRONS.values()) + ".",
                "links": [{"label": "Proof", "to": "/proof"}], "tool": "unknown_base"}

    intent = _intent(q)
    if intent == "forecast" and len(sqns) > 1:
        intent = "compare"
    if intent == "compare":
        fc = ctx.bench("forecast")
        d, note = _horizon(ctx, _days_from(q))
        status = st.status()
        rows = []
        for k, sid in enumerate(SQN_IDS):
            if sqns and len(sqns) > 1 and k not in sqns:
                continue
            b, tt = fc["baseline"]["squadrons"][sid], fc["tatpar"]["squadrons"][sid]
            n = int((st.tail_sqn == k).sum())
            mc_now = int(((st.tail_sqn == k) & (status == 0)).sum())
            rows.append({"Sqn": SQUADRONS[sid].name, "MC today": f"{mc_now}/{n}",
                         f"D+{d} current practice": f"{b['p50'][d]:.0f} ({b['p10'][d]:.0f}–{b['p90'][d]:.0f})",
                         f"D+{d} with TATPAR": f"{tt['p50'][d]:.0f} ({tt['p10'][d]:.0f}–{tt['p90'][d]:.0f})",
                         "_key": b["p50"][d] / n})
        low = min(rows, key=lambda r: r["_key"])
        for r in rows:
            r.pop("_key")
        return {"answer": f"{note}Mission-capable aircraft by squadron, today and forecast for D+{d} "
                          f"({day_to_date(st.day + d)}); median and 80 % range. Lowest under current practice: {low['Sqn']}.",
                "table": rows, "links": [{"label": "Readiness planner", "to": "/planner"}], "tool": "compare"}
    if intent == "forecast":
        fc = ctx.bench("forecast")
        d, note = _horizon(ctx, _days_from(q))
        if not sqns:
            b, tt = fc["baseline"]["fleet"], fc["tatpar"]["fleet"]
            who, n = "the fleet", st.n_tails
        else:
            k = sqns[0]
            b, tt = fc["baseline"]["squadrons"][SQN_IDS[k]], fc["tatpar"]["squadrons"][SQN_IDS[k]]
            who, n = SQUADRONS[SQN_IDS[k]].name, SQUADRONS[SQN_IDS[k]].n_aircraft
        date = day_to_date(st.day + d)
        return {"answer": f"{note}On D+{d} ({date}) {who} is forecast to have {b['p50'][d]:.0f} of {n} aircraft mission-capable "
                          f"(80 % range {b['p10'][d]:.0f}–{b['p90'][d]:.0f}) under current practice, or {tt['p50'][d]:.0f} "
                          f"({tt['p10'][d]:.0f}–{tt['p90'][d]:.0f}) with TATPAR's recommendations. "
                          f"The 80 % band has contained {fc['calibration']['coverage_p10_p90']:.0%} of hidden-truth outcomes in simulated back-tests (notional fleet).",
                "links": [{"label": "Readiness planner", "to": "/planner"}, {"label": "Overview", "to": "/"}], "tool": "forecast"}
    if intent == "risk":
        rows = [r for r in _tail_rows(ctx) if not sqns or SQN_IDS.index(r["squadron"]) in sqns]
        rows = sorted(rows, key=lambda r: -r["p_snag_7d"])[:5]
        return {"answer": "Aircraft most likely to raise a snag in the next 7 days (survival models with base environment and mission severity):",
                "table": [{"Tail": r["tail"], "Sqn": r["squadron"], "P(snag 7d)": f"{r['p_snag_7d']:.0%}", "Status": r["state"]} for r in rows],
                "links": [{"label": "Aircraft health", "to": "/aircraft"}], "tool": "risk"}
    if intent == "engines":
        rows = [r for r in _tail_rows(ctx) if r["engine_rul_fh_min"] is not None
                and (not sqns or SQN_IDS.index(r["squadron"]) in sqns)]
        rows = sorted(rows, key=lambda r: r["engine_rul_fh_min"])[:5]
        return {"answer": "Engines with the lowest calibrated remaining life (median, flight hours) from HUMS:",
                "table": [{"Tail": r["tail"], "Engine RUL (FH)": int(r["engine_rul_fh_min"]), "To phase (FH)": int(r["to_phase"])} for r in rows],
                "links": [{"label": "Fleet flow & engine protection", "to": "/flow"}], "tool": "engines"}
    if intent == "transfers":
        adv = ctx.bench("advisors")
        rows = adv["transfers"][:6]
        return {"answer": f"{len(adv['transfers'])} predictive transfers recommended for the next 14 days. Top moves:",
                "table": [{"Part": r["name"], "From": r["from"], "To": r["to"], "Qty": r["qty"]} for r in rows],
                "links": [{"label": "Sustainment", "to": "/sustainment"}], "tool": "transfers"}
    if intent == "aog":
        from ...optimize.advisors import cannibalisation_advice

        rows = cannibalisation_advice(st)[:6]
        return {"answer": f"{len(st.backorders)} aircraft positions are awaiting parts. Recommendations:",
                "table": [{"Tail": r["tail"], "Part": r["name"], "Down": f"{r['down_days']} d", "Action": r["recommendation"]} for r in rows],
                "links": [{"label": "Sustainment", "to": "/sustainment"}], "tool": "aog"}
    if intent == "waterfall":
        wf = ctx.bench("waterfall")["history"]
        lv = ctx.bench("levers")
        losses = sorted([r for r in wf["rows"] if r["value"] < 0], key=lambda r: r["value"])
        txt = (f"Over the last 12 months the fleet was mission-capable {wf['mc_rate']:.0%} of possessed aircraft-days. "
               f"Biggest losses: " + ", ".join(f"{r['label'].lower()} {-r['value']:,} aircraft-days" for r in losses[:3]) + ". "
               f"In the twin, readiness-based sparing (same budget) adds {lv['rows'][1]['delta']*100:+.1f} pts and the phase-flow "
               f"flying plan another {lv['rows'][2]['delta']*100:+.1f} pts; the full policy {lv['total_delta']*100:+.1f} ± {lv['total_ci']*100:.1f} pts.")
        if sqns:
            txt += " (The loss breakdown is fleet-wide; per-squadron losses are on 06 AFTER-ACTION.)"
        return {"answer": txt, "links": [{"label": "Readiness loss", "to": "/loss"}], "tool": "waterfall"}
    if intent == "planner":
        r = ctx.bench("requirement_demo")
        s0, s1 = r["steps"][0], r["steps"][-1]
        return {"answer": f"Example: for ≥{r['min_mc']} mission-capable at {r['squadron_name']} from D+{r['window']['start']} to "
                          f"D+{r['window']['end']} with a {r['surge']:.0%} task, P(meet) rises from {s0['p_meet']:.0%} to {s1['p_meet']:.0%} "
                          f"with the recommended actions. Set your own requirement"
                          + (f" for {SQN_IDS[sqns[0]]}" if sqns else "") + " in the planner (it tests each action on 80 futures, about 20 s).",
                "links": [{"label": "Readiness planner", "to": "/planner"}], "tool": "planner"}
    # no fleet question recognised: code it as a tech-log entry only if it reads like one
    if len(q.split()) >= 3 and FAULT_RE.search(q) and not q.strip().endswith("?"):
        res = ctx.nlp.classify(q, 1)[0]
        sim = ctx.nlp.similar(q, 3)
        txt = f"That reads like a snag: ATA {res['ata']} {res['name']} ({res['p']:.0%}). Similar past cases:\n" + \
              "\n".join(f"• {s['problem']} → {s['action']}" for s in sim)
        return {"answer": txt, "links": [{"label": "Snag intelligence", "to": "/snags"}], "tool": "snag"}
    lead = "That is outside what I can answer from this platform's data. " if len(q.split()) >= 3 else ""
    return {"answer": lead + HELP, "tool": "help"}


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
