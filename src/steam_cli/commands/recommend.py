"""Simple genre-based recommendation engine (no external ML)."""

from __future__ import annotations

import time
from collections import Counter

import httpx
import requests
import typer
from rich.console import Console
from rich.table import Table

from .. import auth
from ..client import SteamClient, resolve_name
from ..errors import NetworkError

console = Console()

_STORE_SPECIALS = "https://store.steampowered.com/api/featuredcategories/?l=english&cc=us"
_DETAILS = "https://store.steampowered.com/api/appdetails"
_REQUEST_GAP = 0.1


def _app_genres(appid: int) -> set[str]:
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                _DETAILS,
                params={"appids": appid, "l": "english", "cc": "us"},
                headers={"User-Agent": "steam-cli/0.1"},
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise NetworkError(detail=str(exc))
    entry = data.get(str(appid), {})
    if not entry.get("success"):
        return set()
    return {g.get("description", "") for g in entry["data"].get("genres", [])}


def _owned_games(api: object, steam_id: str) -> list[dict]:
    try:
        resp = api.IPlayerService.GetOwnedGames(
            steamid=steam_id, include_appinfo=1, include_played_free_games=1
        )
    except (requests.RequestException, ValueError) as exc:
        raise NetworkError(detail=str(exc))
    return resp.get("response", {}).get("games", [])


def _wishlist_appids(steam_id: str) -> list[int]:
    try:
        session = auth.require_session()
        resp = session.get(
            f"https://store.steampowered.com/wishlist/profiles/{steam_id}/wishlistdata/?p=0",
            timeout=15,
        )
        resp.raise_for_status()
        return [int(a) for a in resp.json().keys()]
    except (requests.RequestException, ValueError) as exc:
        raise NetworkError(detail=str(exc))


def _candidate_pool() -> list[int]:
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(_STORE_SPECIALS, headers={"User-Agent": "steam-cli/0.1"})
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError):
        return []
    pool: list[int] = []
    for section in ("specials", "top_sellers", "new_releases"):
        for item in data.get(section, {}).get("items", []):
            if isinstance(item.get("id"), int):
                pool.append(item["id"])
    return pool


def register(app: typer.Typer) -> None:
    @app.command()
    def recommend(
        based_on: str = typer.Option("library", help="library|wishlist"),
        limit: int = typer.Option(5, help="number of recommendations"),
    ):
        """Recommend games by genre overlap with your library or wishlist."""
        steam_id = auth.require_steam_id()
        client = SteamClient()
        api = client.api

        owned = _owned_games(api, steam_id)
        owned_set = {g["appid"] for g in owned}

        if based_on == "wishlist":
            seed_appids = [a for a in _wishlist_appids(steam_id) if a not in owned_set]
        else:
            playtime = {g["appid"]: g.get("playtime_forever", 0) for g in owned}
            seed_appids = sorted(owned_set, key=lambda a: playtime.get(a, 0), reverse=True)[:10]

        if not seed_appids:
            console.print("[yellow]No seed games found.[/yellow]")
            return

        profile: Counter[str] = Counter()
        for appid in seed_appids[:10]:
            profile.update(_app_genres(appid))
            time.sleep(_REQUEST_GAP)

        scored: list[tuple[int, float]] = []
        for appid in _candidate_pool():
            if appid in owned_set:
                continue
            genres = _app_genres(appid)
            score = sum(profile[g] for g in genres)
            if score > 0:
                scored.append((appid, score))
            time.sleep(_REQUEST_GAP)

        if not scored:
            console.print("[yellow]No candidate games found.[/yellow]")
            return

        scored.sort(key=lambda x: x[1], reverse=True)
        table = Table(title="Recommendations")
        table.add_column("#")
        table.add_column("Name")
        table.add_column("Score")
        for i, (appid, score) in enumerate(scored[:limit], start=1):
            try:
                name = resolve_name(appid)
            except NetworkError:
                name = str(appid)
            table.add_row(str(i), name, str(score))
        console.print(table)
