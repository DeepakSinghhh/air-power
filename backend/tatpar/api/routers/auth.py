"""Sign-in endpoints (the only API routes that do not need a token, with /api/health)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...trust.auth import DEMO_USERS, User, roster
from ..security import current_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Login(BaseModel):
    id: str = Field(..., max_length=64)
    pin: str = Field(..., max_length=64)


@router.get("/roster")
def get_roster():
    r = roster()
    pins = {uid: pin for uid, _, _, pin in DEMO_USERS} if r.demo else {}
    return {"users": [{**u, **({"demo_pin": pins[u["id"]]} if u["id"] in pins else {})} for u in r.users()], "demo": r.demo}


@router.post("/login")
def login(body: Login):
    r = roster()
    try:
        user = r.authenticate(body.id, body.pin)
    except PermissionError as e:
        raise HTTPException(429 if str(e) == "locked" else 401, "too many attempts — wait 5 minutes" if str(e) == "locked" else "wrong ID or PIN") from None
    return {"token": r.issue(user), "user": user.public()}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user.public()
