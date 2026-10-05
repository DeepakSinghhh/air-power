"""What an accepted import changes in the live picture.

* hums    — the engine's uploaded history is re-predicted (calibrated interval + module attribution) and
            the new interval replaces the stored belief, which every alert, risk figure, Monte-Carlo
            forecast, engine-protection cap and planner step reads through ``Belief.engine_quantiles``.
* snags   — filed in the aircraft's technical log, ATA-coded, checked for repeat defects.
* stock   — serviceable stock at the stock point is set to the reported quantity.
* repairs — the unit's return date at BRD / HAL is updated, or it is condemned (BER).

Imports change the models' *beliefs* and the logistics state; the twin's hidden ground truth is
untouched (data changes what we know, not what will happen). Bench runs never read imports.
"""
from __future__ import annotations

import hashlib
import threading

import numpy as np
import pandas as pd

from ..config import FH_PER_CYCLE
from ..data import cmapss
from ..domain.catalog import LRU_TYPES
from ..trust import audit, records
from ..twin.montecarlo import _apply_stock
from ..twin.simulator import START, day_to_date
from ..twin.state import ENGINE_IDX, LRU_IDS, SP_IDX, SQN_IDS
from . import store
from .contracts import CONTRACTS, Register, read_csv, validate

ALERT_FH = 25.0             # engine lower bound below this raises an alert
_lock = threading.Lock()


def date_to_day(d) -> int:
    return (pd.Timestamp(d).date() - START).days


def engine_positions(st, t: int) -> list[int]:
    return [int(p) for p in st.positions_of(t) if st.pos_type[p] == ENGINE_IDX]


def engine_serial(st, tail: str, engine: int) -> int:
    pos = engine_positions(st, st.tail_ids.index(tail))
    return int(st.pos_serial[pos[engine - 1]]) if engine <= len(pos) else -1


# ------------------------------------------------------------------ HUMS
def hums_frame(hist: pd.DataFrame, serial: int) -> pd.DataFrame:
    """An engine's uploaded history in the layout the RUL model reads."""
    f = hist.sort_values("cycle").copy()
    f["uid"] = f"HUMS-{serial}"
    for s in cmapss.SENSORS:
        if s not in f:
            f[s] = np.nan
    f["subset"] = "FD001"
    return f


def _multi_regime(rul, f: pd.DataFrame) -> pd.DataFrame:
    f = f.copy()
    if len(set(rul._regime(f))) > 1:
        f["subset"] = "FD004"       # the model's "several operating regimes" flag
    return f


def engine_interval(rul, hist: pd.DataFrame, serial: int) -> dict:
    f = _multi_regime(rul, hums_frame(hist, serial))
    p = rul.predict_last(f).iloc[-1]
    mods = rul.explain(f)
    top = sorted(mods.items(), key=lambda kv: kv[1])[:3]
    return {"lo": float(p["rul_lo"]), "med": float(p["rul_med"]), "hi": float(p["rul_hi"]),
            "last_cycle": int(f["cycle"].max()), "cycles": int(len(f)), "modules": {k: round(v, 2) for k, v in top}}


def _fh(q) -> dict:
    lo, med, hi = q
    return {"lo": round(lo * FH_PER_CYCLE, 1), "med": round(med * FH_PER_CYCLE, 1), "hi": round(hi * FH_PER_CYCLE, 1)}


