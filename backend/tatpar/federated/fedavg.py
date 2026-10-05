"""Federated learning across air bases (FedAvg), on NASA C-MAPSS engine data.

Each base holds engines with its own operating profile and fault modes (heterogeneous clients):

    Jodhpur  -> FD004 (six operating regimes, two fault modes — harshest)
    Pune     -> FD001 (one regime, HPC degradation)
    Tezpur   -> FD003 (one regime, HPC + fan degradation)
    Thanjavur-> FD002 (six regimes, HPC degradation)
    Leh      -> 8 FD004 engines only (data-poor forward detachment)

Three regimes are compared on every base's held-out official test engines:
* local-only — each base trains alone on its own engines,
* FedAvg     — bases train locally and share only model weights each round,
* centralised — all raw data pooled (the privacy-violating upper bound).

The model is a small MLP (scikit-learn) on the same rolling HUMS features as the production RUL
model. In production the same loop runs with Flower over AFNET (see notebooks/02_federated_flower.ipynb).
"""
from __future__ import annotations

import json
import time

import numpy as np
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from ..config import ARTIFACTS_DIR
from ..data import cmapss
from ..prognostics.engine_rul import RUL_CAP, EngineRUL

CLIENTS = {"Jodhpur": "FD004", "Pune": "FD001", "Tezpur": "FD003", "Thanjavur": "FD002", "Leh": "FD004"}
LEH_ENGINES = 8   # forward detachment: very little local run-to-failure history


def _client_data(rul: EngineRUL, step: int = 2):
    train = cmapss.load_train()
    test = cmapss.load_test()
    split = set(cmapss.split_units()["train"]) | set(cmapss.split_units()["cal"])
    fd4 = sorted(u for u in split if u.startswith("FD004"))
    leh_units = set(np.random.default_rng(1).choice(fd4, LEH_ENGINES, replace=False))
    data = {}
    for base, fd in CLIENTS.items():
        tr = train[(train["subset"] == fd) & train["uid"].isin(split)]
        if base == "Leh":
            tr = tr[tr["uid"].isin(leh_units)]
        elif base == "Jodhpur":
            tr = tr[~tr["uid"].isin(leh_units)]
        Ftr = rul.featurize(tr)
        ytr = np.minimum(tr["rul"].to_numpy(), RUL_CAP)
        keep = np.arange(len(Ftr)) % step == 0
        te = test[test["subset"] == fd]
        Fte = rul.featurize(te)
        last = Fte.groupby("uid").tail(1)
        yte = np.minimum(te.loc[last.index, "rul"].to_numpy(), RUL_CAP)
        data[base] = (Ftr[rul.feature_names].to_numpy()[keep], ytr[keep], last[rul.feature_names].to_numpy(), yte)
    return data


def _new_model(seed: int) -> MLPRegressor:
    return MLPRegressor(hidden_layer_sizes=(64, 32), learning_rate_init=1e-3, batch_size=256, alpha=1e-4,
                        random_state=seed, max_iter=1, warm_start=True)


def _rmse(m, X, y):
    return float(np.sqrt(((np.clip(m.predict(X), 0, None) - y) ** 2).mean()))


def _set_weights(m: MLPRegressor, coefs, inters):
    m.coefs_ = [c.copy() for c in coefs]
    m.intercepts_ = [b.copy() for b in inters]


