"""LRU reliability: Weibull accelerated-failure-time models with environment & usage covariates.

Lives are reconstructed from the maintenance records: each confirmed removal ends a life
(event), installed items still flying are right-censored. Covariates are exposure-weighted
means over the life: base dust / heat / humidity indices and mission g-severity.

    S(t | x) = exp(-(t / lambda(x))^rho),   log lambda(x) = b0 + b . x

Vectorised closed-form survival lets the Fleet Twin and the optimisers query thousands of
conditional failure probabilities per second.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import joblib
import numpy as np
import pandas as pd
from lifelines import WeibullAFTFitter
from lifelines.utils import concordance_index

from ..config import ARTIFACTS_DIR
from ..datagen import history
from ..domain.catalog import LRU_TYPES

COVS = ["dust", "heat", "hum", "g"]
MODEL_PATH = ARTIFACTS_DIR / "survival.joblib"


def build_lives(removals: pd.DataFrame, positions: pd.DataFrame) -> pd.DataFrame:
    """One row per life since last repair. Lives already running when records began are
    left-truncated at ``entry`` (hours on the record card at that date)."""
    ev = removals[(removals["finding"] == "CONFIRMED") & (removals["hours"] > 0)].copy()
    ev["event"] = 1
    ce = positions[(positions["serial"] >= 0) & (positions["hours"] > 0)].copy()
    ce["event"] = 0
    cols = ["lru", "serial", "hours", "entry", "event", "repairs"] + [f"cov_{k}" for k in COVS]
    lives = pd.concat([ev[cols], ce[cols]], ignore_index=True)
    lives = lives[lives["hours"] > lives["entry"] + 1e-6]
    for k in COVS:
        lives[k] = lives[f"cov_{k}"] / lives["hours"]
    return lives.drop(columns=[f"cov_{k}" for k in COVS])


@dataclass
class SurvivalModels:
    params: dict = field(default_factory=dict)     # lru -> {"b0":, "b": array, "rho":}
    metrics: dict = field(default_factory=dict)

    def fit(self, verbose: bool = True, exclude_serials: set | None = None) -> "SurvivalModels":
        lives = build_lives(history.load("removals"), history.load("positions"))
        if exclude_serials:   # flagged rogue units are modelled separately
            lives = lives[~lives["serial"].isin(exclude_serials)]
        rows = []
        for lru, g in lives.groupby("lru"):
            if LRU_TYPES[lru].is_engine:
                continue   # engines use the HUMS-based RUL model
            df = g[COVS + ["hours", "entry", "event"]].copy()
            mu = df[COVS].mean().to_numpy()
            df[COVS] = df[COVS] - mu          # centred: intercept = fleet-average conditions
            aft = WeibullAFTFitter(penalizer=0.01)
            aft.fit(df, duration_col="hours", event_col="event", entry_col="entry")
            lam = aft.params_["lambda_"]
            b0 = float(lam["Intercept"])
            b = np.array([float(lam[k]) for k in COVS])
            rho = float(np.exp(aft.params_["rho_"]["Intercept"]))
            self.params[lru] = {"b0": b0, "b": b, "rho": rho, "mu": mu}
            ci = concordance_index(df["hours"], aft.predict_median(df[COVS]), df["event"])
            rows.append({"lru": lru, "events": int(df["event"].sum()), "censored": int((1 - df["event"]).sum()),
                         "c_index": float(ci), "rho_hat": rho, "beta_true": LRU_TYPES[lru].beta})
        tab = pd.DataFrame(rows)
        self.metrics = {
            "per_lru": tab.to_dict("records"),
            "mean_c_index": float(tab["c_index"].mean()),
            "shape_mae": float((tab["rho_hat"] - tab["beta_true"]).abs().mean()),
            "life_recovery": self._life_recovery(),
        }
        if verbose:
            print(f"survival: {len(tab)} LRU models, mean C-index {self.metrics['mean_c_index']:.3f}, "
                  f"shape MAE {self.metrics['shape_mae']:.2f}, life R² {self.metrics['life_recovery']['r2_log']:.3f}")
        return self

    def _life_recovery(self) -> dict:
        """Predicted vs true mean life at each squadron base (truth from the catalogue)."""
        from ..domain.catalog import SQUADRONS
        from ..domain.environment import base_features, severity_multiplier

        pts = []
        for lru, p in self.params.items():
            l = LRU_TYPES[lru]
            for sq in SQUADRONS.values():
                f = base_features(sq.base)
                x = np.array([f["dust"], f["heat"], f["hum"], 1.15])
                lam = np.exp(p["b0"] + p["b"] @ (x - p["mu"]))
                from math import gamma
                pred = lam * gamma(1 + 1 / p["rho"])
                true = l.mean_life_fh / severity_multiplier(l, sq.base, 1.15)
                pts.append((lru, sq.base, pred, true))
        a = np.log([q[2] for q in pts])
        b = np.log([q[3] for q in pts])
        r2 = 1 - ((a - b) ** 2).sum() / ((b - b.mean()) ** 2).sum()
        return {"r2_log": float(r2), "points": [{"lru": q[0], "base": q[1], "pred": float(q[2]), "true": float(q[3])} for q in pts]}

    # ------------------------------------------------------------ queries
    def scale(self, lru: str, X: np.ndarray) -> np.ndarray:
        """Weibull scale for raw (uncentred) covariates; rows of NaN mean 'fleet average'."""
        p = self.params[lru]
        Z = np.nan_to_num(np.asarray(X, float) - p["mu"], nan=0.0)
        return np.exp(p["b0"] + Z @ p["b"])

    def cond_fail_prob(self, lru: str, age: np.ndarray, horizon: np.ndarray, X: np.ndarray) -> np.ndarray:
        """P(failure within ``horizon`` more flight hours | survived ``age``)."""
        p = self.params[lru]
        lam = self.scale(lru, X)
        rho = p["rho"]
        h0 = (age / lam) ** rho
        h1 = ((age + horizon) / lam) ** rho
        return 1.0 - np.exp(-(h1 - h0))

    def sample_remaining(self, lru: str, age: np.ndarray, X: np.ndarray, u: np.ndarray) -> np.ndarray:
        """Remaining flight hours given survival to ``age`` (inverse transform)."""
        p = self.params[lru]
        lam = self.scale(lru, X)
        rho = p["rho"]
        total = lam * ((age / lam) ** rho - np.log(u)) ** (1 / rho)
        return total - age

    def save(self, path=MODEL_PATH) -> None:
        joblib.dump(self, path)

    @staticmethod
    def load(path=MODEL_PATH) -> "SurvivalModels":
        return joblib.load(path)
