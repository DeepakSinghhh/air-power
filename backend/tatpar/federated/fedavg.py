"""Federated learning across air bases (FedAvg), on NASA C-MAPSS engine data.

Each base holds engines with its own operating profile and fault modes (heterogeneous clients):

    Jodhpur  -> FD004 (six operating regimes, two fault modes — harshest)
    Pune     -> FD001 (one regime, HPC degradation)
    Tezpur   -> FD003 (one regime, HPC + fan degradation)
    Thanjavur-> FD002 (six regimes, HPC degradation)
    Leh      -> 8 FD004 engines only (data-poor forward detachment)

Three regimes are compared, each scored on the base's own held-out official test engines (Leh and
Jodhpur get disjoint parts of the FD004 test set):
* local-only — each base trains alone on its own engines, with its own normalisation,
* FedAvg     — bases train locally and share only model weights and aggregate feature statistics
               (counts, sums, sums of squares) — never an engine record,
* centralised — all raw data pooled (the privacy-violating upper bound).

What leaves a base is the same in every round: model weights, plus once at the start the per-feature
counts/sums/sums-of-squares used for normalisation and one validation RMSE per checkpoint. Operating
regimes are the six published C-MAPSS flight conditions, not learnt from anyone's data. Every regime
runs the same local computation (``rounds`` × ``local_rows`` rows per base) and keeps the checkpoint
with the best validation RMSE on the base's own held-out training engines, so the local-only baseline
is not starved of training steps.

The model is a small MLP (scikit-learn) on the same rolling HUMS features as the production RUL
model. In production the same loop runs with Flower over AFNET (sketched in notebooks/02_federated_bases.ipynb).
"""
from __future__ import annotations

import copy
import json
import time

import numpy as np
from sklearn.neural_network import MLPRegressor

from ..config import ARTIFACTS_DIR
from ..data import cmapss
from ..prognostics.engine_rul import RUL_CAP, USE_SENSORS, EngineRUL

CLIENTS = {"Jodhpur": "FD004", "Pune": "FD001", "Tezpur": "FD003", "Thanjavur": "FD002", "Leh": "FD004"}
LEH_ENGINES = 8          # forward detachment: very little local run-to-failure history
LEH_TEST_SHARE = 0.25    # Leh's share of the FD004 official test engines (the rest are Jodhpur's)
VAL_SHARE = 0.2          # each base holds out this share of its training engines for checkpoint selection
# The six C-MAPSS flight conditions (altitude kft, Mach, throttle resolver angle), Saxena et al. 2008.
FLIGHT_CONDITIONS = np.array([[0, 0, 100], [10, 0.25, 100], [20, 0.7, 100], [25, 0.62, 60], [35, 0.84, 100], [42, 0.84, 100]])


class _Conditions:
    """Regime = nearest published flight condition (scaled so each setting counts comparably)."""
    scale = np.array([42.0, 0.84, 40.0])

    def predict(self, X):
        d = ((X[:, None, :] - FLIGHT_CONDITIONS[None]) / self.scale) ** 2
        return d.sum(-1).argmin(1)


def _sensor_stats(rul: EngineRUL, df) -> dict:
    """Per-regime sensor count, sum and sum of squares — the only thing a base reveals for normalisation."""
    reg = rul._regime(df)
    X = df[USE_SENSORS].to_numpy(dtype=float)
    return {r: (int((reg == r).sum()), X[reg == r].sum(0), (X[reg == r] ** 2).sum(0)) for r in range(len(FLIGHT_CONDITIONS))}


def _norm_from(stats: list[dict]) -> dict:
    out = {}
    for r in range(len(FLIGHT_CONDITIONS)):
        n = sum(s[r][0] for s in stats)
        if n == 0:
            continue
        mu = sum(s[r][1] for s in stats) / n
        var = np.maximum(sum(s[r][2] for s in stats) / n - mu ** 2, 0)
        out[r] = (mu, np.sqrt(var) + 1e-6)
    return out


def _feature_stats(X: np.ndarray) -> tuple[int, np.ndarray, np.ndarray]:
    return len(X), X.sum(0), (X ** 2).sum(0)


def _scaler_from(stats: list[tuple]) -> tuple[np.ndarray, np.ndarray]:
    n = sum(s[0] for s in stats)
    mu = sum(s[1] for s in stats) / n
    sd = np.sqrt(np.maximum(sum(s[2] for s in stats) / n - mu ** 2, 0)) + 1e-6
    return mu, sd


