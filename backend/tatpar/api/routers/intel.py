"""Snag intelligence, data fabric and model cards."""
from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from ...domain.catalog import LRU_TYPES
from ...prognostics.leaks import nff_features
from ...trust import records
from ...trust.auth import User
from ...twin.state import SP_IDS
from ..context import get_ctx
from ..security import current_user, require

router = APIRouter(prefix="/api", tags=["intel"])


class SnagReq(BaseModel):
    text: str
    tail: str | None = None
    lru: str | None = None


@router.post("/snags/analyse")
def analyse(req: SnagReq):
    ctx = get_ctx()
    ata = ctx.nlp.classify(req.text, 3)
    similar = ctx.nlp.similar(req.text, 8)
    fix = ctx.nlp.fix_effectiveness(ata[0]["ata"])
    nff = None
    lru = req.lru
    if lru is None:
        cands = [l for l in LRU_TYPES.values() if l.ata == ata[0]["ata"]]
        lru = cands[0].id if len(cands) == 1 else None
    if lru and req.tail and req.tail in ctx.state.tail_ids:
        t = ctx.state.tail_ids.index(req.tail)
        base = SP_IDS[ctx.state.tail_sp[t]]
        row = pd.DataFrame([{"lru": lru, "text": req.text.upper(), "base": base, "date": pd.Timestamp(ctx.today),
                             "day": ctx.state.day, "tail": req.tail}])
        prior = ctx.tables["snags"][["lru", "text", "base", "date", "day", "tail"]]
        df = pd.concat([prior, row], ignore_index=True)
        p = float(ctx.nff.model.predict_proba(nff_features(df).tail(1))[:, 1][0])
        nff = {"lru": lru, "p_nff": p, "threshold": ctx.nff.threshold,
               "recommendation": ("Ground re-test before removal (likely No-Fault-Found)" if p >= ctx.nff.threshold
                                  else "Proceed with troubleshooting / replacement")}
    return {"ata": ata, "similar": similar, "fix_effectiveness": fix, "nff": nff}


COLS = ["snag_id", "date", "tail", "squadron", "ata", "system", "lru", "text", "finding", "action"]


def filed_for(tail: str | None = None) -> list[dict]:
    """Entries filed from the ops room or imported, newest first (with who filed them)."""
    fs = [f for f in reversed(records.filed_snags()) if tail is None or f["tail"] == tail]
    return [{**{k: f.get(k) for k in COLS}, "filed_by": f.get("filed_by"), "source": f.get("source", "FILED")} for f in fs]


def _file(ctx, tail: str, text: str, lru: str | None, date: str, by: str, source: str) -> dict:
    from ...ingest.apply import file_snag_entry

    return file_snag_entry(ctx, tail, text, lru, date, by, source)


@router.get("/snags/recent")
def recent():
    ctx = get_ctx()
    s = ctx.tables["snags"].sort_values("day", ascending=False).head(60)
    return filed_for() + s[COLS].astype({"date": str}).to_dict("records")


class FileReq(BaseModel):
    text: str
    tail: str
    lru: str | None = None


@router.post("/snags/file")
def file_snag(req: FileReq, user: User = Depends(require("snags:file"))):
    """Analyse and record a new technical-log entry (it then appears in the tech log and the aircraft record)."""
    ctx = get_ctx()
    if req.tail not in ctx.state.tail_ids or not req.text.strip():
        raise HTTPException(422, "unknown tail or empty defect text")
    res = analyse(SnagReq(text=req.text, tail=req.tail, lru=req.lru))
    return {**res, "entry": _file(ctx, req.tail, req.text, req.lru, ctx.today, user.role, "FILED")}


@router.get("/snags/stats")
def snag_stats():
    ctx = get_ctx()
    s = ctx.tables["snags"]
    by_ata = s.groupby(["ata", "system"]).agg(snags=("snag_id", "size"), nff=("finding", lambda f: int((f == "NFF").sum()))).reset_index()
    return {"by_ata": by_ata.sort_values("snags", ascending=False).to_dict("records"),
            "chronic": ctx.tables["chronic_defects"].to_dict("records"), "nlp_metrics": ctx.metrics.get("snag_nlp")}


