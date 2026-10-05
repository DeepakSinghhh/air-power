"""Short-horizon logistics advisors: predictive lateral transfers, AOG cannibalisation choices,
and depot repair expedite lists — all driven by the belief-layer failure probabilities."""
from __future__ import annotations

from math import ceil, sqrt

import numpy as np

from ..domain.catalog import LRU_TYPES, SQUADRONS, TRANSIT_DAYS
from ..twin.state import ED, ENGINE_IDX, LRU_IDS, NMCM_S, NMCS, SP_IDS, SP_IDX, STATE_NAMES, FleetState


def expected_demand(st: FleetState, belief, horizon_days: int) -> dict[tuple[int, int], float]:
    """Expected removals per (stock point, LRU type) over the horizon (failures only)."""
    risk = belief.risk_fn(st, horizon_days)
    out: dict[tuple[int, int], float] = {}
    for p in np.flatnonzero(st.pos_serial >= 0):
        key = (int(st.tail_sp[st.pos_tail[p]]), int(st.pos_type[p]))
        out[key] = out.get(key, 0.0) + float(risk[p])
    return out


def transfer_plan(st: FleetState, belief, horizon_days: int = 14, z: float = 1.0,
                  bases: list[str] | None = None, focus_window: tuple[int, int] | None = None) -> list[dict]:
    """Move spares ahead of predicted demand: ED first, then bases with a surplus over their own need."""
    dem = expected_demand(st, belief, horizon_days)
    base_sps = [SP_IDX[b] for b in (bases or [s.base for s in SQUADRONS.values()])]
    all_bases = [SP_IDX[s.base] for s in SQUADRONS.values()]
    moves = []
    for li in range(len(LRU_IDS)):
        if li == ENGINE_IDX:
            continue
        need, surplus = {}, {}
        for sp in all_bases:
            mu = dem.get((sp, li), 0.0)
            target = int(ceil(mu + z * sqrt(mu))) if mu > 0.2 else 0
            have = len(st.stock.get((sp, li), []))
            if sp in base_sps and have < target:
                need[sp] = (target - have, mu)
            elif have > target:
                surplus[sp] = have - target
        ed_have = len(st.stock.get((ED, li), []))
        for sp, (q, mu) in sorted(need.items(), key=lambda kv: -kv[1][1]):
            while q > 0:
                if ed_have > 0:
                    src = "ED"
                    ed_have -= 1
                else:
                    donors = [d for d, v in surplus.items() if v > 0 and d != sp]
                    if not donors:
                        break
                    d = max(donors, key=lambda d: surplus[d])
                    surplus[d] -= 1
                    src = SP_IDS[d]
                moves.append({"lru": LRU_IDS[li], "name": LRU_TYPES[LRU_IDS[li]].name, "from": src, "to": SP_IDS[sp],
                              "qty": 1, "expected_demand": round(mu, 2), "eta_days": TRANSIT_DAYS})
                q -= 1
    # merge identical moves
    merged: dict[tuple, dict] = {}
    for m in moves:
        k = (m["lru"], m["from"], m["to"])
        if k in merged:
            merged[k]["qty"] += 1
        else:
            merged[k] = m
    return sorted(merged.values(), key=lambda m: (-m["expected_demand"], m["lru"]))


def apply_transfers(st: FleetState, moves: list[dict]) -> int:
    n = 0
    for m in moves:
        li = LRU_IDS.index(m["lru"])
        src = ED if m["from"] == "ED" else SP_IDX[m["from"]]
        dst = SP_IDX[m["to"]]
        for _ in range(m["qty"]):
            lst = st.stock.get((src, li), [])
            if not lst:
                break
            st.shipments.append((st.day + TRANSIT_DAYS, dst, lst.pop(0), -1))
            n += 1
    return n


