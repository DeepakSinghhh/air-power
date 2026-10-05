"""Data fabric: contracts, validation and import of unit data (HUMS, tech log, IMMOLS stock, BRD/HAL repairs)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse

from ...ingest import store
from ...ingest.apply import ingest, reset
from ...ingest.contracts import CONTRACTS
from ...ingest.samples import sample, template
from ...trust.auth import User
from ..context import get_ctx
from ..security import check, current_user, require

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


def _contract(source: str):
    if source not in CONTRACTS:
        raise HTTPException(404, f"unknown source {source!r}; expected one of {', '.join(CONTRACTS)}")
    return CONTRACTS[source]


@router.get("/contracts")
def contracts():
    return [{"source": c.source, "title": c.title, "system": c.system, "entity": c.entity, "applies": c.applies,
             "validate_only": c.validate_only, "key": list(c.key), "notes": list(c.notes),
             "fields": [{"name": f.name, "type": f.type, "unit": f.unit, "required": f.required, "lo": f.lo, "hi": f.hi,
                         "values": list(f.values), "doc": f.doc} for f in c.fields]}
            for c in CONTRACTS.values()]


@router.get("/template/{source}", response_class=PlainTextResponse)
def get_template(source: str, sample_rows: bool = Query(False, alias="sample")):
    _contract(source)
    df = sample(get_ctx(), source) if sample_rows else template(source)
    return PlainTextResponse(df.to_csv(index=False), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="tatpar_{source}{"_sample" if sample_rows else ""}.csv"'})


@router.get("/lineage")
def lineage():
    return list(reversed(store.lineage()))


@router.get("/stamp")
def stamp():
    """Cheap poll: changes whenever data is imported (boards refetch when it does)."""
    lin = store.lineage()
    return {"seq": len(lin), "last": lin[-1] if lin else None}


@router.post("/reset")
def reset_imports(user: User = Depends(require("data:reset"))):
    from ...trust import audit

    out = reset()
    audit.append("data_reset", user.role, f"Removed {out['imports_removed']} data imports", out, user=user.id)
    return out


@router.post("/{source}/validate")
async def validate_upload(source: str, file: UploadFile = File(...), user: User = Depends(current_user)):
    _contract(source)
    return ingest(get_ctx(), source, await file.read(), file.filename or "upload.csv", user, dry_run=True)


@router.post("/{source}")
async def import_upload(source: str, file: UploadFile = File(...), replace: bool = False,
                        user: User = Depends(current_user)):
    c = _contract(source)
    if c.validate_only:
        raise HTTPException(422, f"{c.title} is validate-only in this prototype: {c.applies}")
    check(user, f"data:import:{source}")
    return ingest(get_ctx(), source, await file.read(), file.filename or "upload.csv", user, replace=replace)
