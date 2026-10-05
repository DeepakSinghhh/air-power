# %% [markdown]
# # TATPAR · Deep engine RUL with calibrated intervals (Colab)
#
# A 1D-CNN + Transformer encoder predicts remaining useful life (RUL) quantiles from a 30-cycle
# window of HUMS sensors, trained with pinball loss on **NASA C-MAPSS FD001–FD004**. Conformalised
# quantile regression (CQR) on held-out engines then guarantees ~90 % interval coverage.
#
# * Runs on a free Colab GPU in a few minutes (`Runtime → Change runtime type → GPU`).
# * Uses the same engine split as the TATPAR platform (train 60 % / calibration 20 % / fleet 20 %),
#   so results are comparable with the LightGBM model in `artifacts/metrics.json`.
# * Set `EPOCHS` small for a smoke test.

# %%
import io, os, time, urllib.request, zipfile
import numpy as np, pandas as pd, torch, torch.nn as nn
from sklearn.cluster import KMeans

EPOCHS = int(os.environ.get("EPOCHS", 30))
WINDOW, RUL_CAP, ALPHA = 30, 125, 0.10
QUANTILES = (0.05, 0.5, 0.95)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
torch.manual_seed(0); np.random.seed(0)
print("device", DEVICE)

# %% [markdown]
# ## 1 · Data

# %%
URL = "https://phm-datasets.s3.amazonaws.com/NASA/6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip"
DIR = os.environ.get("CMAPSS_DIR", "cmapss")
if not os.path.exists(os.path.join(DIR, "train_FD001.txt")):
    os.makedirs(DIR, exist_ok=True)
    outer = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(URL).read()))
    inner = next(n for n in outer.namelist() if n.endswith("CMAPSSData.zip"))
    zipfile.ZipFile(io.BytesIO(outer.read(inner))).extractall(DIR)

SETTINGS = ["setting1", "setting2", "setting3"]
SENSORS = ["T2", "T24", "T30", "T50", "P2", "P15", "P30", "Nf", "Nc", "epr", "Ps30", "phi", "NRf", "NRc", "BPR",
           "farB", "htBleed", "Nf_dmd", "PCNfR_dmd", "W31", "W32"]
USE = ["T24", "T30", "T50", "P30", "Nf", "Nc", "Ps30", "phi", "NRf", "NRc", "BPR", "htBleed", "W31", "W32"]
COLS = ["unit", "cycle"] + SETTINGS + SENSORS

def read(p):
    df = pd.read_csv(p, sep=r"\s+", header=None).iloc[:, :len(COLS)]
    df.columns = COLS
    return df

train, test = [], []
for fd in ("FD001", "FD002", "FD003", "FD004"):
    a = read(f"{DIR}/train_{fd}.txt"); a["subset"] = fd; a["uid"] = fd + "-" + a.unit.astype(str)
    a["rul"] = a.groupby("uid").cycle.transform("max") - a.cycle
    b = read(f"{DIR}/test_{fd}.txt"); b["subset"] = fd; b["uid"] = fd + "-T" + b.unit.astype(str)
    r = pd.read_csv(f"{DIR}/RUL_{fd}.txt", header=None)[0].to_numpy()
    b["rul"] = r[b.unit.to_numpy() - 1] + (b.groupby("unit").cycle.transform("max") - b.cycle)
    train.append(a); test.append(b)
train, test = pd.concat(train, ignore_index=True), pd.concat(test, ignore_index=True)

# same deterministic split as the platform (tatpar.data.cmapss.split_units)
rng = np.random.default_rng(7)
split = {"train": [], "cal": [], "fleet": []}
for _, g in train[["uid", "subset"]].drop_duplicates().groupby("subset"):
    u = g.uid.to_numpy().copy(); rng.shuffle(u); n = len(u)
    split["train"] += list(u[: int(.6 * n)]); split["cal"] += list(u[int(.6 * n): int(.8 * n)]); split["fleet"] += list(u[int(.8 * n):])

# operating-regime normalisation
km = KMeans(6, n_init=10, random_state=0).fit(train[SETTINGS].round(2).to_numpy())
tr_mask = train.uid.isin(split["train"])
reg_tr = km.predict(train.loc[tr_mask, SETTINGS].round(2).to_numpy())
stats = {r: (train.loc[tr_mask, USE].to_numpy()[reg_tr == r].mean(0), train.loc[tr_mask, USE].to_numpy()[reg_tr == r].std(0) + 1e-6) for r in range(6)}

def normalise(df):
    reg = km.predict(df[SETTINGS].round(2).to_numpy()); X = df[USE].to_numpy(float); Z = np.zeros_like(X)
    for r, (mu, sd) in stats.items():
        Z[reg == r] = (X[reg == r] - mu) / sd
    return Z

def windows(df, last_only=False):
    Z = normalise(df); out_x, out_y = [], []
    for uid, idx in df.groupby("uid", sort=False).indices.items():
        z, y = Z[idx], np.minimum(df.rul.to_numpy()[idx], RUL_CAP)
        if len(z) < WINDOW:
            z = np.vstack([np.repeat(z[:1], WINDOW - len(z), 0), z]); y = np.concatenate([np.repeat(y[:1], WINDOW - len(y)), y])
        ends = [len(z)] if last_only else range(WINDOW, len(z) + 1)
        for e in ends:
            out_x.append(z[e - WINDOW:e]); out_y.append(y[e - 1])
    return np.array(out_x, np.float32), np.array(out_y, np.float32)

