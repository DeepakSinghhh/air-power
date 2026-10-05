"""Generate two years of notional fleet history with the Fleet Twin (baseline practice).

Outputs (``artifacts/history``): the *observable* records an integrated maintenance system
would hold — sorties, snags with logbook text, removals and shop findings, scheduled
checks, supply transactions, cannibalisations, daily status, engine HUMS pointers.
Ground truth the analytics must never read (life budgets, rogue flags) goes to
``artifacts/truth``. The end-of-history twin state is pickled as "today".
"""
from __future__ import annotations

import pickle
import time

import numpy as np
import pandas as pd

from ..config import ARTIFACTS_DIR, FH_PER_CYCLE, HISTORY_DAYS, SEED
from ..domain.catalog import AIRCRAFT_TYPES, LRU_TYPES, SQUADRONS
from ..twin.policies import BASELINE
from ..twin.simulator import Simulator, day_to_date
from ..twin.state import LRU_IDS, SP_IDS, SQN_IDS, STATE_NAMES, TYPE_IDS, build_initial_state
from .snag_text import REPORTERS, action_text, snag_text

HIST_DIR = ARTIFACTS_DIR / "history"
TRUTH_DIR = ARTIFACTS_DIR / "truth"
STATE_PATH = ARTIFACTS_DIR / "state_today.pkl"


def tail_table(st) -> pd.DataFrame:
    rows = []
    for t, tail in enumerate(st.tail_ids):
        sq = SQUADRONS[SQN_IDS[st.tail_sqn[t]]]
        ty = AIRCRAFT_TYPES[TYPE_IDS[st.tail_type[t]]]
        rows.append({"tail": tail, "squadron": sq.id, "base": sq.base, "type": ty.id, "type_label": ty.label})
    return pd.DataFrame(rows)


