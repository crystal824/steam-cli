"""Unified client: WebAPI for read-only data + an authenticated session for
web-session operations. Not ValvePython's SteamClient class (no gevent)."""

from __future__ import annotations

import re
from functools import lru_cache

import httpx

from steam.webapi import WebAPI

from . import auth
from .errors import ApiKeyMissingError, NetworkError

_APPID_RE = re.compile(r"^\d+$")


class SteamClient:
    def __init__(self, api_key: str | None = None, require_key: bool = True):
        self.api_key = api_key if api_key is not None else auth.get_api_key()
        if require_key and not self.api_key:
            raise ApiKeyMissingError()
        self._api: WebAPI | None = None
        if self.api_key:
            self._api = WebAPI(key=self.api_key)

    @property
    def api(self) -> WebAPI:
        if self._api is None:
            raise ApiKeyMissingError()
        return self._api


@lru_cache(maxsize=2048)
def resolve_appid(term: str) -> int:
    term = term.strip()
    if _APPID_RE.match(term):
        return int(term)
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://steamcommunity.com/actions/SearchApps/" + term,
                headers={"User-Agent": "Mozilla/5.0 (steam-cli/0.1)"},
            )
            resp.raise_for_status()
            results = resp.json()
    except (httpx.HTTPError, ValueError):
        results = _store_search(term)
    if not results:
        raise NetworkError(f"no app found for {term!r}")
    return int(results[0]["appid"])


def _store_search(term: str) -> list[dict]:
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://store.steampowered.com/api/storesearch/",
                params={"term": term, "l": "english", "cc": "us"},
                headers={"User-Agent": "steam-cli/0.1"},
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
    except (httpx.HTTPError, ValueError):
        return []
    return [{"appid": i["id"], "name": i.get("name", "")} for i in items]


def resolve_name(appid: int) -> str:
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://store.steampowered.com/api/appdetails",
                params={"appids": appid, "cc": "us", "l": "english"},
                headers={"User-Agent": "steam-cli/0.1"},
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise NetworkError(detail=str(exc))
    entry = data.get(str(appid), {})
    if entry.get("success"):
        return entry["data"].get("name", str(appid))
    return str(appid)
