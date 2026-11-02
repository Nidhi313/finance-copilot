"""Command-line jobs.

python -m app.cli seed                    load countries, categories, launch packs
python -m app.cli fx-refresh [days]       fetch exchange rates for the last N days (default 7)
python -m app.cli list-users              show users and how many accounts each has
python -m app.cli demo-data [email]       add sample data (no email: the local demo user)
python -m app.cli clear-data <email>      remove a user's accounts and records, keep the user
"""

import sys

from sqlalchemy import func, select

from app.db import SessionLocal
from app.demo import DemoError, clear_user_data, load_demo_data
from app.models import Account, User
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
        elif argv[0] == "list-users":
            rows = db.execute(
                select(User.email, User.created_at, func.count(Account.id))
                .outerjoin(Account, Account.user_id == User.id)
                .group_by(User.id)
                .order_by(User.created_at)
            ).all()
            for email, created, n in rows:
                print(f"{email or '(no email)':40} accounts: {n:3}  since {created:%Y-%m-%d}")
            if not rows:
                print("No users yet.")
        elif argv[0] in ("demo-data", "clear-data"):
            email = argv[1] if len(argv) > 1 else None
            try:
                if argv[0] == "demo-data":
                    print(load_demo_data(db, email))
                elif email:
                    print(clear_user_data(db, email))
                else:
                    print("clear-data needs an email")
                    return 1
            except DemoError as e:
                print(e, file=sys.stderr)
                return 1
        else:
            print(__doc__)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
