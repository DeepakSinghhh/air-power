"""Engine remaining useful life with calibrated (conformal) prediction intervals.

* Operating-condition normalisation: KMeans on the three settings (six regimes in
  FD002/FD004), then per-regime z-scores of each sensor.
* Rolling-window features (30 cycles): smoothed level, mean, slope, std per sensor.
* LightGBM quantile regression at 5 %, 50 % and 95 %, target RUL capped at 125 cycles.
* Conformalised Quantile Regression (Romano et al., 2019) on held-out calibration engines
  widens the band so the 90 % interval achieves ~90 % coverage.
* SHAP attributions on the median model are aggregated by engine module.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from ..config import ARTIFACTS_DIR
from ..data import cmapss

USE_SENSORS = ["T24", "T30", "T50", "P30", "Nf", "Nc", "Ps30", "phi", "NRf", "NRc", "BPR", "htBleed", "W31", "W32"]
WINDOW = 30
RUL_CAP = 125
ALPHA = 0.10
MODEL_PATH = ARTIFACTS_DIR / "engine_rul.joblib"


def _slope(y: np.ndarray) -> float:
    n = len(y)
    if n < 3:
        return 0.0
    x = np.arange(n) - (n - 1) / 2
    return float((x * (y - y.mean())).sum() / (x * x).sum())


@dataclass
class EngineRUL:
    kmeans: KMeans | None = None
    norm: dict = field(default_factory=dict)          # regime -> (mean, std) arrays
    models: dict = field(default_factory=dict)        # quantile -> booster
    q_conformal: float = 0.0
    feature_names: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    # ------------------------------------------------------------ features
    def _regime(self, df: pd.DataFrame) -> np.ndarray:
        return self.kmeans.predict(df[cmapss.SETTINGS].round(2).to_numpy())

    def _normalise(self, df: pd.DataFrame) -> pd.DataFrame:
        reg = self._regime(df)
        X = df[USE_SENSORS].to_numpy(dtype=float)
        Z = np.zeros_like(X)
        for r, (mu, sd) in self.norm.items():
            m = reg == r
            Z[m] = (X[m] - mu) / sd
        out = pd.DataFrame(Z, columns=USE_SENSORS, index=df.index)
        out["uid"] = df["uid"].to_numpy()
        out["cycle"] = df["cycle"].to_numpy()
        out["multi_regime"] = df["subset"].isin(["FD002", "FD004"]).astype(int).to_numpy()
        return out

    def featurize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Rolling features for every cycle of every unit in ``df``."""
        z = self._normalise(df)
        g = z.groupby("uid", sort=False)
        feats = {"cycle": z["cycle"], "multi_regime": z["multi_regime"]}
        for s in USE_SENSORS:
            col = g[s]
            feats[f"{s}_ewm"] = col.transform(lambda v: v.ewm(alpha=0.1).mean())
            feats[f"{s}_mean"] = col.transform(lambda v: v.rolling(WINDOW, min_periods=1).mean())
            feats[f"{s}_std"] = col.transform(lambda v: v.rolling(WINDOW, min_periods=2).std()).fillna(0)
            feats[f"{s}_slope"] = col.transform(lambda v: v.rolling(WINDOW, min_periods=3).apply(_slope, raw=True)).fillna(0)
        F = pd.DataFrame(feats, index=z.index)
        F["uid"] = z["uid"]
        return F

    # ------------------------------------------------------------ fit
    def fit(self, verbose: bool = True) -> "EngineRUL":
        train_df = cmapss.load_train()
        split = cmapss.split_units()
        tr = train_df[train_df["uid"].isin(split["train"])]
        cal = train_df[train_df["uid"].isin(split["cal"])]

        self.kmeans = KMeans(n_clusters=6, n_init=10, random_state=0).fit(train_df[cmapss.SETTINGS].round(2).to_numpy())
        reg = self._regime(tr)
        for r in range(6):
            X = tr.loc[reg == r, USE_SENSORS].to_numpy(dtype=float)
            self.norm[r] = (X.mean(0), X.std(0) + 1e-6)

        Ftr = self.featurize(tr)
        self.feature_names = [c for c in Ftr.columns if c != "uid"]
        ytr = np.minimum(tr["rul"].to_numpy(), RUL_CAP)
        params = dict(n_estimators=500, learning_rate=0.04, num_leaves=31, min_child_samples=40,
                      subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
        for q in (0.05, 0.5, 0.95):
            m = lgb.LGBMRegressor(objective="quantile", alpha=q, **params)
            m.fit(Ftr[self.feature_names], ytr)
            self.models[q] = m

        # conformal calibration on held-out engines (several truncation points per engine)
        Fcal = self.featurize(cal)
        rng = np.random.default_rng(0)
        idx = []
        for _, g in Fcal.groupby("uid"):
            idx += list(rng.choice(g.index, size=min(5, len(g)), replace=False))
        Fc = Fcal.loc[idx]
        yc = np.minimum(cal.loc[idx, "rul"].to_numpy(), RUL_CAP)
        lo, hi = self.models[0.05].predict(Fc[self.feature_names]), self.models[0.95].predict(Fc[self.feature_names])
        scores = np.maximum(lo - yc, yc - hi)
        n = len(scores)
        self.q_conformal = float(np.quantile(scores, min(1.0, (1 - ALPHA) * (n + 1) / n)))
        raw_cov = float(((yc >= lo) & (yc <= hi)).mean())
        self.metrics = {"cal_points": n, "q_conformal": self.q_conformal, "cal_raw_coverage": raw_cov}
        self.metrics.update(self.evaluate())
        if verbose:
            print("engine RUL:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in self.metrics.items() if not isinstance(v, dict)})
        return self

    # ------------------------------------------------------------ predict
    def predict_features(self, F: pd.DataFrame) -> pd.DataFrame:
        X = F[self.feature_names]
        q05, q50, q95 = (self.models[q].predict(X) for q in (0.05, 0.5, 0.95))
        q50 = np.clip(q50, 0, None)
        lo = np.clip(np.minimum(q05, q50) - self.q_conformal, 0, None)
        hi = np.maximum(q95, q50) + self.q_conformal
        return pd.DataFrame({"rul_lo": lo, "rul_med": q50, "rul_hi": hi,
                             "raw_lo": q05, "raw_hi": q95}, index=F.index)

    def predict_last(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prediction at the last available cycle of each unit in ``df``."""
        F = self.featurize(df)
        last = F.groupby("uid").tail(1)
        out = self.predict_features(last)
        out["uid"] = last["uid"].to_numpy()
        out["cycle"] = last["cycle"].to_numpy()
        return out.reset_index(drop=True)

    def explain(self, df: pd.DataFrame) -> dict[str, float]:
        """SHAP contribution (in cycles of RUL) aggregated per engine module, last cycle of one unit."""
        import shap

        F = self.featurize(df).tail(1)[self.feature_names]
        expl = shap.TreeExplainer(self.models[0.5].booster_)
        sv = expl.shap_values(F)[0]
        mod: dict[str, float] = {}
        for name, v in zip(self.feature_names, sv):
            sensor = name.split("_")[0]
            m = cmapss.SENSOR_MODULE.get(sensor, "Usage")
            if name in ("cycle", "multi_regime"):
                m = "Usage / age"
            mod[m] = mod.get(m, 0.0) + float(v)
        return dict(sorted(mod.items(), key=lambda kv: kv[1]))

    # ------------------------------------------------------------ evaluate
    def evaluate(self) -> dict:
        test = cmapss.load_test()
        pred = self.predict_last(test)
        truth = test.groupby("uid").tail(1).set_index("uid")["rul"]
        pred["subset"] = pred["uid"].str[:5]
        pred["y"] = np.minimum(truth.loc[pred["uid"]].to_numpy(), RUL_CAP)
        out = {}
        for fd, g in list(pred.groupby("subset")) + [("ALL", pred)]:
            err = g["rul_med"] - g["y"]
            score = np.where(err < 0, np.exp(-err / 13) - 1, np.exp(err / 10) - 1).sum()
            cov = ((g["y"] >= g["rul_lo"]) & (g["y"] <= g["rul_hi"])).mean()
            raw = ((g["y"] >= g["raw_lo"]) & (g["y"] <= g["raw_hi"])).mean()
            out[fd] = {"n": int(len(g)), "rmse": float(np.sqrt((err ** 2).mean())), "nasa_score": float(score),
                       "picp90": float(cov), "picp90_uncalibrated": float(raw),
                       "mpiw": float((g["rul_hi"] - g["rul_lo"]).mean())}
        return {"test": out}

    # ------------------------------------------------------------ io
    def save(self, path=MODEL_PATH) -> None:
        joblib.dump(self, path)

    @staticmethod
    def load(path=MODEL_PATH) -> "EngineRUL":
        return joblib.load(path)


def hums_window(uid: str, cycle: int) -> pd.DataFrame:
    """HUMS history of a fleet engine: its C-MAPSS trajectory up to ``cycle``."""
    df = cmapss.load_train()
    return df[(df["uid"] == uid) & (df["cycle"] <= cycle)]


def rul_quantile_sampler(lo: float, med: float, hi: float, u: np.ndarray, alpha: float = ALPHA) -> np.ndarray:
    """Inverse-CDF sampling through the calibrated (alpha/2, 0.5, 1-alpha/2) quantiles."""
    p = np.array([0.0, alpha / 2, 0.5, 1 - alpha / 2, 1.0])
    v = np.array([0.0, lo, med, hi, hi + (hi - med) * 0.6])
    v = np.maximum.accumulate(v)
    return np.interp(u, p, v)
