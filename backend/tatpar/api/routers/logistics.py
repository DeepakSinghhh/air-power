"""Sustainment: stock by echelon, repair pipeline, readiness-based sparing, advisors, leaks."""
from __future__ import annotations

from collections import Counter

from fastapi import APIRouter

from ...domain.catalog import LRU_TYPES
from ...optimize.advisors import cannibalisation_advice
from ...twin.state import LRU_IDS, SP_IDS
from ..context import get_ctx

router = APIRouter(prefix="/api", tags=["logistics"])


@router.get("/sustainment")
def sustainment():
    ctx = get_ctx()
    st = ctx.state
    stock = []
    for (sp, li), lst in st.stock.items():
        stock.append({"stock_point": SP_IDS[sp], "lru": LRU_IDS[li], "qty": len(lst)})
    pipe = Counter()
    for (ret, ser, cond) in st.pipeline:
        lid = LRU_IDS[int(st.ser_type[ser])]
        pipe[(LRU_TYPES[lid].agency, lid)] += 1
    pipeline = [{"agency": a, "lru": l, "qty": q} for (a, l), q in pipe.items()]
    transit = Counter(SP_IDS[sp] for (_, sp, _, _) in st.shipments)
    backorders = Counter(LRU_IDS[b["li"]] for b in st.backorders)
    rem = ctx.tables["removals"]
    last = rem[rem["day"] >= rem["day"].max() - 365]
    nff = last.groupby("lru").agg(removals=("removal_id", "size"),
                                  nff=("finding", lambda f: int((f == "NFF").sum()))).reset_index()
    nff["nff_rate"] = nff["nff"] / nff["removals"]
    nff["name"] = nff["lru"].map(lambda k: LRU_TYPES[k].name)
    rogue = ctx.tables["rogue_units"]
    rogue_rows = rogue[rogue["flag"]].head(30).to_dict("records") if len(rogue) else []
    for r in rogue_rows:
        r["name"] = LRU_TYPES[r["lru"]].name
    adv = ctx.bench("advisors") or {}
    supply_flow = [
        {"source": "Squadron bases", "target": "Repair agencies", "value": len(last)},
        {"source": "Repair agencies", "target": "Equipment depot", "value": int(len(last) * 0.96)},
        {"source": "Equipment depot", "target": "Squadron bases", "value": int(len(last) * 0.96)},
    ]
    return {
        "stock": stock, "pipeline": pipeline, "in_transit": dict(transit), "backorders": dict(backorders),
        "rbs": ctx.bench("rbs"), "advisors": {**adv, "cannibalisation": cannibalisation_advice(st)},
        "nff": nff.sort_values("nff_rate", ascending=False).to_dict("records"), "rogue": rogue_rows,
        "supply_flow": supply_flow,
        "lrus": {l.id: {"name": l.name, "cost_lakh": l.cost_lakh, "source": l.source, "agency": l.agency,
                        "lead_days": l.lead_days, "tat_days": l.tat_days} for l in LRU_TYPES.values()},
    }