Xtr, ytr = windows(train[train.uid.isin(split["train"])])
Xcal, ycal = windows(train[train.uid.isin(split["cal"])])
Xte, yte = windows(test, last_only=True)
print("train windows", Xtr.shape, "calibration", Xcal.shape, "test engines", Xte.shape)

# %% [markdown]
# ## 2 · Model: 1D-CNN front end + Transformer encoder + three quantile heads

# %%
class RULNet(nn.Module):
    def __init__(self, n_feat=len(USE), d=64):
        super().__init__()
        self.conv = nn.Sequential(nn.Conv1d(n_feat, d, 5, padding=2), nn.GELU(), nn.Conv1d(d, d, 3, padding=1), nn.GELU())
        self.pos = nn.Parameter(torch.randn(1, WINDOW, d) * 0.02)
        enc = nn.TransformerEncoderLayer(d, nhead=4, dim_feedforward=128, dropout=0.1, batch_first=True)
        self.encoder = nn.TransformerEncoder(enc, num_layers=2)
        self.head = nn.Sequential(nn.Linear(d, 64), nn.GELU(), nn.Linear(64, len(QUANTILES)))

    def forward(self, x):
        h = self.conv(x.transpose(1, 2)).transpose(1, 2) + self.pos
        h = self.encoder(h)[:, -1]
        return self.head(h)

def pinball(pred, y):
    q = torch.tensor(QUANTILES, device=pred.device)
    e = y[:, None] - pred
    return torch.maximum(q * e, (q - 1) * e).mean()

model = RULNet().to(DEVICE)
opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(1, EPOCHS))
Xt, yt = torch.tensor(Xtr), torch.tensor(ytr)
t0 = time.time()
for ep in range(EPOCHS):
    model.train(); perm = torch.randperm(len(Xt)); tot = 0
    for i in range(0, len(Xt), 512):
        b = perm[i:i + 512]
        loss = pinball(model(Xt[b].to(DEVICE)), yt[b].to(DEVICE))
        opt.zero_grad(); loss.backward(); opt.step(); tot += loss.item() * len(b)
    sched.step()
    if ep % 5 == 0 or ep == EPOCHS - 1:
        print(f"epoch {ep:3d}  pinball {tot / len(Xt):.3f}  {time.time() - t0:.0f}s")

# %% [markdown]
# ## 3 · Conformal calibration (CQR) and evaluation on the official test sets

# %%
@torch.no_grad()
def predict(X):
    model.eval(); out = []
    for i in range(0, len(X), 4096):
        out.append(model(torch.tensor(X[i:i + 4096]).to(DEVICE)).cpu().numpy())
    return np.vstack(out)

pc = predict(Xcal)
scores = np.maximum(pc[:, 0] - ycal, ycal - pc[:, 2])
n = len(scores)
qhat = np.quantile(scores, min(1.0, (1 - ALPHA) * (n + 1) / n))
pt = predict(Xte)
lo, med, hi = np.clip(pt[:, 0] - qhat, 0, None), np.clip(pt[:, 1], 0, None), pt[:, 2] + qhat
err = med - yte
res = pd.DataFrame({"subset": test.groupby("uid", sort=False).subset.first().to_numpy(), "err": err,
                    "raw_cov": (yte >= pt[:, 0]) & (yte <= pt[:, 2]), "cov": (yte >= lo) & (yte <= hi), "width": hi - lo})
def nasa(e): return np.where(e < 0, np.exp(-e / 13) - 1, np.exp(e / 10) - 1).sum()
summary = res.groupby("subset").apply(lambda g: pd.Series({"rmse": np.sqrt((g.err ** 2).mean()), "nasa_score": nasa(g.err),
                                                           "picp90_raw": g.raw_cov.mean(), "picp90_cqr": g["cov"].mean(),
                                                           "mpiw": g.width.mean()}))
summary.loc["ALL"] = [np.sqrt((res.err ** 2).mean()), nasa(res.err), res.raw_cov.mean(), res["cov"].mean(), res.width.mean()]
print(f"conformal widening q = {qhat:.2f} cycles")
print(summary.round(3))

# %% [markdown]
# ## 4 · Export for the platform
# Save the weights and the conformal constant; the platform's `EngineRUL` interface can wrap this
# model (`predict_features` → quantiles + `q_conformal`).

# %%
torch.save({"state_dict": model.state_dict(), "q_conformal": float(qhat), "use": USE, "window": WINDOW,
            "regime_stats": {k: (v[0].tolist(), v[1].tolist()) for k, v in stats.items()}}, "engine_rul_deep.pt")
print("saved engine_rul_deep.pt")

# %% [markdown]
# ## 5 · Optional — N-CMAPSS (real flight profiles, module health parameters)
# N-CMAPSS (Arias Chao et al., *Data* 6(1):5, 2021) adds real commercial flight conditions and the
# hidden health parameters of each engine module. On Colab, download `N-CMAPSS_DS02-006.h5` from the
# NASA Prognostics Data Repository and train a multi-task head (RUL + fan/LPC/HPC/HPT/LPT
# efficiency/flow modifiers) to explain *which module* is degrading. Skipped by default (≈ 2.5 GB).