def apply_hums(ctx, acc: pd.DataFrame, file: str, replace: bool = False) -> dict:
    st, out, skipped = ctx.state, [], []
    overrides = store.hums_overrides()
    cols = [f.name for f in CONTRACTS["hums"].fields if f.name not in ("tail", "engine")]
    for (tail, eng), g in acc.groupby(["tail", "engine"]):
        eng = int(eng)
        if len(g) < 5:
            skipped.append(f"{tail} engine {eng}: fewer than 5 cycles")
            continue
        ser = engine_serial(st, tail, eng)
        if ser < 0:
            skipped.append(f"{tail} engine {eng}: no engine fitted in that position")
            continue
        new = g[[c for c in cols if c in g]].copy()
        new["date"] = new["date"].astype(str) if "date" in new else ""
        hist = None if replace else store.hums_history(ser)
        merged = (pd.concat([hist, new]) if hist is not None else new)
        merged = merged.drop_duplicates("cycle", keep="last").sort_values("cycle")
        store.save_hums_history(ser, merged)
        before = ctx.belief.engine_quantiles(st, ser)
        iv = engine_interval(ctx.rul, merged, ser)
        o = {**iv, "age_at": float(st.ser_age[ser]), "lives": int(st.ser_lives[ser]), "tail": tail, "engine": eng,
             "file": file, "ts": store._now()}
        overrides[ser] = o
        ctx.belief.hums_overrides[ser] = o
        after = ctx.belief.engine_quantiles(st, ser)
        a = _fh(after)
        out.append({"tail": tail, "engine": eng, "serial": ser, "cycles": iv["cycles"], "last_cycle": iv["last_cycle"],
                    "before_fh": _fh(before), "after_fh": a, "alert": a["lo"] < ALERT_FH,
                    "modules": iv["modules"]})
    store.save_hums_overrides(overrides)
    summary = "; ".join(f"{r['tail']} E{r['engine']} RUL {r['before_fh']['med']:.0f} → {r['after_fh']['med']:.0f} FH "
                        f"(90 % {r['after_fh']['lo']:.0f}–{r['after_fh']['hi']:.0f}){' ALERT' if r['alert'] else ''}" for r in out)
    return {"engines": out, "skipped": skipped, "summary": summary or "no engine updated"}


# ------------------------------------------------------------------ technical log
def file_snag_entry(ctx, tail: str, text: str, lru: str | None, day: str, by: str, source: str) -> dict:
    t = ctx.state.tail_ids.index(tail)
    a = ctx.nlp.classify(text, 1)[0]
    return records.file_snag({"date": day, "tail": tail, "squadron": SQN_IDS[int(ctx.state.tail_sqn[t])], "ata": a["ata"],
                              "system": a["name"], "ata_p": a["p"], "lru": lru or "", "text": text.strip().upper()[:400],
                              "filed_by": by, "source": source})


def _repeats(ctx, tail: str, ata: int, day: str, window: int = 30) -> int:
    """Earlier entries on the same tail and ATA chapter within ``window`` days (history + filed)."""
    d = pd.Timestamp(day)
    h = ctx.tables["snags"]
    h = h[(h["tail"] == tail) & (h["ata"] == ata)]
    n = int(((d - pd.to_datetime(h["date"])).dt.days.between(1, window)).sum())
    for f in records.filed_snags():
        if f["tail"] == tail and f.get("ata") == ata and 0 < (d - pd.Timestamp(f["date"])).days <= window:
            n += 1
    return n


def apply_snags(ctx, acc: pd.DataFrame, file: str, by: str = "IMPORT", replace: bool = False) -> dict:
    filed, repeats = [], []
    for _, r in acc.iterrows():
        day = str(pd.Timestamp(r["date"]).date())
        lru = r.get("lru") if isinstance(r.get("lru"), str) and r.get("lru") in LRU_TYPES else None
        e = file_snag_entry(ctx, r["tail"], str(r["text"]), lru, day, by, "IMPORT")
        n_prev = _repeats(ctx, r["tail"], e["ata"], day)
        filed.append(e["snag_id"])
        if n_prev >= 2:
            repeats.append(f"{r['tail']} ATA {e['ata']} ({e['system']}): {n_prev} earlier entries in 30 days — chronic-defect watch")
    return {"filed": len(filed), "first": filed[0] if filed else None, "last": filed[-1] if filed else None,
            "repeats": repeats, "summary": f"{len(filed)} entries filed" + (f"; {len(repeats)} repeat defects" if repeats else "")}


# ------------------------------------------------------------------ logistics
def _stock_count(st, sp: int, li: int) -> int:
    return len(st.stock.get((sp, li), []))


