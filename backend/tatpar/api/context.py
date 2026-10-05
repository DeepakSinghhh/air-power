"""Shared application context: the "today" twin state, models and cached benchmark results."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cached_property

import numpy as np
import pandas as pd

from ..config import ARTIFACTS_DIR
from ..datagen import history
from ..nlp.snags import SnagNLP
from ..prognostics.belief import Belief
from ..prognostics.engine_rul import EngineRUL
from ..prognostics.leaks import NFFModel
from ..twin.simulator import day_to_date
from ..twin.state import FleetState

BENCH = ARTIFACTS_DIR / "bench"


@dataclass
class Context:
    state: FleetState
    belief: Belief
    rul: EngineRUL
    nff: NFFModel
    nlp: SnagNLP
    metrics: dict
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Context":
        ctx = cls(
            state=history.load_state(), belief=Belief.load(), rul=EngineRUL.load(), nff=NFFModel.load(),
            nlp=SnagNLP.load(), metrics=json.loads((ARTIFACTS_DIR / "metrics.json").read_text()),
        )
        for name in ("tails", "snags", "removals", "checks", "status", "sorties", "supply", "cann", "repairs",
                     "positions", "engines", "stock"):
            ctx.tables[name] = history.load(name)
        for name in ("rogue_units", "chronic_defects"):
            p = ARTIFACTS_DIR / f"{name}.parquet"
            ctx.tables[name] = pd.read_parquet(p) if p.exists() else pd.DataFrame()
        from ..ingest.apply import replay

        replay(ctx)             # data imported from units since the last build
        return ctx

    def refresh(self) -> None:
        """Drop cached risk after an import changed the state or the beliefs."""
        for k in ("risk7", "risk30"):
            self.__dict__.pop(k, None)

    @property
    def today(self) -> str:
        return str(day_to_date(self.state.day))

    def bench(self, name: str):
        p = BENCH / f"{name}.json"
        return json.loads(p.read_text()) if p.exists() else None

    @cached_property
    def risk7(self) -> np.ndarray:
        return self.belief.risk_fn(self.state, 7)

    @cached_property
    def risk30(self) -> np.ndarray:
        return self.belief.risk_fn(self.state, 30)


_CTX: Context | None = None


def get_ctx() -> Context:
    global _CTX
    if _CTX is None:
        _CTX = Context.load()
    return _CTX


def reload() -> None:
    """Forget the loaded context; the next request rebuilds it from disk."""
    global _CTX
    _CTX = None
