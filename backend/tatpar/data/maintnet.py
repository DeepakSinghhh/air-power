"""MaintNet aviation maintenance logbook (Akhbardeh et al., COLING 2020).

6,169 de-identified problem/action records from a university flight-training fleet, plus an
aviation abbreviation list. Used for real-text similar-case retrieval and weakly-labelled ATA
coding. Source: https://people.rit.edu/fa3019/MaintNet/
"""
from __future__ import annotations

import shutil
import urllib.request
from functools import lru_cache

import pandas as pd

from ..config import RAW_DIR, REPO_DIR

BASE = "https://people.rit.edu/fa3019/technical/data/"
FILES = {"logbook": "maintnet_aviation_dataset_deidentified.csv", "abbrev": "aviation_abbriviation.csv"}
DIR = RAW_DIR / "maintnet"
VENDORED = REPO_DIR / "data" / "vendor" / "maintnet"     # shipped copy (CC BY-SA 4.0), used first


def ensure_downloaded() -> bool:
    DIR.mkdir(parents=True, exist_ok=True)
    ok = True
    for f in FILES.values():
        p = DIR / f
        if p.exists():
            continue
        if (VENDORED / f).exists():
            shutil.copyfile(VENDORED / f, p)
            continue
        try:
            with urllib.request.urlopen(BASE + f, timeout=60) as r:
                p.write_bytes(r.read())
        except Exception:  # offline: retrieval falls back to fleet history only
            ok = False
    return ok


@lru_cache(maxsize=1)
def load_logbook() -> pd.DataFrame:
    ensure_downloaded()
    p = DIR / FILES["logbook"]
    if not p.exists():
        return pd.DataFrame(columns=["ident", "problem", "action"])
    df = pd.read_csv(p, encoding="utf-8-sig")
    df.columns = [c.strip().lower() for c in df.columns]
    df = df.rename(columns={"ident": "ident"}).dropna(subset=["problem"])
    df["action"] = df["action"].fillna("")
    return df[["ident", "problem", "action"]].reset_index(drop=True)


@lru_cache(maxsize=1)
def load_abbreviations() -> dict[str, str]:
    ensure_downloaded()
    p = DIR / FILES["abbrev"]
    if not p.exists():
        return {}
    df = pd.read_csv(p, encoding="utf-8-sig")
    return {str(a).strip().lower(): str(b).strip().lower() for a, b in zip(df.iloc[:, 1], df.iloc[:, 2])}
