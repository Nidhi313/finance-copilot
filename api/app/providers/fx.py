"""Exchange-rate providers. Each provider is a plugin behind one small interface,
so switching or adding a provider never touches the rest of the app."""

from datetime import date
from decimal import Decimal
from typing import Protocol

import httpx

from app.config import settings


class FxProvider(Protocol):
    name: str

    def rates_per_usd(self, start: date, end: date) -> dict[date, dict[str, Decimal]]:
        """Units of each currency per 1 USD, for every date the provider has in the range."""
        ...


class FrankfurterProvider:
    """Frankfurter v2 (https://frankfurter.dev): free, no key, blends central bank
    reference rates. Returns a list of {date, base, quote, rate}."""

    name = "frankfurter"

    def __init__(self, base_url: str | None = None, client: httpx.Client | None = None):
        self.base_url = (base_url or settings.fx_base_url).rstrip("/")
        self.client = client or httpx.Client(timeout=settings.fx_timeout_seconds)

    def rates_per_usd(self, start: date, end: date) -> dict[date, dict[str, Decimal]]:
        params = {"base": "USD"}
        if start == end:
            params["date"] = start.isoformat()
        else:
            params["from"] = start.isoformat()
            params["to"] = end.isoformat()
        resp = self.client.get(f"{self.base_url}/rates", params=params)
        resp.raise_for_status()
        out: dict[date, dict[str, Decimal]] = {}
        for item in resp.json():
            if item.get("base") != "USD":
                continue
            d = date.fromisoformat(item["date"])
            out.setdefault(d, {})[item["quote"]] = Decimal(str(item["rate"]))
        return out


PROVIDERS = {"frankfurter": FrankfurterProvider}


def get_provider() -> FxProvider:
    return PROVIDERS[settings.fx_provider]()
