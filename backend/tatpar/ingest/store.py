"""Where imported data lives: an append-only lineage log, the accepted rows of every import, and
each engine's uploaded HUMS history. Kept apart from the generated history so a reset is clean."""
from __future__ import annotations

import json
import shutil
import threading
from datetime import datetime, timezone

import pandas as pd

from ..config import ARTIFACTS_DIR

DIR = ARTIFACTS_DIR / "ingest"
_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def lineage() -> list[dict]:
    p = DIR / "lineage.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def record(source: str, file: str, sha256: str, report: dict, result: dict, user: str, role: str,
           accepted: pd.DataFrame) -> dict:
    """Append one import to the lineage log and keep its accepted rows (replayed when the server restarts)."""
    with _lock:
        DIR.mkdir(parents=True, exist_ok=True)
        seq = len(lineage()) + 1
        e = {"seq": seq, "ts": _now(), "source": source, "file": file, "sha256": sha256,
             "rows": report["rows"], "accepted": report["accepted"], "rejected": report["rejected"],
             "user": user, "role": role, "summary": result.get("summary", "")}
        (DIR / "batches").mkdir(exist_ok=True)
        accepted.to_csv(DIR / "batches" / f"{seq:05d}_{source}.csv", index=False)
        with (DIR / "lineage.jsonl").open("a") as f:
            f.write(json.dumps(e) + "\n")
        return e


def batch(seq: int, source: str) -> pd.DataFrame:
    return pd.read_csv(DIR / "batches" / f"{seq:05d}_{source}.csv")


# ------------------------------------------------------------------ HUMS histories and current intervals
def hums_history(serial: int) -> pd.DataFrame | None:
    p = DIR / "hums" / f"{serial}.csv"
    return pd.read_csv(p) if p.exists() else None


def save_hums_history(serial: int, df: pd.DataFrame) -> None:
    (DIR / "hums").mkdir(parents=True, exist_ok=True)
    df.to_csv(DIR / "hums" / f"{serial}.csv", index=False)


def hums_overrides() -> dict[int, dict]:
    p = DIR / "hums_overrides.json"
    return {int(k): v for k, v in json.loads(p.read_text()).items()} if p.exists() else {}


def save_hums_overrides(o: dict[int, dict]) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / "hums_overrides.json").write_text(json.dumps({str(k): v for k, v in o.items()}, indent=1))


def clear() -> int:
    """Remove every import. Returns how many imports were removed."""
    with _lock:
        n = len(lineage())
        if DIR.exists():
            shutil.rmtree(DIR)
        return n
