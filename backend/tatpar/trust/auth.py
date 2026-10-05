"""Sign-in and role-based access control.

Users sign in with an ID and PIN and receive a signed, expiring bearer token. Every API call
except ``/api/health`` and ``/api/auth/login`` requires a valid token, and decisions are gated by
role: only the Station Commander approves a readiness plan, only the engineering side files snags,
and the auditor can look and analyse but not decide. The ledger records the *signed-in* identity, never a name the client
claims.

Prototype roster: one notional user per role with a demo PIN (``DEMO_USERS``). For a unit
deployment set ``TATPAR_USERS`` to a JSON file of ``{"id", "name", "role", "salt", "hash"}``
entries (``python -m tatpar.trust.auth hash <pin>`` prints a salt/hash pair) and ``TATPAR_SECRET``
to a long random string.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from dataclasses import dataclass

from ..config import ARTIFACTS_DIR

ROLES = ("STN CDR", "SENGO", "LOG OFFR", "DEPOT MGR", "AUDITOR")
ROLE_TITLE = {"STN CDR": "Station Commander", "SENGO": "Senior Engineering Officer", "LOG OFFR": "Logistics Officer",
              "DEPOT MGR": "Depot Manager", "AUDITOR": "Analyst / Auditor"}

# permission -> roles allowed
PERMISSIONS: dict[str, set[str]] = {
    "approve:readiness_plan": {"STN CDR"},
    "approve:daily_signal": {"STN CDR", "SENGO"},
    "order:update": {"STN CDR", "SENGO", "LOG OFFR", "DEPOT MGR"},
    "snags:file": {"STN CDR", "SENGO"},
    "data:import": {"STN CDR", "SENGO", "LOG OFFR"},           # legacy tech-log CSV import
    "data:import:hums": {"STN CDR", "SENGO"},
    "data:import:snags": {"STN CDR", "SENGO"},
    "data:import:stock": {"STN CDR", "LOG OFFR"},
    "data:import:repairs": {"STN CDR", "LOG OFFR", "DEPOT MGR"},
    "data:reset": {"STN CDR"},
}

# id, display name, role, demo PIN — notional people, prototype only
DEMO_USERS = [
    ("stncdr", "Station Commander (demo)", "STN CDR", "2601"),
    ("sengo", "Senior Engineering Officer (demo)", "SENGO", "2602"),
    ("logoffr", "Logistics Officer (demo)", "LOG OFFR", "2603"),
    ("depotmgr", "Depot Manager (demo)", "DEPOT MGR", "2604"),
    ("auditor", "Analyst / Auditor (demo)", "AUDITOR", "2605"),
]
TOKEN_TTL_S = 12 * 3600
MAX_FAILS, LOCK_S = 5, 300


@dataclass(frozen=True)
class User:
    id: str
    name: str
    role: str

    @property
    def permissions(self) -> list[str]:
        return sorted(p for p, roles in PERMISSIONS.items() if self.role in roles)

    def can(self, perm: str) -> bool:
        return self.role in PERMISSIONS.get(perm, set())

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "role": self.role, "title": ROLE_TITLE.get(self.role, self.role),
                "permissions": self.permissions}


def hash_pin(pin: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 200_000).hex()
    return salt, h


def _secret() -> bytes:
    env = os.environ.get("TATPAR_SECRET")
    if env:
        return env.encode()
    p = ARTIFACTS_DIR / "secret.key"
    if not p.exists():
        ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        p.write_text(secrets.token_hex(32))
        try:
            p.chmod(0o600)
        except OSError:  # pragma: no cover
            pass
    return p.read_text().strip().encode()


def sign(data: bytes) -> str:
    return hmac.new(_secret(), data, hashlib.sha256).hexdigest()


class Roster:
    def __init__(self) -> None:
        self._users: dict[str, tuple[User, str, str]] = {}
        path = os.environ.get("TATPAR_USERS")
        if path:
            for u in json.loads(open(path).read()):
                if u["role"] not in ROLES:
                    raise ValueError(f"unknown role {u['role']!r} for {u['id']}")
                self._users[u["id"]] = (User(u["id"], u["name"], u["role"]), u["salt"], u["hash"])
        else:
            for uid, name, role, pin in DEMO_USERS:
                salt, h = hash_pin(pin, hashlib.sha256(uid.encode()).hexdigest()[:32])
                self._users[uid] = (User(uid, name, role), salt, h)
        self._fails: dict[str, list[float]] = {}

    @property
    def demo(self) -> bool:
        return not os.environ.get("TATPAR_USERS")

    def users(self) -> list[dict]:
        return [{"id": u.id, "name": u.name, "role": u.role} for u, _, _ in self._users.values()]

    def authenticate(self, uid: str, pin: str) -> User:
        now = time.time()
        fails = [t for t in self._fails.get(uid, []) if now - t < LOCK_S]
        if len(fails) >= MAX_FAILS:
            raise PermissionError("locked")
        rec = self._users.get(uid)
        ok = rec is not None and hmac.compare_digest(hash_pin(pin, rec[1])[1], rec[2])
        if not ok:
            self._fails[uid] = fails + [now]
            raise PermissionError("bad credentials")
        self._fails.pop(uid, None)
        return rec[0]

    def issue(self, user: User) -> str:
        body = base64.urlsafe_b64encode(json.dumps({"sub": user.id, "role": user.role, "exp": int(time.time()) + TOKEN_TTL_S}).encode()).decode()
        return f"{body}.{sign(body.encode())}"

    def verify(self, token: str) -> User:
        try:
            body, sig = token.rsplit(".", 1)
        except ValueError:
            raise PermissionError("malformed token") from None
        if not hmac.compare_digest(sig, sign(body.encode())):
            raise PermissionError("bad signature")
        claims = json.loads(base64.urlsafe_b64decode(body.encode()))
        if claims["exp"] < time.time():
            raise PermissionError("expired")
        rec = self._users.get(claims["sub"])
        if rec is None or rec[0].role != claims["role"]:
            raise PermissionError("unknown user")
        return rec[0]


_ROSTER: Roster | None = None


def roster() -> Roster:
    global _ROSTER
    if _ROSTER is None:
        _ROSTER = Roster()
    return _ROSTER


if __name__ == "__main__":  # python -m tatpar.trust.auth hash <pin>
    if len(sys.argv) == 3 and sys.argv[1] == "hash":
        s, h = hash_pin(sys.argv[2])
        print(json.dumps({"salt": s, "hash": h}))
    else:
        print(__doc__)
