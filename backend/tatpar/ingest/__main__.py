"""Data-fabric housekeeping.

    python -m tatpar.ingest reset      # remove every import (and imported tech-log entries)
    python -m tatpar.ingest samples    # write data/samples/*.csv from the current fleet register
    python -m tatpar.ingest docs       # write docs/05-data-contracts.md from the contracts
"""
from __future__ import annotations

import sys

from ..config import REPO_DIR


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else ""
    if cmd == "reset":
        from . import store
        from ..trust import records

        print(f"removed {store.clear()} imports and {records.remove_imported_snags()} imported tech-log entries "
              "(restart the server to reload the generated state)")
    elif cmd == "samples":
        from ..api.context import Context
        from .samples import write_samples

        print("wrote", write_samples(Context.load(), REPO_DIR / "data" / "samples"))
    elif cmd == "docs":
        from .contracts import markdown

        (REPO_DIR / "docs" / "05-data-contracts.md").write_text(markdown())
        print("wrote docs/05-data-contracts.md")
    else:
        print(__doc__)


main(sys.argv[1:])
