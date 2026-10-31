"""Command-line jobs.

python -m app.cli seed                 load countries, categories, launch packs
python -m app.cli fx-refresh [days]    fetch exchange rates for the last N days (default 7)
"""

import sys

from app.db import SessionLocal
from app.providers.fx import get_provider
from app.seed import seed
from app.services.fx_ingest import refresh


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    with SessionLocal() as db:
        if argv[0] == "seed":
            print(seed(db))
        elif argv[0] == "fx-refresh":
            days = int(argv[1]) if len(argv) > 1 else 7
            try:
                print({"rates_stored": refresh(db, get_provider(), days)})
            except Exception as e:  # noqa: BLE001
                print(f"FX refresh failed: {e}", file=sys.stderr)
                return 2
        else:
            print(__doc__)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
