"""Paths and global settings."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

DATA_DIR = Path(os.environ.get("TATPAR_DATA_DIR", REPO_DIR / "data"))
RAW_DIR = DATA_DIR / "raw"          # downloaded public datasets (gitignored)
ENV_DIR = DATA_DIR / "env"          # cached environment data (committed)
ARTIFACTS_DIR = Path(os.environ.get("TATPAR_ARTIFACTS_DIR", BACKEND_DIR / "artifacts"))

# Synthetic-world settings
SEED = int(os.environ.get("TATPAR_SEED", "2026"))
HISTORY_DAYS = 730                   # two years of generated history
HISTORY_START = "2024-10-01"         # day 0 of history; "today" = start + HISTORY_DAYS

# One C-MAPSS cycle is mapped to this many flight hours (notional).
FH_PER_CYCLE = 3.0

for _d in (RAW_DIR, ARTIFACTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
