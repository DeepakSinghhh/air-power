"""Hash-chained, append-only audit log of recommendations and human decisions.

Each entry stores the SHA-256 of (previous hash + canonical JSON of the entry), so any edit to an
earlier record breaks verification. Each hash is also signed with the server key (HMAC-SHA256,
``TATPAR_SECRET`` or ``artifacts/secret.key``), so rebuilding the whole chain after an edit is caught
too unless the key is stolen. In service this would be the unit's PKI key in an HSM.
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
    return json.dumps({k: entry[k] for k in sorted(entry) if k not in ("hash", "sig")}, sort_keys=True, default=str)


def _sign(h: str) -> str:
    from .auth import sign
    return sign(h.encode())


def read() -> list[dict]:
    if not LOG.exists():
        return []
    return [json.loads(l) for l in LOG.read_text().splitlines() if l.strip()]


def append(kind: str, persona: str, summary: str, payload: dict | None = None, decision: str = "approved",
           user: str | None = None) -> dict:
    with _lock:
        entries = read()
        prev = entries[-1]["hash"] if entries else GENESIS
        e = {"seq": len(entries) + 1, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "kind": kind, "persona": persona, "decision": decision, "summary": summary,
             "payload": payload or {}, "prev": prev}
        if user:
            e["user"] = user
        e["hash"] = hashlib.sha256((prev + _canon(e)).encode()).hexdigest()
        e["sig"] = _sign(e["hash"])
        with LOG.open("a") as f:
            f.write(json.dumps(e, default=str) + "\n")
        return e


def verify() -> dict:
    entries = read()
    prev = GENESIS
    signed = 0
    for e in entries:
        h = hashlib.sha256((prev + _canon(e)).encode()).hexdigest()
        if e["prev"] != prev or e["hash"] != h:
            return {"ok": False, "entries": len(entries), "broken_at": e["seq"]}
        if "sig" in e:
            if e["sig"] != _sign(h):
                return {"ok": False, "entries": len(entries), "broken_at": e["seq"], "reason": "signature"}
            signed += 1
        prev = e["hash"]
    return {"ok": True, "entries": len(entries), "head": prev, "signed": signed}
