"""Price / discount helpers. Current prices come from the official store
appdetails endpoint; historical lows come from IsThereAnyDeal's API (requires
an ITAD developer key set via the STEAM_CLI_ITAD_KEY environment variable)."""

from __future__ import annotations

import os

import httpx

from ..errors import NetworkError

_STORE_DETAILS = "https://store.steampowered.com/api/appdetails"
_ITAD_LOOKUP = "https://api.isthereanydeal.com/games/lookup/v1"
_ITAD_PRICES = "https://api.isthereanydeal.com/games/prices/v3"
_STEAM_SHOP_ID = 61


def itad_available() -> bool:
    return bool(os.environ.get("STEAM_CLI_ITAD_KEY"))


def _appdetails(appid: int, cc: str = "us", lang: str = "english") -> dict:
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                _STORE_DETAILS,
                params={"appids": appid, "cc": cc, "l": lang},
                headers={"User-Agent": "steam-cli/0.1"},
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise NetworkError(detail=str(exc))
    entry = data.get(str(appid), {})
    if not entry.get("success"):
        raise NetworkError(f"no store data for appid {appid}")
    return entry["data"]


def current_price(appid: int, cc: str = "us") -> dict:
    data = _appdetails(appid, cc=cc)
    price = data.get("price_overview") or {}
    discount = price.get("discount_percent", 0)
    return {
        "appid": appid,
        "name": data.get("name", str(appid)),
        "free": data.get("is_free", False),
        "currency": price.get("currency"),
        "final": price.get("final"),
        "initial": price.get("initial"),
        "discount_percent": discount,
        "on_sale": discount > 0,
        "formatted": price.get("final_formatted"),
    }


def _itad_key() -> str | None:
    return os.environ.get("STEAM_CLI_ITAD_KEY") or None


def _itad_lookup(appid: int) -> str | None:
    key = _itad_key()
    if not key:
        return None
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                _ITAD_LOOKUP,
                params={"key": key, "appid": appid},
                headers={"User-Agent": "steam-cli/0.1"},
            )
            if resp.status_code in (401, 403):
                return None
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError):
        return None
    if not data.get("found"):
        return None
    game = data.get("game") or {}
    return game.get("id")


def price_history(appid: int, cc: str = "us") -> dict | None:
    itad_id = _itad_lookup(appid)
    if not itad_id:
        return None
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                _ITAD_PRICES,
                params={
                    "key": _itad_key(),
                    "country": cc.upper(),
                    "shops": str(_STEAM_SHOP_ID),
                },
                json=[itad_id],
                headers={"User-Agent": "steam-cli/0.1"},
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError):
        return None
    prices = data if isinstance(data, list) else []
    if not prices:
        return None
    entry = prices[0]
    low = entry.get("historyLow", {}).get("all") or {}
    return {
        "appid": appid,
        "historical_low": low.get("amount"),
        "historical_low_currency": low.get("currency"),
        "historical_low_at": None,
    }