def generate(seed: int = SEED, days: int = HISTORY_DAYS, verbose: bool = True) -> dict[str, pd.DataFrame]:
    t0 = time.time()
    st = build_initial_state(seed)
    sim = Simulator(st, BASELINE, seed=seed + 1, record=True).run(days)
    rng = np.random.default_rng(seed + 2)
    tails = tail_table(st)
    tail_of = dict(enumerate(st.tail_ids))
    R = sim.rec

    def dt(d):
        return pd.Timestamp(day_to_date(d))

    sorties = pd.DataFrame(R["sorties"], columns=["day", "t", "hours", "g_mean"])
    sorties["tail"] = sorties["t"].map(tail_of)
    sorties["date"] = sorties["day"].map(dt)
    sorties = sorties.drop(columns="t").merge(tails[["tail", "squadron", "base", "type"]], on="tail")
    sorties["sorties"] = (sorties["hours"] / sorties["type"].map(lambda k: AIRCRAFT_TYPES[k].sortie_hours)).round().astype(int)

    removals = pd.DataFrame(R["removals"])
    removals["date"] = removals["day"].map(dt)
    removals["removal_id"] = [f"RM-{i:05d}" for i in range(len(removals))]
    truth_removals = removals[["removal_id", "rogue_truth", "age_eff", "engine_unit"]].copy()
    removals = removals.drop(columns=["rogue_truth", "age_eff", "engine_unit"])

    snags = pd.DataFrame(R["snags"], columns=["day", "tail", "lru", "pos", "kind", "intermittent", "bite_reset", "serial"])
    snags["date"] = snags["day"].map(dt)
    snags["snag_id"] = [f"SG-{i:05d}" for i in range(len(snags))]
    snags["ata"] = snags["lru"].map(lambda k: LRU_TYPES[k].ata)
    snags["system"] = snags["lru"].map(lambda k: LRU_TYPES[k].system)
    snags["text"] = [snag_text(l, i, b, rng) for l, i, b in zip(snags["lru"], snags["intermittent"], snags["bite_reset"])]
    snags["reported_by"] = rng.choice(REPORTERS, len(snags))
    # link to removal / shop finding
    key = removals.set_index(["day", "tail", "serial"])
    findings, rem_ids = [], []
    for d, tl, sn in zip(snags["day"], snags["tail"], snags["serial"]):
        try:
            r = key.loc[(d, tl, sn)]
            r = r.iloc[0] if isinstance(r, pd.DataFrame) else r
            findings.append(r["finding"])
            rem_ids.append(r["removal_id"])
        except KeyError:
            findings.append("RETEST")
            rem_ids.append(None)
    snags["finding"] = findings
    snags["removal_id"] = rem_ids
    snags["action"] = [action_text(l, f, int(s), rng) for l, f, s in zip(snags["lru"], snags["finding"], snags["serial"])]
    snags = snags.merge(tails[["tail", "squadron", "base"]], on="tail")

    checks = pd.DataFrame(R["checks"], columns=["tail", "check", "start_day", "end_day"])
    checks["start"] = checks["start_day"].map(dt)
    checks["end"] = checks["end_day"].map(dt)
    supply = pd.DataFrame(R["supply"], columns=["day", "lru", "from", "to", "kind"])
    supply["date"] = supply["day"].map(dt)
    cann = pd.DataFrame(R["cann"], columns=["day", "donor", "recipient", "lru", "serial"])
    cann["date"] = cann["day"].map(dt)
    repairs = pd.DataFrame(R["repairs"], columns=["serial", "lru", "sent_day", "return_day", "finding", "condemned"])

    A = sim.status_array()
    status = pd.DataFrame({
        "day": np.repeat(np.arange(A.shape[0]), A.shape[1]),
        "tail": np.tile(st.tail_ids, A.shape[0]),
        "state": [STATE_NAMES[k] for k in A.ravel()],
    })
    status["date"] = status["day"].map(dt)
    status = status.merge(tails[["tail", "squadron", "base"]], on="tail")

    # current installed configuration (observable: serial, hours since repair, exposure, repairs)
    pos_rows = []
    for p in range(len(st.pos_tail)):
        s = int(st.pos_serial[p])
        row = {"pos": p, "tail": st.tail_ids[st.pos_tail[p]], "lru": LRU_IDS[st.pos_type[p]], "serial": s}
        if s >= 0:
            row.update({"hours": float(st.ser_hrs[s]), "repairs": int(st.ser_repairs[s]),
                        "entry": float(st.ser_entry[s]),
                        "life_start": int(st.ser_life_start[s]),
                        **{f"cov_{k}": float(st.ser_cov[s, i]) for i, k in enumerate(("dust", "heat", "hum", "alt", "salt", "g"))}})
        pos_rows.append(row)
    positions = pd.DataFrame(pos_rows)

    eng_rows = []
    for p in np.flatnonzero(st.pos_type == LRU_IDS.index("ENGINE")):
        s = int(st.pos_serial[p])
        if s < 0:
            continue
        u = int(st.ser_unit[s])
        life = st.engine_unit_life[u]
        cyc = int(min(life - 1, max(1, st.ser_age[s] // FH_PER_CYCLE)))
        eng_rows.append({"pos": int(p), "tail": st.tail_ids[st.pos_tail[p]], "serial": s,
                         "cmapss_uid": st.engine_units[u], "hums_cycle": cyc, "hours": float(st.ser_hrs[s])})
    engines = pd.DataFrame(eng_rows)

    stock = pd.DataFrame([
        {"stock_point": SP_IDS[sp], "lru": LRU_IDS[li], "qty": len(v)} for (sp, li), v in st.stock.items()
    ])

    out = {"tails": tails, "sorties": sorties, "snags": snags, "removals": removals, "checks": checks,
           "supply": supply, "cann": cann, "repairs": repairs, "status": status, "positions": positions,
           "engines": engines, "stock": stock}

    HIST_DIR.mkdir(parents=True, exist_ok=True)
    TRUTH_DIR.mkdir(parents=True, exist_ok=True)
    for k, df in out.items():
        df.to_parquet(HIST_DIR / f"{k}.parquet", index=False)
    truth = pd.DataFrame({
        "serial": np.arange(st.n_ser), "lru": [LRU_IDS[i] for i in st.ser_type[: st.n_ser]],
        "rogue": st.ser_rogue[: st.n_ser], "life_budget": st.ser_L[: st.n_ser], "age_eff": st.ser_age[: st.n_ser],
    })
    truth.to_parquet(TRUTH_DIR / "serials.parquet", index=False)
    truth_removals.to_parquet(TRUTH_DIR / "removals.parquet", index=False)
    with open(STATE_PATH, "wb") as f:
        pickle.dump(st, f)
    if verbose:
        mc = (A == 0).mean()
        print(f"history: {days} days, {len(snags)} snags, {len(removals)} removals, MC {mc:.1%}, "
              f"{time.time() - t0:.1f}s")
    return out


def load(name: str) -> pd.DataFrame:
    return pd.read_parquet(HIST_DIR / f"{name}.parquet")


def load_state():
    with open(STATE_PATH, "rb") as f:
        return pickle.load(f)


if __name__ == "__main__":
    generate()
