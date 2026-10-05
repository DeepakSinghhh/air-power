"""Hash-chained, append-only audit log of recommendations and human decisions.

Each entry stores the SHA-256 of (previous hash + canonical JSON of the entry), so any edit to an
earlier record breaks verification. In production the chain head would be countersigned with the
unit's PKI key; here verification is local.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone

from ..config import ARTIFACTS_DIR

LOG = ARTIFACTS_DIR / "audit_log.jsonl"
GENESIS = "0" * 64
_lock = threading.Lock()


def _canon(entry: dict) -> str:
    return json.dumps({k: entry[k] for k in sorted(entry) if k != "hash"}, sort_keys=True, default=str)


def read() -> list[dict]:
    if not LOG.exists():
        return []
    return [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()]


def append(kind: str, persona: str, summary: str, payload: dict | None = None, decision: str = "approved") -> dict:
    with _lock:
        entries = read()
        prev = entries[-1]["hash"] if entries else GENESIS
        e = {"seq": len(entries) + 1, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "kind": kind, "persona": persona, "decision": decision, "summary": summary,
             "payload": payload or {}, "prev": prev}
        e["hash"] = hashlib.sha256((prev + _canon(e)).encode()).hexdigest()
        with LOG.open("a") as f:
            f.write(json.dumps(e, default=str) + "\n")
        return e


def verify() -> dict:
    entries = read()
    prev = GENESIS
    for e in entries:
        h = hashlib.sha256((prev + _canon(e)).encode()).hexdigest()
        if e["prev"] != prev or e["hash"] != h:
            return {"ok": False, "entries": len(entries), "broken_at": e["seq"]}
        prev = e["hash"]
    return {"ok": True, "entries": len(entries), "head": prev}
