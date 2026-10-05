# %% [markdown]
# # TATPAR · Federated engine prognostics across air bases (Colab)
#
# Five bases train an engine-RUL model **without sharing raw HUMS data**: only model weights travel
# (over AFNET in production). Bases differ in operating regime and fault modes (non-IID), and Leh is
# a forward detachment with only 8 engines of history.
#
# Compares local-only, FedAvg, FedProx (proximal term against client drift) and centralised training.
# The production path is [Flower](https://flower.ai): each base runs a `NumPyClient` wrapping the same
# `train`/`evaluate` functions below; the server runs `FedAvg`/`FedProx` strategies (see section 4).

# %%
import io, os, urllib.request, zipfile, copy
import numpy as np, pandas as pd, torch, torch.nn as nn
ROUNDS = int(os.environ.get("ROUNDS", 60)); LOCAL_STEPS = int(os.environ.get("LOCAL_STEPS", 20)); MU = 0.01
RUL_CAP = 125; torch.manual_seed(0); np.random.seed(0)
DIR = os.environ.get("CMAPSS_DIR", "cmapss")
URL = "https://phm-datasets.s3.amazonaws.com/NASA/6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip"
if not os.path.exists(f"{DIR}/train_FD001.txt"):
    os.makedirs(DIR, exist_ok=True)
    outer = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(URL).read()))
    zipfile.ZipFile(io.BytesIO(outer.read(next(n for n in outer.namelist() if n.endswith("CMAPSSData.zip"))))).extractall(DIR)

COLS = ["unit", "cycle", "s1", "s2", "s3"] + [f"x{i}" for i in range(21)]
USE = [f"x{i}" for i in (1, 2, 3, 6, 7, 8, 10, 11, 12, 13, 14, 16, 19, 20)]
def load(kind, fd):
    df = pd.read_csv(f"{DIR}/{kind}_{fd}.txt", sep=r"\s+", header=None).iloc[:, :26]; df.columns = COLS; df["fd"] = fd
    if kind == "train":
        df["rul"] = df.groupby("unit").cycle.transform("max") - df.cycle
    else:
        r = pd.read_csv(f"{DIR}/RUL_{fd}.txt", header=None)[0].to_numpy()
        df["rul"] = r[df.unit.to_numpy() - 1] + df.groupby("unit").cycle.transform("max") - df.cycle
    return df

def regime(df):
    return df[["s1", "s2", "s3"]].round(0).astype(str).agg("|".join, axis=1)

def fit_stats(df):
    g = df.groupby(regime(df))[USE]
    return g.mean(), g.std() + 1e-6

def features(df, stats):
    # per-unit rolling means over 30 cycles of regime-normalised sensors; stats come from training data only
    df = df.copy(); key = regime(df); mu, sd = stats
    df[USE] = (df[USE] - mu.reindex(key).to_numpy()) / sd.reindex(key).to_numpy()
    roll = df.groupby(["fd", "unit"])[USE].transform(lambda v: v.rolling(30, min_periods=1).mean())
    X = np.hstack([roll.to_numpy(), df[["cycle"]].to_numpy() / 300.0]).astype(np.float32)
    return X, np.minimum(df.rul.to_numpy(), RUL_CAP).astype(np.float32)

BASES = {"Jodhpur": "FD004", "Pune": "FD001", "Tezpur": "FD003", "Thanjavur": "FD002", "Leh": "FD004"}
clients = {}
fd4_units = np.random.default_rng(1).permutation(load("train", "FD004").unit.unique())
for b, fd in BASES.items():
    tr = load("train", fd)
    if b == "Leh": tr = tr[tr.unit.isin(fd4_units[:8])]
    if b == "Jodhpur": tr = tr[~tr.unit.isin(fd4_units[:8])]
    te = load("test", fd); te_last = te.groupby("unit").tail(1).index
    st = fit_stats(tr); Xtr, ytr = features(tr, st); Xte_all, yte_all = features(te, st)
    pos = te.index.get_indexer(te_last)
    clients[b] = (torch.tensor(Xtr), torch.tensor(ytr), torch.tensor(Xte_all[pos]), torch.tensor(yte_all[pos]))