def cannibalisation_advice(st: FleetState) -> list[dict]:
    """For each grounded aircraft awaiting a part: wait vs lateral vs cannibalise (consolidated donor)."""
    status = st.status()
    out = []
    for bo in sorted(st.backorders, key=lambda b: b["since"]):
        p, li = bo["pos"], bo["li"]
        t = int(st.pos_tail[p])
        sq = st.tail_sqn[t]
        lid = LRU_IDS[li]
        inbound = [a for (a, _, _, pp) in st.shipments if pp == p]
        if inbound:
            wait = min(inbound) - st.day
            src = "in transit"
        elif st.stock.get((ED, li)):
            wait, src = TRANSIT_DAYS + 1, "depot stock"
        else:
            rets = [r for (r, ser, c) in st.pipeline if int(st.ser_type[ser]) == li and not c]
            wait = (min(rets) - st.day + TRANSIT_DAYS) if rets else 60
            src = "repair pipeline" if rets else "procurement"
        lateral = [SP_IDS[k_sp] for (k_sp, k_li), lst in st.stock.items() if k_li == li and lst and k_sp not in (ED, st.tail_sp[t])]
        donors = []
        for p2 in np.flatnonzero((st.pos_type == li) & (st.pos_serial >= 0)):
            t2 = int(st.pos_tail[p2])
            if t2 == t or st.tail_sqn[t2] != sq or st.check_kind[t2] == "overhaul":
                continue
            s2 = status[t2]
            if s2 == NMCS:
                donors.append({"tail": st.tail_ids[t2], "state": STATE_NAMES[s2],
                               "down_days": int(st.day - st.nmcs_since[t2]) if st.nmcs_since[t2] >= 0 else 0})
            elif s2 == NMCM_S and st.check_end[t2] - st.day >= 4:
                donors.append({"tail": st.tail_ids[t2], "state": STATE_NAMES[s2],
                               "down_days": int(st.check_end[t2] - st.day)})
        donors.sort(key=lambda d: -d["down_days"])
        sole = st.missing[t] == 1
        if wait <= 2:
            rec = "Wait — part arrives within 2 days"
        elif lateral and wait > TRANSIT_DAYS + 1:
            rec = f"Lateral transfer from {lateral[0].title()} ({TRANSIT_DAYS} days)"
        elif donors and sole:
            rec = f"Cannibalise from {donors[0]['tail']} (already down {donors[0]['down_days']} d) — consolidate"
        else:
            rec = "Wait — no lateral stock or eligible donor"
        out.append({"tail": st.tail_ids[t], "squadron": SQUADRONS[list(SQUADRONS)[sq]].id, "lru": lid,
                    "name": LRU_TYPES[lid].name, "down_days": int(st.day - bo["since"]), "eta_days": int(wait),
                    "source": src, "lateral_options": lateral[:3], "donors": donors[:3], "sole_missing_part": bool(sole),
                    "recommendation": rec})
    return out


def expedite_candidates(st: FleetState, belief, sqn: int | None = None, horizon_days: int = 30, k: int = 6) -> list[dict]:
    """Repairs whose early return adds most readiness: types with open demand or predicted shortfall."""
    dem = expected_demand(st, belief, horizon_days)
    open_bo: dict[int, int] = {}
    for bo in st.backorders:
        t = int(st.pos_tail[bo["pos"]])
        if sqn is None or st.tail_sqn[t] == sqn:
            open_bo[bo["li"]] = open_bo.get(bo["li"], 0) + 1
    score = {}
    for li in range(len(LRU_IDS)):
        mu = sum(v for (sp, l), v in dem.items() if l == li and (sqn is None or sp == SP_IDX[list(SQUADRONS.values())[sqn].base]))
        stock = sum(len(st.stock.get((sp, li), [])) for sp in range(len(SP_IDS)))
        score[li] = open_bo.get(li, 0) * 2 + max(0.0, mu - stock)
    rows = []
    for (ret, ser, cond) in st.pipeline:
        li = int(st.ser_type[ser])
        if cond or score.get(li, 0) <= 0:
            continue
        rows.append({"serial": int(ser), "lru": LRU_IDS[li], "name": LRU_TYPES[LRU_IDS[li]].name,
                     "agency": LRU_TYPES[LRU_IDS[li]].agency, "return_in_days": int(ret - st.day),
                     "priority": round(score[li], 2)})
    rows.sort(key=lambda r: (-r["priority"], r["return_in_days"]))
    return rows[:k]


def apply_expedite(st: FleetState, rows: list[dict], factor: float = 0.5) -> None:
    chosen = {r["serial"] for r in rows}
    new = []
    for (ret, ser, cond) in st.pipeline:
        if int(ser) in chosen:
            ret = st.day + max(2, int((ret - st.day) * factor))
        new.append((ret, ser, cond))
    st.pipeline = new
