"""End-to-end build: data -> history -> models -> belief -> metrics.

    python -m tatpar.pipelines.build_all            # everything (≈2 min on a laptop)
    python -m tatpar.pipelines.build_all --skip-rul # reuse a trained engine model
"""
from __future__ import annotations

import argparse
import json
import time

from ..config import ARTIFACTS_DIR
from ..data import cmapss
from ..datagen import history
from ..prognostics.belief import Belief
from ..prognostics.engine_rul import MODEL_PATH as RUL_PATH, EngineRUL
from ..prognostics.leaks import NFFModel, chronic_defects, rogue_metrics, rogue_units
from ..prognostics.survival import SurvivalModels
from ..data import maintnet
from ..nlp.snags import SnagNLP

METRICS_PATH = ARTIFACTS_DIR / "metrics.json"


def build(skip_rul: bool = False) -> dict:
    t0 = time.time()
    cmapss.ensure_downloaded()
    history.generate()
    if skip_rul and RUL_PATH.exists():
        rul = EngineRUL.load()
    else:
        rul = EngineRUL().fit()
        rul.save()
    surv = SurvivalModels().fit(verbose=False)
    rogue = rogue_units(surv)
    # refit reliability without the flagged rogue serials (they get their own risk multiplier)
    surv = SurvivalModels().fit(exclude_serials=set(rogue.loc[rogue["flag"], "serial"]))
    surv.save()
    nff = NFFModel().fit()
    nff.save()
    rogue.to_parquet(ARTIFACTS_DIR / "rogue_units.parquet", index=False)
    chronic = chronic_defects()
    chronic.to_parquet(ARTIFACTS_DIR / "chronic_defects.parquet", index=False)
    belief = Belief.build(surv, rul, set(rogue.loc[rogue["flag"], "serial"]))
    belief.save()
    maintnet.ensure_downloaded()
    nlp = SnagNLP().fit()
    nlp.save()
    metrics = {
        "engine_rul": rul.metrics,
        "survival": {k: v for k, v in surv.metrics.items()},
        "nff": nff.metrics,
        "rogue": rogue_metrics(rogue),
        "chronic_defects": int(len(chronic)),
        "snag_nlp": nlp.metrics,
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=1, default=float))
    print(f"build complete in {time.time() - t0:.0f}s -> {ARTIFACTS_DIR}")
    return metrics


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-rul", action="store_true")
    build(ap.parse_args().skip_rul)