print({b: len(c[1]) for b, c in clients.items()})

# %%
def net():
    return nn.Sequential(nn.Linear(len(USE) + 1, 64), nn.ReLU(), nn.Linear(64, 32), nn.ReLU(), nn.Linear(32, 1))

def train(model, X, y, steps, global_params=None, mu=0.0, lr=1e-3):
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    for _ in range(steps):
        idx = torch.randint(0, len(X), (256,))
        loss = ((model(X[idx]).squeeze(-1) - y[idx]) ** 2).mean()
        if mu and global_params is not None:   # FedProx proximal term
            loss = loss + mu / 2 * sum(((p - g) ** 2).sum() for p, g in zip(model.parameters(), global_params))
        opt.zero_grad(); loss.backward(); opt.step()
    return model

@torch.no_grad()
def rmse(model, X, y):
    return float(torch.sqrt(((model(X).squeeze(-1).clamp(min=0) - y) ** 2).mean()))

def federated(mu):
    g = net(); n = {b: len(c[1]) for b, c in clients.items()}; N = sum(n.values())
    for r in range(ROUNDS):
        states = []
        for b, (X, y, _, _) in clients.items():
            m = copy.deepcopy(g); gp = [p.detach().clone() for p in g.parameters()]
            states.append((n[b], train(m, X, y, LOCAL_STEPS, gp, mu).state_dict()))
        g.load_state_dict({k: sum(w * s[k] for w, s in states) / N for k in states[0][1]})
    return g

results = {}
results["Local only"] = {b: rmse(train(net(), X, y, ROUNDS * LOCAL_STEPS), Xe, ye) for b, (X, y, Xe, ye) in clients.items()}
g = federated(0.0); results["FedAvg"] = {b: rmse(g, c[2], c[3]) for b, c in clients.items()}
g = federated(MU); results["FedProx"] = {b: rmse(g, c[2], c[3]) for b, c in clients.items()}
Xall = torch.cat([c[0] for c in clients.values()]); yall = torch.cat([c[1] for c in clients.values()])
cm = train(net(), Xall, yall, ROUNDS * LOCAL_STEPS * len(clients)); results["Centralised (pooled raw data)"] = {b: rmse(cm, c[2], c[3]) for b, c in clients.items()}
print(pd.DataFrame(results).T.round(1).assign(mean=lambda d: d.mean(1).round(2)))

# %% [markdown]
# ## 4 · Deploying with Flower
# ```python
# import flwr as fl
# class BaseClient(fl.client.NumPyClient):
#     def __init__(self, base): self.base, self.model = base, net()
#     def get_parameters(self, config): return [p.detach().numpy() for p in self.model.state_dict().values()]
#     def fit(self, parameters, config):
#         self.model.load_state_dict({k: torch.tensor(v) for k, v in zip(self.model.state_dict(), parameters)})
#         X, y, _, _ = clients[self.base]; train(self.model, X, y, LOCAL_STEPS)
#         return self.get_parameters(config), len(y), {}
#     def evaluate(self, parameters, config):
#         self.model.load_state_dict({k: torch.tensor(v) for k, v in zip(self.model.state_dict(), parameters)})
#         _, _, Xe, ye = clients[self.base]; return rmse(self.model, Xe, ye) ** 2, len(ye), {}
# # Each base: fl.client.start_client(server_address="<hq-aggregator>:8080", client=BaseClient("Jodhpur").to_client())
# # HQ:        fl.server.start_server(config=fl.server.ServerConfig(num_rounds=60), strategy=fl.server.strategy.FedProx(proximal_mu=0.01))
# ```
# Add secure aggregation / differential privacy (Flower `SecAgg+`, `DifferentialPrivacyClientSideFixedClipping`) for
# classified environments; transport runs over the existing AFNET backbone with mutual TLS.
