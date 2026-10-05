"""Operational records written from the ops room: filed technical-log entries and the orders an
approved plan issues. Both are append-only JSON-lines files; an order's current status is the fold
of its events, so its whole history is kept. Every status change is also written to the
hash-chained decision ledger by the API.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone

from ..config import ARTIFACTS_DIR

FILED = ARTIFACTS_DIR / "filed_snags.jsonl"
ORDERS = ARTIFACTS_DIR / "orders.jsonl"
_lock = threading.Lock()

# who carries out each kind of order
OWNER = {"phase": "SENGO", "engine_protect": "SENGO", "policy": "SENGO", "transfer": "LOG OFFR", "expedite": "DEPOT MGR"}
STATUSES = ("ISSUED", "ACTIONED", "CANCELLED")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _append(path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(obj, default=str) + "\n")


# ------------------------------------------------------------------ technical log
def filed_snags() -> list[dict]:
    return _read(FILED)


def file_snag(entry: dict) -> dict:
    with _lock:
        n = len(_read(FILED)) + 1
        e = {"snag_id": f"TL-{n:04d}", "ts": _now(), "finding": "OPEN", "action": "", **entry}
        _append(FILED, e)
        return e


# ------------------------------------------------------------------ orders
def order_text(d: dict) -> str:
    t = d.get("type")
    if t == "phase":
        return f"PHASE CHECK {d['tail']} AT {d['phase_start']}"
    if t == "engine_protect":
        return f"CAP {d['tail']} FLYING AT ENGINE LOWER BOUND ({str(d.get('reason', '')).upper()})"
    if t == "transfer":
        return f"MOVE {d['qty']}× {str(d['name']).upper()} {str(d['from']).upper()} → {str(d['to']).upper()}"
    if t == "expedite":
        return f"EXPEDITE {str(d['name']).upper()} S/N {d['serial']} AT {d['agency']}"
    if t == "policy":
        return str(d.get("text", "")).upper()
    raise ValueError(f"unknown order type {t!r}")


def issue(items: list[dict], plan_seq: int, user: str) -> list[dict]:
    with _lock:
        n = len({e["order"]["id"] for e in _read(ORDERS) if e["op"] == "issue"})
        out = []
        for d in items[:60]:
            if d.get("type") not in OWNER:
                continue
            n += 1
            o = {"id": f"ORD-{n:04d}", "type": d["type"], "text": order_text(d), "owner": OWNER[d["type"]],
                 "lever": d.get("lever", ""), "plan_seq": plan_seq, "issued_by": user, "issued": _now()}
            _append(ORDERS, {"op": "issue", "order": o})
            out.append({**o, "status": "ISSUED", "history": []})
        return out


def orders() -> list[dict]:
    cur: dict[str, dict] = {}
    for e in _read(ORDERS):
        if e["op"] == "issue":
            cur[e["order"]["id"]] = {**e["order"], "status": "ISSUED", "history": []}
        elif e["op"] == "status" and e["id"] in cur:
            cur[e["id"]]["status"] = e["status"]
            cur[e["id"]]["history"].append({k: e[k] for k in ("status", "by", "note", "ts")})
    return list(cur.values())


def set_status(oid: str, status: str, by: str, note: str = "") -> dict:
    if status not in STATUSES:
        raise ValueError(status)
    with _lock:
        o = next((x for x in orders() if x["id"] == oid), None)
        if o is None:
            raise KeyError(oid)
        _append(ORDERS, {"op": "status", "id": oid, "status": status, "by": by, "note": note[:200], "ts": _now()})
    return next(x for x in orders() if x["id"] == oid)
