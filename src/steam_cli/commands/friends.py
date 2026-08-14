"""Friends and profile commands."""

from __future__ import annotations

import datetime
import re

import requests
import typer
from rich.console import Console
from rich.table import Table

from .. import auth
from ..client import SteamClient, resolve_appid
from ..errors import EndpointUnavailableError, NetworkError

console = Console()

INVITE_LINK_URL = "https://steamcommunity.com/actions/QuickInviteLink"


def _fetch_friends(client: SteamClient, steamid: str) -> list[dict]:
    try:
        data = client.api.ISteamUser.GetFriendList(steamid=steamid, relationship="friend")
    except Exception as exc:
        raise NetworkError(detail=str(exc))
    return data.get("friendslist", {}).get("friends", [])


def _fetch_players(client: SteamClient, steamids: list[str]) -> list[dict]:
    try:
        data = client.api.ISteamUser.GetPlayerSummaries(steamids=",".join(steamids))
    except Exception as exc:
        raise NetworkError(detail=str(exc))
    return data.get("response", {}).get("players", [])


def _extract_invite_link(text: str) -> str | None:
    match = re.search(r"https://s\.team/p/[A-Za-z0-9_-]+", text)
    if match:
        return match.group(0)
    match = re.search(r"https://steamcommunity\.com/(quickinvite|invite)/[A-Za-z0-9_-]+", text)
    return match.group(0) if match else None


def register(app: typer.Typer) -> None:
    group = typer.Typer()
    app.add_typer(group, name="friends")

    @group.command("list")
    def list_friends(
        online: bool = typer.Option(False, "--online", help="Only show online friends"),
    ):
        """List your Steam friends."""
        client = SteamClient()
        steamid = auth.require_steam_id()
        friends = _fetch_friends(client, steamid)
        if not friends:
            console.print("no friends found")
            return
        players = _fetch_players(client, [f["steamid"] for f in friends])
        table = Table(title="Friends")
        table.add_column("Name")
        table.add_column("SteamID")
        table.add_column("Status")
        table.add_column("In-game")
        for p in players:
            state = p.get("personastate", 0)
            if online and state == 0:
                continue
            table.add_row(
                p.get("personaname", ""),
                str(p.get("steamid", "")),
                "Online" if state != 0 else "Offline",
                p.get("gameextrainfo") or "-",
            )
        console.print(table)

    @group.command()
    def playing(appid: str):
        """List friends currently playing a game."""
        client = SteamClient()
        steamid = auth.require_steam_id()
        target = resolve_appid(appid)
        friends = _fetch_friends(client, steamid)
        if not friends:
            console.print("no friends found")
            return
        players = _fetch_players(client, [f["steamid"] for f in friends])
        matches = [p for p in players if str(p.get("gameid", "")) == str(target)]
        if not matches:
            console.print("no friends currently playing this game")
            return
        for p in matches:
            console.print(f"{p.get('personaname', '')} - {p.get('gameextrainfo') or appid}")

    @group.command("recently-played")
    def recently_played():
        """Show your recently played games."""
        client = SteamClient()
        steamid = auth.require_steam_id()
        try:
            data = client.api.IPlayerService.GetRecentlyPlayedGames(steamid=steamid, count=0)
            games = data.get("response", {}).get("games", [])
        except Exception as exc:
            raise NetworkError(detail=str(exc))
        if not games:
            console.print("no recently played games")
            return
        table = Table(title="Recently played")
        table.add_column("Name")
        table.add_column("AppID")
        table.add_column("2 weeks (min)")
        table.add_column("Total (min)")
        for g in games:
            table.add_row(
                g.get("name", ""),
                str(g.get("appid", "")),
                str(g.get("playtime_2weeks", 0)),
                str(g.get("playtime_forever", 0)),
            )
        console.print(table)

    @group.command("invite-link")
    def invite_link(
        refresh: bool = typer.Option(
            False, "--refresh", help="Generate a new link (invalidates the old one)"
        ),
    ):
        """Show or refresh your friend invite link."""
        session = auth.require_session()
        try:
            sessionid = session.cookies.get("sessionid") or ""
            if refresh:
                resp = session.post(
                    INVITE_LINK_URL, data={"sessionid": sessionid}, timeout=15
                )
            else:
                resp = session.get(INVITE_LINK_URL, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise EndpointUnavailableError(
                detail=f"{exc}; this endpoint may have changed"
            )
        link = _extract_invite_link(resp.text)
        if not link:
            raise EndpointUnavailableError(
                "could not parse an invite link; this endpoint may have changed"
            )
        console.print(link)
        auth.log_audit("friends.invite-link", "refresh" if refresh else "get", "ok")

    @app.command()
    def profile(steamid_or_vanity: str):
        """Show a public Steam profile by SteamID64 or vanity URL."""
        client = SteamClient()
        term = steamid_or_vanity.strip()
        steamid = term
        try:
            data = client.api.ISteamUser.ResolveVanityURL(vanityurl=term)
            response = data.get("response", {})
            if response.get("success") == 1:
                steamid = response.get("steamid") or steamid
        except Exception:
            steamid = term
        try:
            data = client.api.ISteamUser.GetPlayerSummaries(steamids=steamid)
            players = data.get("response", {}).get("players", [])
        except Exception as exc:
            raise NetworkError(detail=str(exc))
        if not players:
            raise NetworkError("profile not found")
        p = players[0]
        console.print(f"[bold]{p.get('personaname', '')}[/bold]")
        console.print(f"SteamID: {p.get('steamid', '')}")
        console.print(f"Profile: https://steamcommunity.com/profiles/{p.get('steamid', '')}")
        state = p.get("personastate", 0)
        console.print(f"Status: {'Online' if state else 'Offline'}")
        for key, label in (
            ("realname", "Real name"),
            ("locacountryid", "Country"),
            ("locastateid", "State"),
            ("locacityid", "City"),
        ):
            if p.get(key):
                console.print(f"{label}: {p[key]}")
        if p.get("timecreated"):
            created = datetime.datetime.fromtimestamp(
                int(p["timecreated"]), datetime.timezone.utc
            ).strftime("%Y-%m-%d")
            console.print(f"Member since: {created}")