def _raw_client_data():
    """Each base's training engines (split into fit / validation) and its own official test engines."""
    train = cmapss.load_train()
    test = cmapss.load_test()
    split = set(cmapss.split_units()["train"]) | set(cmapss.split_units()["cal"])
    fd4 = sorted(u for u in split if u.startswith("FD004"))
    leh_units = set(np.random.default_rng(1).choice(fd4, LEH_ENGINES, replace=False))
    fd4_test = sorted(test.loc[test["subset"] == "FD004", "uid"].unique())
    leh_test = set(np.random.default_rng(2).choice(fd4_test, int(len(fd4_test) * LEH_TEST_SHARE), replace=False))
    rng = np.random.default_rng(3)
    data = {}
    for base, fd in CLIENTS.items():
        tr = train[(train["subset"] == fd) & train["uid"].isin(split)]
        te = test[test["subset"] == fd]
        if base == "Leh":
            tr, te = tr[tr["uid"].isin(leh_units)], te[te["uid"].isin(leh_test)]
        elif base == "Jodhpur":
            tr, te = tr[~tr["uid"].isin(leh_units)], te[~te["uid"].isin(leh_test)]
        units = sorted(tr["uid"].unique())
        val_units = set(rng.choice(units, max(2, int(round(len(units) * VAL_SHARE))), replace=False))
        data[base] = {"fit": tr[~tr["uid"].isin(val_units)], "val": tr[tr["uid"].isin(val_units)], "test": te}
    return data


def _features(rul: EngineRUL, raw: dict, norm: dict, step: int = 2):
    """Rolling HUMS features for one base, normalised with the given per-regime statistics."""
    r = copy.copy(rul)
    r.kmeans, r.norm = _Conditions(), norm
    Ff = r.featurize(raw["fit"])
    keep = np.arange(len(Ff)) % step == 0
    yf = np.minimum(raw["fit"]["rul"].to_numpy(), RUL_CAP)
    Fv = r.featurize(raw["val"])
    yv = np.minimum(raw["val"]["rul"].to_numpy(), RUL_CAP)
    Ft = r.featurize(raw["test"])
    last = Ft.groupby("uid").tail(1)
    yt = np.minimum(raw["test"].loc[last.index, "rul"].to_numpy(), RUL_CAP)
    cols = rul.feature_names
    return Ff[cols].to_numpy()[keep], yf[keep], Fv[cols].to_numpy()[::step], yv[::step], last[cols].to_numpy(), yt


def _new_model(seed: int) -> MLPRegressor:
    return MLPRegressor(hidden_layer_sizes=(64, 32), learning_rate_init=1e-3, batch_size=256, alpha=1e-4,
                        random_state=seed, max_iter=1, warm_start=True)


def _rmse(m, X, y):
    return float(np.sqrt(((np.clip(m.predict(X), 0, None) - y) ** 2).mean()))


def _set_weights(m: MLPRegressor, coefs, inters):
    m.coefs_ = [c.copy() for c in coefs]
    m.intercepts_ = [b.copy() for b in inters]


def _weights(m):
    return [c.copy() for c in m.coefs_], [b.copy() for b in m.intercepts_]


def _scaled(d, mu, sd):
    Xf, yf, Xv, yv, Xt, yt = d
    return (Xf - mu) / sd, yf, (Xv - mu) / sd, yv, (Xt - mu) / sd, yt


def _train(m, draw, val, rounds: int, check_every: int = 10):
    """Run ``rounds`` local steps; keep the weights with the lowest validation RMSE."""
    best, best_w = np.inf, None
    for r in range(rounds):
        X, y = draw()
        m.partial_fit(X, y)
        if (r + 1) % check_every == 0:
            v = val(m)
            if v < best:
                best, best_w = v, _weights(m)
    if best_w is not None:
        _set_weights(m, *best_w)
    return m


