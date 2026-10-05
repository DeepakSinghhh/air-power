"""Logistics-leak detectors: No-Fault-Found prediction, rogue units, chronic defects.

* **NFF predictor** — at snag time (before the removal decision) estimate the probability
  that the suspect unit will test No-Fault-Found in the shop, from the snag text and context.
  A high score recommends a ground re-test instead of a removal.
* **Rogue units** — serials whose confirmed removals are far above what the fleet reliability
  model predicts for their exposure (Poisson exceedance on cumulative hazard).
* **Chronic defects** — the same tail reporting >= 3 snags in the same ATA chapter within 30 days.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

from ..config import ARTIFACTS_DIR
from ..datagen import history
from ..domain.catalog import LRU_TYPES
from ..domain.environment import base_features
from .survival import COVS, SurvivalModels

INTERMITTENT_RE = re.compile(r"INTERMITTENT|COMES AND GOES|NOT BE REPRODUCED|OCCURRED TWICE|NOT REPEATED", re.I)
RESET_RE = re.compile(r"BITE RESET|BIT PASSED|POWER CYCLE|RESET OK", re.I)
HARD_RE = re.compile(r"LEAK|WORN|NOISY|AWAAZ|SEIZED|FAILS TO|DRAGGING|SURGE|HIGH", re.I)
LRU_LIST = list(LRU_TYPES)
NFF_PATH = ARTIFACTS_DIR / "nff.joblib"


def nff_features(snags: pd.DataFrame, removals: pd.DataFrame | None = None) -> pd.DataFrame:
    """Features available at snag time (no shop finding)."""
    X = pd.DataFrame(index=snags.index)
    X["lru"] = snags["lru"].map(LRU_LIST.index).astype(int)
    X["intermittent"] = snags["text"].str.contains(INTERMITTENT_RE).astype(int)
    X["reset_cleared"] = snags["text"].str.contains(RESET_RE).astype(int)
    X["hard_symptom"] = snags["text"].str.contains(HARD_RE).astype(int)
    X["humidity"] = snags["base"].map(lambda b: base_features(b)["hum"])
    X["month"] = pd.to_datetime(snags["date"]).dt.month
    # same tail & LRU snagged in the previous 60 days (repeat-substitution pattern)
    s = snags.sort_values("day")
    prev = []
    last: dict[tuple[str, str], list[int]] = {}
    for idx, d, t, l in zip(s.index, s["day"], s["tail"], s["lru"]):
        lst = last.setdefault((t, l), [])
        prev.append((idx, sum(1 for x in lst if d - x <= 60)))
        lst.append(d)
    X["repeat_60d"] = pd.Series(dict(prev))
    return X


def _threshold(score: np.ndarray, y: np.ndarray, max_fpr: float = 0.08) -> float:
    """Lowest threshold whose false-positive rate is at most ``max_fpr``."""
    for th in np.linspace(0.05, 0.95, 91):
        if ((score >= th) & (y == 0)).sum() / max(1, (y == 0).sum()) <= max_fpr:
            return float(th)
    return 0.95


@dataclass
class NFFModel:
    model: lgb.LGBMClassifier | None = None
    threshold: float = 0.5
    metrics: dict = field(default_factory=dict)

    def fit(self, verbose: bool = True) -> "NFFModel":
        snags = history.load("snags")
        snags = snags[snags["finding"].isin(["CONFIRMED", "NFF"])].copy()
        X = nff_features(snags)
        y = (snags["finding"] == "NFF").astype(int).to_numpy()
        params = dict(n_estimators=300, learning_rate=0.05, num_leaves=15, min_child_samples=20, verbose=-1)
        groups = snags["tail"].to_numpy()
        oof = np.zeros(len(y))
        hit = np.zeros(len(y), dtype=bool)        # flagged at a threshold chosen without the scored fold
        for tr, te in GroupKFold(n_splits=5).split(X, y, groups=groups):
            m = lgb.LGBMClassifier(**params).fit(X.iloc[tr], y[tr], categorical_feature=["lru"])
            oof[te] = m.predict_proba(X.iloc[te])[:, 1]
            inner = np.zeros(len(tr))
            for itr, ite in GroupKFold(n_splits=4).split(X.iloc[tr], y[tr], groups=groups[tr]):
                mi = lgb.LGBMClassifier(**params).fit(X.iloc[tr[itr]], y[tr[itr]], categorical_feature=["lru"])
                inner[ite] = mi.predict_proba(X.iloc[tr[ite]])[:, 1]
            hit[te] = oof[te] >= _threshold(inner, y[tr])
        auc = roc_auc_score(y, oof)
        # operating point: keep false positives (true failures sent to re-test) at <= 8 %. The rates reported
        # (and used by the twin) are nested: each fold's threshold is chosen on the other folds only.
        best = _threshold(oof, y)
        tpr = (hit & (y == 1)).sum() / max(1, (y == 1).sum())
        fpr = (hit & (y == 0)).sum() / max(1, (y == 0).sum())
        prec = (hit & (y == 1)).sum() / max(1, hit.sum())
        self.model = lgb.LGBMClassifier(**params).fit(X, y, categorical_feature=["lru"])
        self.threshold = float(best)
        self.metrics = {"n": int(len(y)), "nff_rate": float(y.mean()), "auc": float(auc), "threshold": float(best),
                        "tpr": float(tpr), "fpr": float(fpr), "precision": float(prec)}
        if verbose:
            print("NFF:", {k: round(v, 3) for k, v in self.metrics.items()})
        return self

    def predict(self, snags: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(nff_features(snags))[:, 1]

    def save(self, path=NFF_PATH) -> None:
        joblib.dump(self, path)

    @staticmethod
    def load(path=NFF_PATH) -> "NFFModel":
        return joblib.load(path)


def rogue_units(surv: SurvivalModels, min_removals: int = 2, alpha: float = 0.01) -> pd.DataFrame:
    """Flag serials whose lives after repair are repeatedly far shorter than the fleet model predicts.

    For every confirmed removal the probability integral transform u = F(t | survived entry, x)
    is uniform under the reliability model. A rogue unit produces several small u; Fisher's
    method combines them: -2 sum(ln u) ~ chi^2(2k) under the null.
    """
    from scipy.stats import chi2

    rem = history.load("removals")
    conf = rem[(rem["finding"] == "CONFIRMED") & (rem["hours"] > 0)].copy()
    parts = []
    for lru, g in conf.groupby("lru"):
        if lru not in surv.params:
            continue
        X = np.column_stack([g[f"cov_{k}"] / g["hours"] for k in COVS])
        p = surv.params[lru]
        lam = surv.scale(lru, X)
        S = lambda t: np.exp(-(t / lam) ** p["rho"])
        se, st = S(g["entry"].to_numpy()), S(g["hours"].to_numpy())
        u = np.clip((se - st) / np.maximum(se, 1e-12), 1e-9, 1.0)
        parts.append(pd.DataFrame({"serial": g["serial"].to_numpy(), "lru": lru, "u": u,
                                   "hours": g["hours"].to_numpy(), "tail": g["tail"].to_numpy()}))
    lives = pd.concat(parts)
    agg = lives.groupby(["serial", "lru"]).agg(
        removals=("u", "size"), fisher=("u", lambda v: float(-2 * np.log(v).sum())),
        median_life_h=("hours", "median"), last_tail=("tail", "last")).reset_index()
    agg["p_value"] = chi2.sf(agg["fisher"], 2 * agg["removals"])
    # robust reference: the type's fleet median life at removal (insensitive to the rogues themselves)
    ref = lives.groupby("lru")["hours"].median()
    agg["life_ratio"] = agg["median_life_h"] / agg["lru"].map(ref)
    agg["flag"] = (((agg["removals"] >= 3) & (agg["life_ratio"] < 0.25)) |
                   ((agg["removals"] >= min_removals) & (agg["p_value"] < alpha) & (agg["life_ratio"] < 0.25)))
    return agg.sort_values(["flag", "p_value"], ascending=[False, True])


def rogue_metrics(flags: pd.DataFrame) -> dict:
    """Score the detector against the hidden truth (evaluation only)."""
    truth = pd.read_parquet(ARTIFACTS_DIR / "truth" / "serials.parquet").set_index("serial")["rogue"]
    rem = history.load("removals")
    counts = rem[rem["finding"] == "CONFIRMED"].groupby("serial").size()
    rogue_seen = {s for s in counts.index if truth.get(s, False)}
    rogue_3 = {s for s in rogue_seen if counts[s] >= 3}
    flagged = set(flags.loc[flags["flag"], "serial"])
    tp = len(flagged & rogue_seen)
    return {"flagged": len(flagged), "true_rogue_with_removals": len(rogue_seen), "tp": tp,
            "precision": tp / max(1, len(flagged)), "recall": tp / max(1, len(rogue_seen)),
            "recall_3plus_removals": len(flagged & rogue_3) / max(1, len(rogue_3))}


def chronic_defects(window_days: int = 30, min_snags: int = 3) -> pd.DataFrame:
    snags = history.load("snags").sort_values("day")
    out = []
    for (tail, ata), g in snags.groupby(["tail", "ata"]):
        days = g["day"].to_numpy()
        for i in range(len(days)):
            j = np.searchsorted(days, days[i] + window_days, side="right")
            if j - i >= min_snags:
                out.append({"tail": tail, "ata": int(ata), "system": g["system"].iloc[0], "first": int(days[i]),
                            "last": int(days[j - 1]), "snags": int(j - i),
                            "lrus": ", ".join(sorted(set(g["lru"].iloc[i:j])))})
                break
    return pd.DataFrame(out)
