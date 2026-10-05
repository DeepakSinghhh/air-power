"""NASA C-MAPSS turbofan degradation data (FD001-FD004).

Saxena, Goebel, Simon & Eklund (2008), "Damage propagation modeling for aircraft engine
run-to-failure simulation", PHM'08. Public domain, NASA Prognostics Center of Excellence.
"""
from __future__ import annotations

import io
import urllib.request
import zipfile
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import RAW_DIR

URL = "https://phm-datasets.s3.amazonaws.com/NASA/6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip"
DIR = RAW_DIR / "cmapss"
SUBSETS = ("FD001", "FD002", "FD003", "FD004")

SETTINGS = ["setting1", "setting2", "setting3"]
SENSORS = ["T2", "T24", "T30", "T50", "P2", "P15", "P30", "Nf", "Nc", "epr", "Ps30", "phi",
           "NRf", "NRc", "BPR", "farB", "htBleed", "Nf_dmd", "PCNfR_dmd", "W31", "W32"]
COLUMNS = ["unit", "cycle"] + SETTINGS + SENSORS

# Sensor -> engine module, used to turn SHAP attributions into "where is the degradation".
SENSOR_MODULE = {
    "T2": "Inlet", "P2": "Inlet",
    "P15": "Fan", "Nf": "Fan", "NRf": "Fan", "BPR": "Fan", "Nf_dmd": "Fan", "PCNfR_dmd": "Fan",
    "T24": "LPC",
    "T30": "HPC", "P30": "HPC", "Ps30": "HPC", "Nc": "HPC", "NRc": "HPC", "phi": "HPC",
    "farB": "Combustor/HPT", "htBleed": "Combustor/HPT", "W31": "Combustor/HPT",
    "T50": "LPT", "W32": "LPT", "epr": "Overall",
}


def ensure_downloaded() -> Path:
    if (DIR / "train_FD001.txt").exists():
        return DIR
    DIR.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(URL, timeout=300) as r:
        outer = zipfile.ZipFile(io.BytesIO(r.read()))
    inner_name = next(n for n in outer.namelist() if n.endswith("CMAPSSData.zip"))
    zipfile.ZipFile(io.BytesIO(outer.read(inner_name))).extractall(DIR)
    return DIR


def _read(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=r"\s+", header=None)
    df = df.iloc[:, : len(COLUMNS)]
    df.columns = COLUMNS
    return df


@lru_cache(maxsize=1)
def load_train() -> pd.DataFrame:
    """All run-to-failure training trajectories, with a global ``uid`` and true RUL."""
    ensure_downloaded()
    parts = []
    for fd in SUBSETS:
        df = _read(DIR / f"train_{fd}.txt")
        df["subset"] = fd
        df["uid"] = fd + "-" + df["unit"].astype(str)
        df["life"] = df.groupby("uid")["cycle"].transform("max")
        df["rul"] = df["life"] - df["cycle"]
        parts.append(df)
    return pd.concat(parts, ignore_index=True)


@lru_cache(maxsize=1)
def load_test() -> pd.DataFrame:
    """Official test trajectories (truncated) with the true RUL at the last cycle."""
    ensure_downloaded()
    parts = []
    for fd in SUBSETS:
        df = _read(DIR / f"test_{fd}.txt")
        rul = pd.read_csv(DIR / f"RUL_{fd}.txt", header=None).iloc[:, 0].to_numpy()
        df["subset"] = fd
        df["uid"] = fd + "-T" + df["unit"].astype(str)
        last = df.groupby("unit")["cycle"].transform("max")
        df["rul"] = rul[df["unit"].to_numpy() - 1] + (last - df["cycle"])
        df["life"] = df["cycle"] + df["rul"]
        parts.append(df)
    return pd.concat(parts, ignore_index=True)


def split_units(seed: int = 7) -> dict[str, list[str]]:
    """Deterministic unit split of the training trajectories.

    * ``train`` (60 %) fits the RUL model,
    * ``cal`` (20 %) calibrates conformal intervals,
    * ``fleet`` (20 %) backs the engines of the synthetic fleet, so the model never saw them.
    """
    uids = load_train()[["uid", "subset"]].drop_duplicates()
    rng = np.random.default_rng(seed)
    out = {"train": [], "cal": [], "fleet": []}
    for _, g in uids.groupby("subset"):
        u = g["uid"].to_numpy().copy()
        rng.shuffle(u)
        n = len(u)
        a, b = int(0.6 * n), int(0.8 * n)
        out["train"] += list(u[:a])
        out["cal"] += list(u[a:b])
        out["fleet"] += list(u[b:])
    return out


def unit_lives() -> pd.Series:
    df = load_train()
    return df.groupby("uid")["life"].first()
