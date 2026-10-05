"""Readiness-loss accounting: where aircraft-days go, and how many each lever recovers."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .state import STATE_LABELS, STATE_NAMES

LOSS_ORDER = ["NMCS", "NMCM_U", "NMCM_S", "DEPOT", "WAIT"]


def history_waterfall(status: pd.DataFrame, n_tails: int, last_days: int = 365) -> dict:
    """Aircraft-days by status over the last ``last_days`` of recorded history."""
    d1 = int(status["day"].max())
    s = status[status["day"] > d1 - last_days]
    counts = s["state"].value_counts().to_dict()
    possessed = n_tails * last_days
    rows = [{"key": "POSSESSED", "label": "Possessed aircraft-days", "value": possessed}]
    for k in LOSS_ORDER:
        rows.append({"key": k, "label": STATE_LABELS[k], "value": -int(counts.get(k, 0))})
    rows.append({"key": "MC", "label": STATE_LABELS["MC"], "value": int(counts.get("MC", 0))})
    by_sqn = (s.groupby(["squadron", "state"]).size().unstack(fill_value=0) / last_days).round(2)
    return {"days": last_days, "rows": rows, "mc_rate": counts.get("MC", 0) / possessed,
            "by_squadron": by_sqn.reset_index().to_dict("records")}


def forecast_waterfall(state_share_base: dict, state_share_new: dict, n_tails: int, days: int) -> list[dict]:
    """Aircraft-days per cause under current practice vs TATPAR, and the recovered difference."""
    out = []
    for k in LOSS_ORDER + ["MC"]:
        b = state_share_base[k] * n_tails * days
        n = state_share_new[k] * n_tails * days
        out.append({"key": k, "label": STATE_LABELS[k], "baseline": round(b), "tatpar": round(n),
                    "recovered": round(b - n) if k != "MC" else round(n - b)})
    return out


def monthly_mc(status: pd.DataFrame) -> list[dict]:
    s = status.copy()
    s["month"] = pd.to_datetime(s["date"]).dt.to_period("M").astype(str)
    g = s.groupby(["month", "squadron"])["state"].apply(lambda x: float((x == "MC").mean())).unstack()
    g["fleet"] = s.groupby("month")["state"].apply(lambda x: float((x == "MC").mean()))
    return g.round(4).reset_index().to_dict("records")


def pareto_causes(snags: pd.DataFrame, status: pd.DataFrame | None = None) -> list[dict]:
    g = snags.groupby(["ata", "system"]).agg(snags=("snag_id", "size"),
                                              nff=("finding", lambda f: int((f == "NFF").sum()))).reset_index()
    g = g.sort_values("snags", ascending=False)
    g["cum_share"] = g["snags"].cumsum() / g["snags"].sum()
    return g.to_dict("records")


def summarise_states(arr: np.ndarray) -> dict[str, float]:
    return {STATE_NAMES[k]: float((arr == k).mean()) for k in range(len(STATE_NAMES))}