SOURCES = [
    ("hums", "HUMS / ACMS engine health", "engines", "EngineHealthSnapshot", "Health monitoring data", "DA → DM"),
    ("sorties", "Flying records (sorties, hours, mission g)", "sorties", "Sortie", "Operation / usage", "DA"),
    ("snags", "Technical log snags (e-MMS / Form-700 style)", "snags", "Snag", "Failure / malfunction report", "SD"),
    ("removals", "Removals & shop findings", "removals", "Removal, ShopFinding", "Maintenance task, shop findings", "HA"),
    ("checks", "Scheduled checks", "checks", "MaintenanceEvent", "Maintenance task performed", "HA"),
    ("supply", "Spares stock & transactions (IMMOLS style)", "supply", "SupplyTransaction, StockLevel", "Material supply (S2000M)", "—"),
    ("repairs", "BRD / HAL repair orders", "repairs", "RepairOrder", "Repair / overhaul event", "—"),
    ("positions", "Installed configuration (serials, TSO)", "positions", "InstalledPosition, SerialisedItem", "Product breakdown, serialised item", "—"),
    ("status", "Daily aircraft status", "status", "StatusDay", "Availability data", "AG"),
]


# common-data-model source -> data contract a unit can import it through (tatpar.ingest.contracts)
INGEST_SOURCE = {"hums": "hums", "snags": "snags", "supply": "stock", "repairs": "repairs", "sorties": "sorties"}


def _quality(df: pd.DataFrame) -> dict:
    if df is None or len(df) == 0:
        return {"rows": 0, "completeness": 0.0}
    comp = float(1 - df.isna().mean().mean())
    return {"rows": int(len(df)), "completeness": round(comp, 4), "columns": len(df.columns)}


@router.get("/data/sources")
def sources():
    from ...ingest import store

    ctx = get_ctx()
    out = []
    last_import = {e["source"]: e for e in store.lineage()}
    for key, label, table, entity, s5000f, osacbm in SOURCES:
        df = ctx.tables.get(table)
        q = _quality(df)
        last = None
        if df is not None and "day" in df.columns and len(df):
            last = int(ctx.state.day - df["day"].max())
        consistency = 1.0
        if table == "snags" and len(df):
            consistency = float(df["removal_id"].notna().mean() + (df["finding"] == "RETEST").mean())
        imp = last_import.get(INGEST_SOURCE.get(key, ""))
        if imp:
            last = 0             # a unit export arrived since the last build
        out.append({"key": key, "label": label, "entity": entity, "s5000f": s5000f, "osa_cbm": osacbm,
                    "ingest": INGEST_SOURCE.get(key), "last_import": imp,
                    **q, "freshness_days": last, "consistency": round(min(1.0, consistency), 4),
                    "score": round(0.5 * q.get("completeness", 0) + 0.3 * consistency + 0.2 * (1.0 if (last or 0) <= 2 else 0.5), 3)})
    lineage = {
        "nodes": ["HUMS", "Tech log", "Flying records", "Spares ERP", "Repair agencies", "Common data model",
                  "Engine RUL", "LRU survival", "NFF / rogue", "Snag NLP", "Fleet Twin", "FMP", "RBS", "Planner",
                  "Command centre"],
        "edges": [["HUMS", "Common data model"], ["Tech log", "Common data model"], ["Flying records", "Common data model"],
                  ["Spares ERP", "Common data model"], ["Repair agencies", "Common data model"],
                  ["Common data model", "Engine RUL"], ["Common data model", "LRU survival"],
                  ["Common data model", "NFF / rogue"], ["Common data model", "Snag NLP"],
                  ["Engine RUL", "Fleet Twin"], ["LRU survival", "Fleet Twin"], ["NFF / rogue", "Fleet Twin"],
                  ["Fleet Twin", "FMP"], ["Fleet Twin", "RBS"], ["Fleet Twin", "Planner"], ["FMP", "Planner"],
                  ["RBS", "Planner"], ["Planner", "Command centre"], ["Snag NLP", "Command centre"]],
    }
    return {"sources": out, "lineage": lineage, "today": ctx.today}