def run(rounds: int = 200, local_epochs: int = 1, local_rows: int = 4096, seed: int = 0, verbose: bool = True) -> dict:
    t0 = time.time()
    rul = EngineRUL.load()
    raw = _raw_client_data()
    probe = copy.copy(rul)
    probe.kmeans = _Conditions()
    sstats = {b: _sensor_stats(probe, d["fit"]) for b, d in raw.items()}
    shared_norm = _norm_from(list(sstats.values()))            # aggregate of every base's sums: no records move
    local_data = {b: _features(rul, raw[b], _norm_from([sstats[b]])) for b in raw}
    fed_data = {b: _features(rul, raw[b], shared_norm) for b in raw}
    local_data = {b: _scaled(d, *_scaler_from([_feature_stats(d[0])])) for b, d in local_data.items()}
    mu, sd = _scaler_from([_feature_stats(d[0]) for d in fed_data.values()])
    fed_data = {b: _scaled(d, mu, sd) for b, d in fed_data.items()}
    rng = np.random.default_rng(seed)

    def draw_from(d):
        return lambda: (lambda idx: (d[0][idx], d[1][idx]))(rng.choice(len(d[1]), size=min(local_rows, len(d[1])), replace=False))

    # local-only: the same local computation as a federated client, never averaged
    local = {}
    for b, d in local_data.items():
        m = _train(_new_model(seed), draw_from(d), lambda m, d=d: _rmse(m, d[2], d[3]), rounds)
        local[b] = _rmse(m, d[4], d[5])

    # centralised (pooled raw data): each step sees the same rows the five bases would draw that round
    pooled_draws = [draw_from(d) for d in fed_data.values()]

    def pooled():
        parts = [f() for f in pooled_draws]
        return np.vstack([p[0] for p in parts]), np.concatenate([p[1] for p in parts])
    Xv_all = np.vstack([d[2] for d in fed_data.values()])
    yv_all = np.concatenate([d[3] for d in fed_data.values()])
    mc = _train(_new_model(seed), pooled, lambda m: _rmse(m, Xv_all, yv_all), rounds)
    central = {b: _rmse(mc, d[4], d[5]) for b, d in fed_data.items()}

    # FedAvg with stateful clients (each base keeps its optimiser state between rounds)
    g = _new_model(seed)
    g.partial_fit(fed_data["Pune"][0][:512], fed_data["Pune"][1][:512])        # initialise weight shapes
    clients = {}
    for b, d in fed_data.items():
        m = _new_model(seed)
        m.partial_fit(d[0][:256], d[1][:256])
        clients[b] = m
    curve = []
    n = {b: len(d[1]) for b, d in fed_data.items()}
    N = sum(n.values())
    draws = {b: draw_from(d) for b, d in fed_data.items()}
    best, best_w = np.inf, _weights(g)
    for r in range(rounds):
        coefs, inters = [], []
        for b in fed_data:
            m = clients[b]
            _set_weights(m, g.coefs_, g.intercepts_)
            m.partial_fit(*draws[b]())               # a few local steps: limits client drift on non-IID bases
            coefs.append([c * n[b] for c in m.coefs_])
            inters.append([c * n[b] for c in m.intercepts_])
        _set_weights(g, [sum(c[i] for c in coefs) / N for i in range(len(g.coefs_))],
                     [sum(c[i] for c in inters) / N for i in range(len(g.intercepts_))])
        if (r + 1) % 10 == 0:
            # each base reports one number: the global model's RMSE on its own validation engines
            v = sum(n[b] * _rmse(g, d[2], d[3]) for b, d in fed_data.items()) / N
            if v < best:
                best, best_w = v, _weights(g)
            curve.append({"round": r + 1, "rmse": float(np.mean([_rmse(g, d[4], d[5]) for d in fed_data.values()]))})
    _set_weights(g, *best_w)
    fed = {b: _rmse(g, d[4], d[5]) for b, d in fed_data.items()}
    # personalised: the federated model fine-tuned on the base's own data (best of 5 epochs on its validation engines)
    pers = {}
    for b, d in fed_data.items():
        m = clients[b]
        _set_weights(m, g.coefs_, g.intercepts_)
        m = _train(m, lambda d=d: (d[0], d[1]), lambda m, d=d: _rmse(m, d[2], d[3]), 5, check_every=1)
        pers[b] = _rmse(m, d[4], d[5])

    mean = lambda d: float(np.mean(list(d.values())))
    out = {
        "description": "FedAvg across five bases with heterogeneous engines (NASA C-MAPSS subsets), including a data-poor "
                       "Leh detachment with 8 engines; RMSE on each base's own held-out official test engines (Leh and "
                       "Jodhpur use disjoint FD004 test engines). Only model weights and aggregate feature statistics "
                       "leave a base; every regime gets the same local training steps and keeps its best checkpoint on "
                       "the base's own validation engines.",
        "clients": CLIENTS, "rounds": rounds, "local_rows_per_round": local_rows,
        "test_engines": {b: int(raw[b]["test"]["uid"].nunique()) for b in raw},
        "train_engines": {b: int(raw[b]["fit"]["uid"].nunique()) for b in raw},
        "results": [
            {"regime": "Local only (each base alone)", "rmse": mean(local), "per_base": local, "data_moved": "No"},
            {"regime": "Federated (FedAvg, weights only)", "rmse": mean(fed), "per_base": fed,
             "data_moved": "No — weights and aggregate statistics only"},
            {"regime": "Federated + local fine-tune (personalised)", "rmse": mean(pers), "per_base": pers,
             "data_moved": "No — weights and aggregate statistics only"},
            {"regime": "Centralised (all raw data pooled)", "rmse": mean(central), "per_base": central, "data_moved": "Yes — all HUMS data"},
        ],
        "curve": curve, "elapsed_s": time.time() - t0,
    }
    (ARTIFACTS_DIR / "bench").mkdir(parents=True, exist_ok=True)
    (ARTIFACTS_DIR / "bench" / "federated.json").write_text(json.dumps(out, indent=1))
    if verbose:
        print("federated:", {r["regime"]: round(r["rmse"], 2) for r in out["results"]}, f"{out['elapsed_s']:.0f}s")
        for r in out["results"]:
            print("  ", r["regime"][:28], {k: round(v, 1) for k, v in r["per_base"].items()})
    return out


if __name__ == "__main__":
    run()
