"""Snag intelligence, data fabric and model cards."""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel

from ...domain.catalog import LRU_TYPES, SQUADRONS
from ...prognostics.leaks import nff_features
from ...twin.state import SP_IDS
from ..context import get_ctx

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


@router.get("/snags/recent")
def recent():
    ctx = get_ctx()
    s = ctx.tables["snags"].sort_values("day", ascending=False).head(60)
    return s[["snag_id", "date", "tail", "squadron", "ata", "system", "lru", "text", "finding", "action"]].astype({"date": str}).to_dict("records")


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
    ("supply", "Spares transactions (IMMOLS style)", "supply", "SupplyTransaction", "Material supply (S2000M)", "—"),
    ("repairs", "BRD / HAL repair orders", "repairs", "RepairOrder", "Repair / overhaul event", "—"),
    ("positions", "Installed configuration (serials, TSO)", "positions", "InstalledPosition, SerialisedItem", "Product breakdown, serialised item", "—"),
    ("status", "Daily aircraft status", "status", "StatusDay", "Availability data", "AG"),
]


def _quality(df: pd.DataFrame) -> dict:
    if df is None or len(df) == 0:
        return {"rows": 0, "completeness": 0.0}
    comp = float(1 - df.isna().mean().mean())
    return {"rows": int(len(df)), "completeness": round(comp, 4), "columns": len(df.columns)}


@router.get("/data/sources")
def sources():
    ctx = get_ctx()
    out = []
    for key, label, table, entity, s5000f, osacbm in SOURCES:
        df = ctx.tables.get(table)
        q = _quality(df)
        last = None
        if df is not None and "day" in df.columns and len(df):
            last = int(ctx.state.day - df["day"].max())
        consistency = 1.0
        if table == "snags" and len(df):
            consistency = float(df["removal_id"].notna().mean() + (df["finding"] == "RETEST").mean())
        out.append({"key": key, "label": label, "entity": entity, "s5000f": s5000f, "osa_cbm": osacbm,
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


REQUIRED = {
    "snags": ["date", "tail", "text"],
    "stock": ["stock_point", "lru", "qty"],
    "sorties": ["date", "tail", "hours"],
}


@router.post("/data/validate")
async def validate(kind: str, file: UploadFile = File(...)):
    """Validate an uploaded CSV export against the common data model (no data is stored)."""
    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "errors": [f"Could not parse CSV: {e}"]}
    cols = [c.strip().lower() for c in df.columns]
    df.columns = cols
    errors, warnings = [], []
    need = REQUIRED.get(kind, [])
    missing = [c for c in need if c not in cols]
    if missing:
        errors.append(f"Missing required columns: {', '.join(missing)}")
    ctx = get_ctx()
    if "tail" in cols:
        unknown = sorted(set(df["tail"].astype(str)) - set(ctx.state.tail_ids))
        if unknown:
            warnings.append(f"{len(unknown)} tail numbers not in fleet register (e.g. {', '.join(unknown[:3])})")
    if "lru" in cols:
        unknown = sorted(set(df["lru"].astype(str)) - set(LRU_TYPES))
        if unknown:
            warnings.append(f"{len(unknown)} part types not in catalogue (e.g. {', '.join(unknown[:3])}) — entity resolution needed")
    if "date" in cols:
        bad = pd.to_datetime(df["date"], errors="coerce").isna().sum()
        if bad:
            errors.append(f"{bad} rows with unparseable dates")
    out = {"ok": not errors, "rows": int(len(df)), "columns": cols, "errors": errors, "warnings": warnings,
           "completeness": round(float(1 - df.isna().mean().mean()), 4)}
    if kind == "snags" and "text" in cols and not errors:
        sample = df["text"].astype(str).head(20).tolist()
        out["ata_preview"] = [{"text": t, "ata": ctx.nlp.classify(t, 1)[0]} for t in sample]
    return out


@router.get("/models")
def models():
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
         "metrics": m.get("snag_nlp"), "intended_use": "Coding, search, fix recommendation", "limits": "MaintNet labels are keyword-derived."},
        {"id": "forecast", "name": "Readiness forecast (Fleet Twin Monte-Carlo)", "data": "All of the above",
         "metrics": fc.get("calibration"), "intended_use": "P(meet requirement), planning", "limits": "Notional fleet parameters."},
    ]
    return {"cards": cards, "federated": fl, "calibration_points": m["survival"]["life_recovery"]["points"]}
