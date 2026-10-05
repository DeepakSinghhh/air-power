"""CSV templates and realistic samples for each data contract, built from the live fleet register so
every sample row refers to a real tail, serial or stock point and passes validation."""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from ..data import cmapss
from ..domain.catalog import LRU_TYPES, SQUADRONS
from ..twin.simulator import day_to_date
from ..twin.state import LRU_IDS, SP_IDS
from .contracts import CONTRACTS

DEMO_CUT = 35          # the sample download stops this many cycles before the replayed engine's end of life


def template(source: str) -> pd.DataFrame:
    return pd.DataFrame(columns=CONTRACTS[source].columns)


def demo_unit() -> tuple[str, pd.DataFrame]:
    """A run-to-failure C-MAPSS engine the RUL model never trained or calibrated on (fleet split, FD001)."""
    fleet = [u for u in cmapss.split_units()["fleet"] if u.startswith("FD001")]
    tr = cmapss.load_train()
    life = tr[tr["uid"].isin(fleet)].groupby("uid")["cycle"].max()
    uid = sorted(u for u, n in life.items() if 180 <= n <= 260)[0]
    return uid, tr[tr["uid"] == uid].sort_values("cycle")


def demo_engine(ctx) -> tuple[str, int]:
    """First serviceable twin-engine aircraft whose engine 1 is healthy: where the HUMS demo lands."""
    from .apply import engine_serial

    st = ctx.state
    status = st.status()
    for t, tail in enumerate(st.tail_ids):
        if not tail.startswith("HF") or status[t] != 0:
            continue
        ser = engine_serial(st, tail, 1)
        if ser >= 0 and ctx.belief.engine_quantiles(st, ser)[1] >= 100:
            return tail, 1
    return st.tail_ids[0], 1


def hums_rows(tail: str, engine: int, traj: pd.DataFrame, today) -> pd.DataFrame:
    last = int(traj["cycle"].max())
    out = pd.DataFrame({"tail": tail, "engine": engine, "cycle": traj["cycle"].astype(int).to_numpy(),
                        "date": [str(today - timedelta(days=(last - int(c)) // 2)) for c in traj["cycle"]]})
    for c in cmapss.SETTINGS + cmapss.SENSORS:
        out[c] = traj[c].round(4).to_numpy()
    return out


def sample(ctx, source: str) -> pd.DataFrame:
    st = ctx.state
    today = day_to_date(st.day)
    if source == "hums":
        tail, eng = demo_engine(ctx)
        _, traj = demo_unit()
        return hums_rows(tail, eng, traj[traj["cycle"] <= traj["cycle"].max() - DEMO_CUT], today)
    if source == "snags":
        first = [next(t for i, t in enumerate(st.tail_ids) if st.tail_sqn[i] == k) for k in range(len(SQUADRONS))]
        rows = [(first[0], "HYD PRESSURE LH SYSTEM MEIN FLUCTUATION, TAXI KE DAURAN", "HYD_PUMP", "SGT RAWAT"),
                (first[1], "RWR INOP ON GROUND TEST, BITE FAIL", "", "CPL NAIR"),
                (first[2], "FUEL QTY IND FLUCTUATING IN FLIGHT, LH TANK", "FQP", "SGT DAS"),
                (first[3], "INTERCOM NOISY BOTH COCKPITS. BITE RESET OK", "", "CPL KHAN")]
        return pd.DataFrame([{"date": str(today), "tail": t, "text": x, "lru": l, "reported_by": r} for t, x, l, r in rows])
    if source == "stock":
        rows = []
        for sp, lru, add in (("jodhpur", "HYD_PUMP", 2), ("jodhpur", "GEN", 1), ("ED", "INS", 2), ("ED", "FCU", 1)):
            have = len(st.stock.get((SP_IDS.index(sp), LRU_IDS.index(lru)), []))
            rows.append({"stock_point": sp, "lru": lru, "qty": have + add, "as_of": str(today)})
        return pd.DataFrame(rows)
    if source == "repairs":
        rows = []
        for ret, ser, cond in sorted(st.pipeline, key=lambda x: -x[0])[:6]:
            if cond:
                continue
            lru = LRU_IDS[int(st.ser_type[ser])]
            sooner = max(st.day + 2, ret - 10)
            rows.append({"serial": int(ser), "lru": lru, "agency": LRU_TYPES[lru].agency, "status": "IN_WORK",
                         "expected_return": str(day_to_date(sooner)), "finding": "CONFIRMED"})
        return pd.DataFrame(rows[:4])
    if source == "sorties":
        tails = [t for i, t in enumerate(st.tail_ids) if st.tail_sqn[i] == 0][:4]
        rng = np.random.default_rng(0)
        return pd.DataFrame([{"date": str(today), "tail": t, "hours": round(float(rng.uniform(0.8, 1.6)), 1),
                              "mission": m} for t, m in zip(tails, ("training", "air_combat", "strike", "recce_nav"))])
    raise KeyError(source)


def write_samples(ctx, out_dir) -> list[str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for src in CONTRACTS:
        p = out_dir / f"{src}_sample.csv"
        sample(ctx, src).to_csv(p, index=False)
        written.append(p.name)
    return written
