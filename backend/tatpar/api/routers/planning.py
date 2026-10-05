"""Readiness forecast, flight & maintenance plan, requirement planner, levers and loss waterfall."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from ...optimize.fmp import Requirement, phase_ladder, plan_fleet
from ...optimize.requirement import plan_requirement
from ...twin.montecarlo import forecast
from ...twin.policies import BASELINE, TATPAR
from ...twin.state import SQN_IDS
from ...trust import audit, records
from ...trust.auth import User
from ..context import get_ctx
from ..security import check, current_user

router = APIRouter(prefix="/api", tags=["planning"])


@router.get("/forecast")
def get_forecast():
    return get_ctx().bench("forecast")


class ForecastReq(BaseModel):
    policy: str = Field("baseline", pattern="^(baseline|tatpar)$")
    days: int = Field(60, ge=7, le=120)
    reps: int = Field(80, ge=10, le=300)


@router.post("/forecast/run")
def run_forecast(req: ForecastReq):
    ctx = get_ctx()
    nff = ctx.metrics["nff"]
    pol = BASELINE if req.policy == "baseline" else TATPAR.with_(risk_fn=ctx.belief.risk_fn, nff_tpr=nff["tpr"], nff_fpr=nff["fpr"])
    f = forecast(ctx.state, pol, req.days, req.reps, ctx.belief)
    return {"fleet": f.bands(), "squadrons": {q: f.bands(k) for k, q in enumerate(SQN_IDS)},
            "state_share": f.state_share(), "mc_rate": f.mc_rate(), "reps": req.reps, "days": req.days}


@router.get("/plan")
def get_plan():
    ctx = get_ctx()
    return {"plan": ctx.bench("plan"), "ladder": ctx.bench("ladder")}


class PlanReq(BaseModel):
    horizon: int = Field(30, ge=7, le=45)
    sqn: str | None = None
    start: int | None = None
    end: int | None = None
    min_capable: int | None = None

    @field_validator("sqn")
    @classmethod
    def _known_sqn(cls, v):
        return _known(v) if v else v


def _known(sqn: str) -> str:
    if sqn not in SQN_IDS:
        raise ValueError(f"unknown squadron {sqn!r}; expected one of {', '.join(SQN_IDS)}")
    return sqn


@router.post("/plan/run")
def run_plan(req: PlanReq):
    ctx = get_ctx()
    r = None
    if req.sqn and req.min_capable is not None and req.start is not None and req.end is not None:
        r = Requirement(SQN_IDS.index(req.sqn), req.start, req.end, req.min_capable)
    p = plan_fleet(ctx.state, req.horizon, ctx.belief, r, time_limit=5.0)
    return {"plan": p, "ladder": {"now": phase_ladder(ctx.state)}}


@router.get("/requirement/demo")
def requirement_demo():
    return get_ctx().bench("requirement_demo")


class RequirementReq(BaseModel):
    sqn: str = "SQN-A"
    start: int = Field(14, ge=0, le=40)
    end: int = Field(17, ge=0, le=45)
    min_mc: int = Field(9, ge=1, le=16)
    surge: float = Field(1.2, ge=0.5, le=2.0)
    reps: int = Field(80, ge=20, le=200)

    @field_validator("sqn")
    @classmethod
    def _known_sqn(cls, v):
        return _known(v)


@router.post("/requirement")
def run_requirement(req: RequirementReq):
    ctx = get_ctx()
    nff = ctx.metrics["nff"]
    end = max(req.end, req.start)
    return plan_requirement(ctx.state, ctx.belief, SQN_IDS.index(req.sqn), req.start, end, req.min_mc, req.surge,
                            req.reps, nff["tpr"], nff["fpr"])


class Approval(BaseModel):
    kind: str = Field(..., pattern="^[a-z_]{3,40}$")
    summary: str = Field(..., max_length=500)
    payload: dict = {}
    decision: str = Field("approved", pattern="^(approved|rejected|deferred)$")
    persona: str | None = None   # ignored: the ledger records the signed-in identity


@router.post("/approve")
def approve(a: Approval, user: User = Depends(current_user)):
    check(user, f"approve:{a.kind}" if f"approve:{a.kind}" in _APPROVALS else "approve:readiness_plan")
    e = audit.append(a.kind, user.role, a.summary, a.payload, a.decision, user=user.id)
    if a.kind == "readiness_plan" and a.decision == "approved" and isinstance(a.payload.get("orders"), list):
        e = {**e, "orders": records.issue(a.payload["orders"], e["seq"], user.role)}
    return e


@router.get("/orders")
def get_orders():
    os_ = sorted(records.orders(), key=lambda o: o["id"], reverse=True)
    return {"orders": os_[:200], "outstanding": sum(o["status"] == "ISSUED" for o in os_),
            "actioned": sum(o["status"] == "ACTIONED" for o in os_)}


class OrderUpdate(BaseModel):
    status: str = Field(..., pattern="^(ISSUED|ACTIONED|CANCELLED)$")
    note: str = Field("", max_length=200)


@router.post("/orders/{oid}")
def update_order(oid: str, body: OrderUpdate, user: User = Depends(current_user)):
    check(user, "order:update")
    o = next((x for x in records.orders() if x["id"] == oid), None)
    if o is None:
        raise HTTPException(404, f"no order {oid}")
    if user.role not in (o["owner"], "STN CDR"):
        raise HTTPException(403, f"{oid} belongs to {o['owner']}; only {o['owner']} or STN CDR may update it")
    o = records.set_status(oid, body.status, user.role, body.note)
    audit.append("order_update", user.role, f"{oid} {body.status}: {o['text']}", {"order": oid, "note": body.note},
                 "approved", user=user.id)
    return o


_APPROVALS = {"approve:readiness_plan", "approve:daily_signal"}


@router.get("/audit")
def get_audit():
    return {"entries": audit.read()[-200:], "verify": audit.verify()}


@router.get("/levers")
def levers():
    return get_ctx().bench("levers")


@router.get("/waterfall")
def waterfall():
    return get_ctx().bench("waterfall")


@router.get("/sensitivity")
def sensitivity():
    return get_ctx().bench("sensitivity")
