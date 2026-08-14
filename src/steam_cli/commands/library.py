"""Library commands for the user's owned games."""

from __future__ import annotations

import datetime
from typing import Any

import requests
import typer
from rich.console import Console
from rich.table import Table

from .. import auth
from ..client import SteamClient, resolve_appid, resolve_name
from ..errors import NetworkError

console = Console()
group = typer.Typer()


def register(app: typer.Typer) -> None:
    app.add_typer(group, name="library")


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


def _last_played(game: dict[str, Any]) -> str:
    ts = game.get("rtime_last_played") or 0
    if not ts:
        return "-"
    try:
        return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return "-"


@group.command("list")
def list_games(
    recent: bool = typer.Option(False, "--recent", help="Only games played in the last 2 weeks"),
    never_played: bool = typer.Option(False, "--never-played", help="Only games never played"),
    sort: str = typer.Option("name", "--sort", help="name|playtime|added"),
) -> None:
    """List owned games."""
    client = _client()
    games = _owned_games(client)

    if recent:
        games = [g for g in games if g.get("playtime_2weeks", 0) > 0]
        games.sort(key=lambda g: g.get("playtime_2weeks", 0), reverse=True)
    elif never_played:
        games = [g for g in games if g.get("playtime_forever", 0) == 0]
    elif sort == "playtime":
        games.sort(key=lambda g: g.get("playtime_forever", 0), reverse=True)
    elif sort == "added":
        games.sort(key=lambda g: g.get("rtime_last_played", 0) or 0, reverse=True)
    else:
        games.sort(key=lambda g: str(g.get("name", "")).lower())

    table = Table(title="Library")
    table.add_column("Name")
    table.add_column("AppID", justify="right")
    table.add_column("Playtime (h)", justify="right")
    table.add_column("Last played")
    for g in games:
        table.add_row(
            str(g.get("name", g.get("appid"))),
            str(g.get("appid", "")),
            f"{g.get('playtime_forever', 0) / 60:.1f}",
            _last_played(g),
        )
    console.print(table)


@group.command()
def has(appid_or_name: str) -> None:
    """Check whether a game is in the library."""
    client = _client()
    games = _owned_games(client)
    appid = resolve_appid(appid_or_name)
    owned = next((g for g in games if g.get("appid") == appid), None)
    if owned is not None:
        console.print(f"[green]yes[/green] — {owned.get('name') or appid} ({appid})")
    else:
        console.print(f"[red]no[/red] — {resolve_name(appid)} ({appid})")
