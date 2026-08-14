"""Wishlist commands (store web-session endpoints)."""

from __future__ import annotations

import requests
import typer
from rich.console import Console
from rich.table import Table

from .. import auth
from ..client import resolve_appid
from ..errors import ForbiddenError, NetworkError
from ..utils.price import current_price

console = Console()

WISHLIST_DATA_URL = "https://store.steampowered.com/wishlist/profiles/{steamid}/wishlistdata/"
ADD_TO_WISHLIST_URL = "https://store.steampowered.com/api/addtowishlist"
REMOVE_FROM_WISHLIST_URL = "https://store.steampowered.com/api/removefromwishlist"


def _session_id(session: requests.Session) -> str:
    sid = session.cookies.get("sessionid")
    if sid:
        return sid
    state = auth.load_session()
    return state.session_id if state else ""


def _wishlist_data(session: requests.Session, steamid: str) -> dict:
    url = WISHLIST_DATA_URL.format(steamid=steamid) + "?p=0"
    try:
        resp = session.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise NetworkError(detail=str(exc))
    if not isinstance(data, dict):
        raise NetworkError("unexpected wishlist response")
    return data


def _wishlist_modify(session: requests.Session, url: str, appid: int, sessionid: str) -> str:
    try:
        resp = session.post(url, data={"appid": appid, "sessionid": sessionid}, timeout=20)
    except requests.RequestException as exc:
        raise NetworkError(detail=str(exc))
    if resp.status_code == 403:
        return "forbidden"
    if resp.status_code != 200:
        return str(resp.status_code)
    return "ok"


def register(app: typer.Typer) -> None:
    group = typer.Typer()
    app.add_typer(group, name="wishlist")

    @group.command("list")
    def list_wishlist():
        """List your Steam wishlist."""
        session = auth.require_session()
        steamid = auth.require_steam_id()
        data = _wishlist_data(session, steamid)
        if not data:
            console.print("wishlist is empty")
            return
        table = Table(title="Wishlist")
        table.add_column("AppID")
        table.add_column("Name")
        for appid, info in data.items():
            table.add_row(
                str(appid), info.get("name", str(appid)) if isinstance(info, dict) else str(info)
            )
        console.print(table)

    @group.command()
    def add(
        appid_or_name: str,
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview only"),
    ):
        """Add a game to your wishlist."""
        appid = resolve_appid(appid_or_name)
        if dry_run:
            console.print(f"[yellow]dry-run[/yellow] would add appid {appid} to the wishlist")
            return
        session = auth.require_session()
        result = _wishlist_modify(session, ADD_TO_WISHLIST_URL, appid, _session_id(session))
        auth.log_audit("wishlist.add", str(appid), result)
        if result == "ok":
            console.print(f"[green]Added appid {appid} to the wishlist.[/green]")
        elif result == "forbidden":
            raise ForbiddenError()
        else:
            raise NetworkError(detail=f"HTTP {result}")

    @group.command()
    def remove(
        appid_or_name: str,
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview only"),
    ):
        """Remove a game from your wishlist."""
        appid = resolve_appid(appid_or_name)
        if dry_run:
            console.print(f"[yellow]dry-run[/yellow] would remove appid {appid} from the wishlist")
            return
        session = auth.require_session()
        result = _wishlist_modify(session, REMOVE_FROM_WISHLIST_URL, appid, _session_id(session))
        auth.log_audit("wishlist.remove", str(appid), result)
        if result == "ok":
            console.print(f"[green]Removed appid {appid} from the wishlist.[/green]")
        elif result == "forbidden":
            raise ForbiddenError()
        else:
            raise NetworkError(detail=f"HTTP {result}")

    @group.command("on-sale")
    def on_sale():
        """Show wishlisted games that are currently on sale."""
        session = auth.require_session()
        steamid = auth.require_steam_id()
        data = _wishlist_data(session, steamid)
        if not data:
            console.print("wishlist is empty")
            return
        table = Table(title="Wishlist on sale")
        table.add_column("AppID")
        table.add_column("Name")
        table.add_column("Discount")
        table.add_column("Price")
        shown = 0
        for appid_str in list(data.keys())[:100]:
            try:
                appid = int(appid_str)
            except ValueError:
                continue
            try:
                price = current_price(appid)
            except NetworkError:
                continue
            if not price["on_sale"]:
                continue
            shown += 1
            table.add_row(
                str(appid),
                price["name"],
                f"{price['discount_percent']}%",
                price["formatted"] or "-",
            )
        if shown == 0:
            console.print("no wishlisted games are on sale right now")
            return
        console.print(table)