@router.post("/data/validate")
async def validate(kind: str, file: UploadFile = File(...), user: User = Depends(current_user)):
    """Validate an uploaded CSV export against its data contract (no data is stored). Kept for older clients;
    see /api/ingest/{source}/validate."""
    from ...ingest.apply import ingest
    from ...ingest.contracts import CONTRACTS

    if kind not in CONTRACTS:
        raise HTTPException(422, f"unknown kind {kind!r}")
    rep = ingest(get_ctx(), kind, await file.read(), file.filename or "upload.csv", user, dry_run=True)["report"]
    return _legacy(rep)


def _legacy(rep: dict) -> dict:
    """Older response shape: rejected rows reported as warnings."""
    warn = list(rep.get("warnings", []))
    if rep.get("rejected"):
        first = rep["row_errors"][0] if rep.get("row_errors") else None
        warn.insert(0, f"{rep['rejected']} rows rejected" + (f" (line {first['line']}: {first['reasons'][0]})" if first else ""))
    return {**rep, "warnings": warn}


@router.post("/snags/import")
async def import_snags(file: UploadFile = File(...), user: User = Depends(require("data:import"))):
    """Validate an e-MMS / Form-700 style CSV export and file every valid row into the tech log.
    Kept for older clients; see POST /api/ingest/snags."""
    from ...ingest.apply import ingest

    out = ingest(get_ctx(), "snags", await file.read(), file.filename or "upload.csv", user)
    res = out.get("result") or {}
    return {**_legacy(out["report"]), "filed": res.get("filed", 0), "first": res.get("first"), "last": res.get("last"),
            "repeats": res.get("repeats", [])}


def _finite(x):
    """NaN / inf -> None so the model cards are valid JSON."""
    if isinstance(x, dict):
        return {k: _finite(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_finite(v) for v in x]
    if isinstance(x, float) and not np.isfinite(x):
        return None
    return x


@router.get("/models")
def models():
    return _finite(_models())


def _models():
    ctx = get_ctx()
    m = ctx.metrics
    fc = ctx.bench("forecast") or {}
    fl = ctx.bench("federated")
    cards = [
        {"id": "engine_rul", "name": "Engine RUL (LightGBM quantile + conformal)", "data": "NASA C-MAPSS FD001–FD004 (public)",
         "metrics": m["engine_rul"]["test"], "intended_use": "Engine removal planning; flying caps in FMP",
         "limits": "Trained on simulated turbofan data; real engines need fine-tuning on unit HUMS."},
        {"id": "survival", "name": "LRU reliability (Weibull AFT per type)", "data": "Fleet removal records (notional)",
         "metrics": {k: v for k, v in m["survival"].items() if k != "life_recovery"} | {"life_r2_log": m["survival"]["life_recovery"]["r2_log"]},
         "intended_use": "Failure probabilities for forecasting, sparing and bundling",
         "limits": "Only four bases: environment effects partly confounded."},
        {"id": "nff", "name": "No-Fault-Found predictor (LightGBM)", "data": "Snag text + context (notional)",
         "metrics": m["nff"], "intended_use": "Recommend ground re-test before removal", "limits": "Decision support only."},
        {"id": "rogue", "name": "Rogue-unit detector (PIT/Fisher + life ratio)", "data": "Serial removal histories",
         "metrics": m["rogue"], "intended_use": "Quarantine and deep-strip candidates", "limits": "Needs ≥2–3 removals."},
        {"id": "snag_nlp", "name": "ATA auto-coder & case retrieval", "data": "Fleet snags + MaintNet logbook (public)",
         "metrics": {k: v for k, v in (m.get("snag_nlp") or {}).items() if k in ("maintnet_vs_action", "maintnet_keyword_masked", "fleet", "fleet_hinglish")},
         "intended_use": "Coding, search, fix recommendation",
         "limits": "On real logbook text it agrees with what was repaired about 3 times in 4 — a little better than keyword rules, "
                   "and no better than guessing once its keywords are removed. Needs a few hundred expert-coded unit entries."},
        {"id": "forecast", "name": "Readiness forecast (Fleet Twin Monte-Carlo)", "data": "All of the above",
         "metrics": fc.get("calibration"), "intended_use": "P(meet requirement), planning", "limits": "Notional fleet parameters."},
    ]
    return {"cards": cards, "federated": fl, "calibration_points": m["survival"]["life_recovery"]["points"]}
