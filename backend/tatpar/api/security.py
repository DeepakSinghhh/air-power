"""FastAPI dependencies for sign-in and role checks (see ``tatpar.trust.auth``)."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException

from ..trust.auth import PERMISSIONS, User, roster


def current_user(authorization: str | None = Header(None)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "sign in required", headers={"WWW-Authenticate": "Bearer"})
    try:
        return roster().verify(authorization[7:].strip())
    except PermissionError as e:
        raise HTTPException(401, f"session invalid: {e}", headers={"WWW-Authenticate": "Bearer"}) from None


def check(user: User, perm: str) -> None:
    if not user.can(perm):
        raise HTTPException(403, f"{user.role} may not {perm.replace(':', ' ')}; requires {' / '.join(sorted(PERMISSIONS.get(perm, {'STN CDR'})))}")


def require(perm: str):
    def dep(user: User = Depends(current_user)) -> User:
        check(user, perm)
        return user
    return dep
