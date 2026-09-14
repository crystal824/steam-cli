"""Unified client: WebAPI for read-only data + an authenticated session for
web-session operations. Not ValvePython's SteamClient class (no gevent)."""

from __future__ import annotations

import re
from functools import lru_cache
from urllib.parse import quote

import httpx
import requests
from steam.webapi import WebAPI

from . import USER_AGENT, auth, region
from .errors import ApiKeyMissingError, NetworkError

_APPID_RE = re.compile(r"^\d+$")
# CJK titles: see resolve_appid() — the community search index cannot be trusted for them.
_CJK_RE = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]")


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


def owned_games(client: SteamClient) -> list[dict]:
    """Games in the signed-in account's library (requires key + session)."""
    try:
        response = client.api.IPlayerService.GetOwnedGames(
            steamid=auth.require_steam_id(),
            include_appinfo=1,
            include_played_free_games=1,
        )
    except (requests.RequestException, ValueError) as exc:
        raise NetworkError(detail=str(exc))
    return response.get("response", {}).get("games", [])


def join_terms(parts: str | list[str] | tuple[str, ...] | None) -> str:
    """Join a positional `<name>` that typer collected as a list of words.

    `steam search black myth` used to die with "Got unexpected extra argument(s) (myth)"
    unless the user quoted it — a poor first impression for a CLI whose examples all
    involve multi-word game names. Every command that accepts a name runs its
    positional argument through here.
    """
    if isinstance(parts, str):
        return parts.strip()
    if not parts:
        return ""
    return " ".join(str(part) for part in parts).strip()


@lru_cache(maxsize=2048)
def resolve_appid(term: str) -> int:
    term = term.strip()
    if _APPID_RE.match(term):
        return int(term)
    # A CJK title goes through the Chinese store search first: the community
    # SearchApps index answers [] for 艾尔登法环/战地6 and can even return a
    # knock-off for 黑神话, while storesearch with l=schinese&cc=cn returns the
    # real game (黑神话 → 2358720, 艾尔登法环 → 1245620, verified 2026-09-13).
    if _CJK_RE.search(term):
        hits = _store_search(term, lang="schinese", cc="cn")
        if hits:
            return int(hits[0]["appid"])
    results = _search_apps(term)
    if not results:
        results = _store_search(term)
    if not results and not _CJK_RE.search(term):
        results = _store_search(term, lang="schinese", cc="cn")
    if not results:
        raise NetworkError(f"no app found for {term!r}")
    return int(results[0]["appid"])


def _search_apps(term: str) -> list[dict]:
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://steamcommunity.com/actions/SearchApps/" + quote(term, safe=""),
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
            return list(resp.json())
    except (httpx.HTTPError, ValueError):
        return []


def _store_search(term: str, lang: str | None = None, cc: str | None = None) -> list[dict]:
    """Store search. Region/language default to the account's (see region.py)."""
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://store.steampowered.com/api/storesearch/",
                params=region.store_params({"term": term, "l": lang, "cc": cc}),
                headers={"User-Agent": USER_AGENT},
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
                params=region.store_params({"appids": appid}),
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise NetworkError(detail=str(exc))
    entry = data.get(str(appid), {})
    if entry.get("success"):
        return entry["data"].get("name", str(appid))
    return str(appid)
