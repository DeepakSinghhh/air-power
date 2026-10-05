"""TATPAR API.  Run:  uvicorn tatpar.api.main:app --port 8000"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..config import REPO_DIR
from .context import get_ctx
from .routers import fleet, intel, logistics, planning

app = FastAPI(title="TATPAR — Readiness Assurance API", version="0.1.0",
              description="SIH 2026 PS 26249. Notional fleet data; not IAF data.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
for r in (fleet.router, planning.router, logistics.router, intel.router):
    app.include_router(r)

try:
    from .routers import copilot  # noqa: E402

    app.include_router(copilot.router)
except ImportError:  # pragma: no cover
    pass


@app.on_event("startup")
def _warm() -> None:
    get_ctx()


@app.get("/api/health")
def health():
    ctx = get_ctx()
    return {"ok": True, "today": ctx.today, "tails": ctx.state.n_tails}


DIST = Path(REPO_DIR / "frontend" / "dist")
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")
