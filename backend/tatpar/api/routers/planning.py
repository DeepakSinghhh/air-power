"""Readiness forecast, flight & maintenance plan, requirement planner, levers and loss waterfall."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ...optimize.fmp import Requirement, phase_ladder, plan_fleet
from ...optimize.requirement import plan_requirement
from ...twin.montecarlo import forecast
from ...twin.policies import BASELINE, TATPAR
from ...twin.state import SQN_IDS
from ...trust import audit
from ..context import get_ctx

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


@router.post("/requirement")
def run_requirement(req: RequirementReq):
    ctx = get_ctx()
    nff = ctx.metrics["nff"]
    end = max(req.end, req.start)
    return plan_requirement(ctx.state, ctx.belief, SQN_IDS.index(req.sqn), req.start, end, req.min_mc, req.surge,
                            req.reps, nff["tpr"], nff["fpr"])


class Approval(BaseModel):
    persona: str
    kind: str
    summary: str
    payload: dict = {}
    decision: str = Field("approved", pattern="^(approved|rejected|deferred)$")


@router.post("/approve")
def approve(a: Approval):
    return audit.append(a.kind, a.persona, a.summary, a.payload, a.decision)


@router.get("/audit")
def get_audit():
    return {"entries": audit.read()[-200:], "verify": audit.verify()}


@router.get("/levers")
def levers():
    return get_ctx().bench("levers")


@router.get("/waterfall")
def waterfall():
    return get_ctx().bench("waterfall")