def apply_stock(ctx, acc: pd.DataFrame, file: str, seed: int = 0, replace: bool = False) -> dict:
    st = ctx.state
    override, rows = {}, []
    for _, r in acc.iterrows():
        sp, li = SP_IDX[r["stock_point"]], LRU_IDS.index(r["lru"])
        override[(sp, li)] = int(r["qty"])
        rows.append({"stock_point": r["stock_point"], "lru": r["lru"], "before": _stock_count(st, sp, li), "after": int(r["qty"])})
    _apply_stock(st, override, seed)
    changed = [r for r in rows if r["before"] != r["after"]]
    return {"rows": rows, "summary": f"{len(rows)} stock lines set, {len(changed)} changed"}


def apply_repairs(ctx, acc: pd.DataFrame, file: str, replace: bool = False) -> dict:
    st = ctx.state
    upd = {int(r["serial"]): r for _, r in acc.iterrows()}
    rows, pipe = [], []
    for (ret, ser, cond) in st.pipeline:
        r = upd.get(int(ser))
        if r is None:
            pipe.append((ret, ser, cond))
            continue
        new_ret = max(st.day + 1, date_to_day(r["expected_return"]))
        new_cond = str(r["status"]).upper() == "BER"
        rows.append({"serial": int(ser), "lru": LRU_IDS[int(st.ser_type[ser])], "status": r["status"],
                     "before": str(day_to_date(ret)), "after": str(day_to_date(new_ret)), "condemned": new_cond})
        pipe.append((new_ret, ser, new_cond))
    st.pipeline = pipe
    sooner = sum(1 for r in rows if r["after"] < r["before"])
    return {"rows": rows, "summary": f"{len(rows)} repair orders updated ({sooner} sooner, "
                                     f"{sum(r['condemned'] for r in rows)} condemned)"}


APPLY = {"hums": apply_hums, "snags": apply_snags, "stock": apply_stock, "repairs": apply_repairs}


# ------------------------------------------------------------------ entry points
def ingest(ctx, source: str, raw: bytes, file: str, user, dry_run: bool = False, replace: bool = False) -> dict:
    """Validate an export and, unless ``dry_run`` or the source is validate-only, apply and record it."""
    df, err = read_csv(raw)
    if err:
        return {"report": {"source": source, "ok": False, "rows": 0, "accepted": 0, "rejected": 0, "errors": [err],
                           "row_errors": [], "warnings": []}, "applied": False}
    with _lock:
        rep, acc = validate(source, df, Register.from_state(ctx.state))
        if dry_run or not rep["ok"] or CONTRACTS[source].validate_only:
            return {"report": rep, "applied": False}
        kw = {"replace": replace}
        if source == "snags":
            kw["by"] = user.role
        if source == "stock":
            kw["seed"] = len(store.lineage()) + 1
        result = APPLY[source](ctx, acc, file, **kw)
        sha = hashlib.sha256(raw).hexdigest()
        lin = store.record(source, file, sha, rep, result, user.id, user.role, acc)
        audit.append("data_import", user.role, f"Imported {rep['accepted']} {source} rows from {file}: {result['summary']}"[:480],
                     {"seq": lin["seq"], "source": source, "file": file, "sha256": sha, "rows": rep["rows"],
                      "accepted": rep["accepted"], "rejected": rep["rejected"]}, user=user.id)
        ctx.refresh()
    return {"report": rep, "applied": True, "result": result, "lineage": lin}


def replay(ctx) -> None:
    """Re-apply stored imports to a freshly loaded state (server restart)."""
    ctx.belief.hums_overrides = store.hums_overrides()
    for e in store.lineage():
        if e["source"] in ("stock", "repairs"):
            acc = store.batch(e["seq"], e["source"])
            if e["source"] == "stock":
                apply_stock(ctx, acc, e["file"], seed=e["seq"])
            else:
                apply_repairs(ctx, acc, e["file"])


def reset() -> dict:
    """Remove every import (and imported tech-log entries); the next request reloads the generated state."""
    from ..api import context

    n = store.clear()
    removed = records.remove_imported_snags()
    context.reload()
    return {"imports_removed": n, "snags_removed": removed}
