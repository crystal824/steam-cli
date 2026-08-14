"""Library statistics commands."""

from __future__ import annotations

import datetime
from typing import Any

import requests
import typer
from rich.console import Console
from rich.table import Table

from .. import auth
from ..client import SteamClient, resolve_appid
from ..errors import NetworkError

console = Console()
group = typer.Typer()


def register(app: typer.Typer) -> None:
    app.add_typer(group, name="stats")


def _client() -> SteamClient:
    return SteamClient()


def _owned_games(client: SteamClient) -> list[dict[str, Any]]:
    try:
        response = client.api.IPlayerService.GetOwnedGames(
            steamid=auth.require_steam_id(),
            include_appinfo=1,
            include_played_free_games=1,
        )
    except (requests.RequestException, ValueError) as exc:
        raise NetworkError(detail=str(exc))
    return response.get("response", {}).get("games", [])


def _recently_played(client: SteamClient) -> list[dict[str, Any]]:
    try:
        response = client.api.IPlayerService.GetRecentlyPlayedGames(
            steamid=auth.require_steam_id()
        )
    except (requests.RequestException, ValueError) as exc:
        raise NetworkError(detail=str(exc))
    return response.get("response", {}).get("games", [])


@group.command()
def summary() -> None:
    """Summarize library statistics."""
    client = _client()
    games = _owned_games(client)
    recent = _recently_played(client)

    total_games = len(games)
    total_minutes = sum(g.get("playtime_forever", 0) for g in games)
    played_2weeks = len(recent)
    never_played = sum(1 for g in games if g.get("playtime_forever", 0) == 0)

    console.print(f"Total games: {total_games}")
    console.print(f"Total playtime: {total_minutes / 60:.1f} hours")
    console.print(f"Played in last 2 weeks: {played_2weeks}")
    console.print(f"Never played: {never_played}")

    top = sorted(games, key=lambda g: g.get("playtime_forever", 0), reverse=True)[:5]
    table = Table(title="Top 5 by playtime")
    table.add_column("Name")
    table.add_column("AppID", justify="right")
    table.add_column("Hours", justify="right")
    for g in top:
        table.add_row(
            str(g.get("name", g.get("appid"))),
            str(g.get("appid", "")),
            f"{g.get('playtime_forever', 0) / 60:.1f}",
        )
    console.print(table)


@group.command()
def game(appid: str) -> None:
    """Show stats for a single owned game."""
    client = _client()
    games = _owned_games(client)
    appid_int = resolve_appid(appid)
    owned = next((g for g in games if g.get("appid") == appid_int), None)
    if owned is None:
        console.print(f"[red]not in library[/red] — {appid_int}")
        return

    ts = owned.get("rtime_last_played") or 0
    try:
        last = datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "-"
    except (OverflowError, OSError, ValueError):
        last = "-"
    console.print(f"{owned.get('name') or appid_int} ({appid_int})")
    console.print(f"Playtime: {owned.get('playtime_forever', 0) / 60:.1f} hours")
    console.print(f"Last played: {last}")

    try:
        ach = client.api.ISteamUserStats.GetPlayerAchievements(
            appid=appid_int, steamid=auth.require_steam_id()
        )
    except (requests.RequestException, ValueError) as exc:
        raise NetworkError(detail=str(exc))
    achievements = ach.get("playerstats", {}).get("achievements")
    if achievements is None:
        console.print("Achievements: n/a")
    else:
        achieved = sum(1 for a in achievements if a.get("achieved"))
        console.print(f"Achievements: {achieved}/{len(achievements)}")
