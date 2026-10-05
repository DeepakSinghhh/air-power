"""Base Environmental Severity Index.

Dust comes from real CAMS reanalysis (2024, via the Open-Meteo Air-Quality API, cached in
``data/env/cams_dust_2024.json``). Heat, humidity, altitude and salt exposure come from
approximate climatological normals in the catalogue. Each LRU type has AFT coefficients
(``LRUType.sens``); its life is consumed ``exp(sum(b_k * x_k))`` times faster than at a
benign reference base.
"""
from __future__ import annotations

import json
from functools import lru_cache
from math import exp, log1p

import numpy as np

from ..config import ENV_DIR
from .catalog import BASES, LRUType

FEATURES = ("dust", "heat", "hum", "alt", "salt")

# Fallback annual mean dust (µg/m³) if the cached CAMS file is missing.
_FALLBACK_DUST = {"jodhpur": 84.7, "pune": 9.9, "tezpur": 5.0, "thanjavur": 2.9, "leh": 13.4}


@lru_cache(maxsize=1)
def _cams() -> dict:
    path = ENV_DIR / "cams_dust_2024.json"
    if path.exists():
        return json.loads(path.read_text())["bases"]
    return {k: {"dust_mean": v, "dust_monthly_mean": [v] * 12} for k, v in _FALLBACK_DUST.items()}


def dust_index(dust_ugm3: float) -> float:
    return log1p(dust_ugm3 / 20.0)


@lru_cache(maxsize=None)
def base_features(base_id: str, month: int | None = None) -> dict[str, float]:
    """Severity features for a base; ``month`` (1-12) selects the seasonal dust value."""
    b = BASES[base_id]
    cams = _cams()[base_id]
    dust = cams["dust_mean"] if month is None else cams["dust_monthly_mean"][month - 1]
    return {
        "dust": dust_index(dust),
        "heat": max(0.0, (b.tmax_annual_c - 28.0) / 5.0),
        "hum": max(0.0, (b.rh_annual_pct - 50.0) / 25.0),
        "alt": b.elevation_m / 3000.0,
        "salt": b.coastal,
    }


def severity_multiplier(lru: LRUType, base_id: str, g_sev: float = 1.0, month: int | None = None) -> float:
    """Life-consumption rate relative to a benign reference (1.0)."""
    f = base_features(base_id, month)
    s = sum(lru.sens[k] * f[k] for k in FEATURES) + lru.sens["g"] * (g_sev - 1.0)
    return exp(s)


def monthly_multiplier_table(lru_types: list[LRUType], base_ids: list[str]) -> np.ndarray:
    """Array [month(0..11), base, lru] of environment-only multipliers (g handled separately)."""
    out = np.zeros((12, len(base_ids), len(lru_types)))
    for m in range(12):
        for bi, b in enumerate(base_ids):
            f = base_features(b, m + 1)
            for li, l in enumerate(lru_types):
                out[m, bi, li] = exp(sum(l.sens[k] * f[k] for k in FEATURES))
    return out


def base_table() -> list[dict]:
    """Per-base summary for the UI / docs."""
    rows = []
    for bid, b in BASES.items():
        f = base_features(bid)
        cams = _cams()[bid]
        rows.append({
            "base": bid, "name": b.name, "lat": b.lat, "lon": b.lon, "elevation_m": b.elevation_m,
            "climate": b.climate, "dust_ugm3": round(cams["dust_mean"], 1),
            "dust_monthly": cams["dust_monthly_mean"], **{k: round(v, 3) for k, v in f.items()},
            # composite index: mean multiplier across a generic sensitivity profile
            "severity_index": round(exp(0.25 * f["dust"] + 0.15 * f["heat"] + 0.12 * f["hum"]
                                        + 0.1 * f["alt"] + 0.1 * f["salt"]), 3),
        })
    return rows