def run(rounds: int = 200, local_epochs: int = 1, local_rows: int = 4096, seed: int = 0, verbose: bool = True) -> dict:
    t0 = time.time()
    rul = EngineRUL.load()
    data = _client_data(rul)
    scaler = StandardScaler().fit(np.vstack([d[0] for d in data.values()]))   # shared feature schema (only means/stds)
    data = {b: (scaler.transform(Xtr), ytr, scaler.transform(Xte), yte) for b, (Xtr, ytr, Xte, yte) in data.items()}
    total_epochs = 40      # same order of local computation as the federated run

    # local-only
    local = {}
    for b, (Xtr, ytr, Xte, yte) in data.items():
        m = _new_model(seed)
        for _ in range(total_epochs):
            m.partial_fit(Xtr, ytr)
        local[b] = _rmse(m, Xte, yte)

    # centralised (pooled raw data)
    Xall = np.vstack([d[0] for d in data.values()])
    yall = np.concatenate([d[1] for d in data.values()])
    mc = _new_model(seed)
    for _ in range(total_epochs):
        mc.partial_fit(Xall, yall)
    central = {b: _rmse(mc, d[2], d[3]) for b, d in data.items()}

    # FedAvg with stateful clients (each base keeps its optimiser state between rounds)
    g = _new_model(seed)
    g.partial_fit(data["Pune"][0][:512], data["Pune"][1][:512])        # initialise weight shapes
    clients = {}
    for b, (Xtr, ytr, _, _) in data.items():
        m = _new_model(seed)
        m.partial_fit(Xtr[:256], ytr[:256])
        clients[b] = m
    curve = []
    n = {b: len(d[1]) for b, d in data.items()}
    N = sum(n.values())
    rng = np.random.default_rng(seed)
    for r in range(rounds):
        coefs, inters = [], []
        for b, (Xtr, ytr, _, _) in data.items():
            m = clients[b]
            _set_weights(m, g.coefs_, g.intercepts_)
            idx = rng.choice(len(ytr), size=min(local_rows, len(ytr)), replace=False)
            m.partial_fit(Xtr[idx], ytr[idx])       # a few local steps: limits client drift on non-IID bases
            coefs.append([c * n[b] for c in m.coefs_])
            inters.append([c * n[b] for c in m.intercepts_])
        _set_weights(g, [sum(c[i] for c in coefs) / N for i in range(len(g.coefs_))],
                     [sum(c[i] for c in inters) / N for i in range(len(g.intercepts_))])
        if (r + 1) % 10 == 0:
            curve.append({"round": r + 1, "rmse": float(np.mean([_rmse(g, d[2], d[3]) for d in data.values()]))})
    fed = {b: _rmse(g, d[2], d[3]) for b, d in data.items()}
    # personalised: the federated model fine-tuned for one epoch on the base's own data
    pers = {}
    for b, (Xtr, ytr, Xte, yte) in data.items():
        m = clients[b]
        _set_weights(m, g.coefs_, g.intercepts_)
        m.partial_fit(Xtr, ytr)
        pers[b] = _rmse(m, Xte, yte)

    mean = lambda d: float(np.mean(list(d.values())))
    out = {
        "description": "FedAvg across five bases with heterogeneous engines (NASA C-MAPSS subsets), including a data-poor "
                       "Leh detachment with 8 engines; RMSE on each base's held-out official test engines. Only model weights leave a base.",
        "clients": CLIENTS, "rounds": rounds, "local_rows_per_round": local_rows,
        "results": [
            {"regime": "Local only (each base alone)", "rmse": mean(local), "per_base": local, "data_moved": "No"},
            {"regime": "Federated (FedAvg, weights only)", "rmse": mean(fed), "per_base": fed, "data_moved": "No — weights only"},
            {"regime": "Federated + local fine-tune (personalised)", "rmse": mean(pers), "per_base": pers, "data_moved": "No — weights only"},
            {"regime": "Centralised (all raw data pooled)", "rmse": mean(central), "per_base": central, "data_moved": "Yes — all HUMS data"},
        ],
        "curve": curve, "elapsed_s": time.time() - t0,
    }
    (ARTIFACTS_DIR / "bench").mkdir(parents=True, exist_ok=True)
    (ARTIFACTS_DIR / "bench" / "federated.json").write_text(json.dumps(out, indent=1))
    if verbose:
        print("federated:", {r["regime"]: round(r["rmse"], 2) for r in out["results"]}, f"{out['elapsed_s']:.0f}s")
    return out


if __name__ == "__main__":
    run()
