from __future__ import annotations

import datetime
import time

import httpx
import requests
import typer
from rich.console import Console
from rich.table import Table

from .. import auth
from ..client import SteamClient, resolve_appid
from ..errors import NetworkError
from ..utils.price import current_price, itad_available, price_history

console = Console()

_STORE_SEARCH = "https://store.steampowered.com/api/storesearch/"
_STORE_DETAILS = "https://store.steampowered.com/api/appdetails"
_WISHLIST = "https://store.steampowered.com/wishlist/profiles/{steamid}/wishlistdata/"
_UA = "steam-cli/0.1"


def _get_json(url: str, params: dict | None = None) -> dict:
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(url, params=params, headers={"User-Agent": _UA})
            resp.raise_for_status()
            return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise NetworkError(detail=str(exc))


def _format_ts(ts: float | int | None) -> str:
    if not ts:
        return "-"
    try:
        return datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return str(ts)


def register(app: typer.Typer) -> None:
    @app.command()
    def search(
        query: str,
        limit: int = 10,
        type: str = typer.Option("all", help="game|dlc|software|all"),
    ) -> None:
        """Search the Steam store."""
        data = _get_json(
            _STORE_SEARCH,
            params={"term": query, "l": "english", "cc": "us", "count": limit},
        )
        hits = data.get("items", [])
        if type != "all":
            hits = [h for h in hits if h.get("type") == type]

        table = Table(title=f"search: {query}")
        table.add_column("AppID")
        table.add_column("Name")
        table.add_column("Type")
        for hit in hits:
            table.add_row(str(hit.get("id", "")), hit.get("name", ""), hit.get("type", ""))
        console.print(table)

    @app.command("app")
    def app_details(appid_or_name: str) -> None:
        """Show details for an app."""
        appid = resolve_appid(appid_or_name)
        payload = _get_json(
            _STORE_DETAILS,
            params={"appids": appid, "l": "english", "cc": "us"},
        )
        entry = payload.get(str(appid)) or {}
        if not entry.get("success"):
            console.print("[yellow]No store data available for this app.[/yellow]")
            return
        data = entry.get("data") or {}

        console.print(f"[bold]{data.get('name', appid_or_name)}[/bold]")
        console.print(f"type: {data.get('type', '-')}")
        console.print("free: " + ("yes" if data.get("is_free") else "no"))

        price = data.get("price_overview") or {}
        if price:
            line = f"price: {price.get('final_formatted', '-')}"
            if price.get("discount_percent"):
                line += f"  ([green]-{price['discount_percent']}%[/green])"
            console.print(line)
        else:
            console.print("price: -")

        genres = ", ".join(g.get("description", "") for g in data.get("genres", []))
        if genres:
            console.print(f"genres: {genres}")

        categories = ", ".join(c.get("description", "") for c in data.get("categories", []))
        if categories:
            console.print(f"categories: {categories}")

        release = (data.get("release_date") or {}).get("date")
        if release:
            console.print(f"release: {release}")

        description = data.get("short_description") or ""
        if description:
            if len(description) > 200:
                description = description[:200] + "\u2026"
            console.print(f"description: {description}")

        recs = (data.get("recommendations") or {}).get("total")
        if recs is not None:
            console.print(f"recommendations: {recs}")

    @app.command()
    def price(appid_or_name: str) -> None:
        """Show current and historical low price for an app."""
        appid = resolve_appid(appid_or_name)
        cur = current_price(appid)
        console.print(f"[bold]{cur['name']}[/bold]")
        if cur["free"]:
            console.print("price: Free to Play")
        else:
            line = f"price: {cur['formatted'] or '-'}"
            if cur["discount_percent"]:
                line += f"  ([green]-{cur['discount_percent']}%[/green])"
            console.print(line)

        hist = price_history(appid)
        if hist is not None and hist.get("historical_low") is not None:
            low = hist["historical_low"]
            cur = hist.get("historical_low_currency") or ""
            console.print(f"historical low: {low} {cur}".rstrip())
        elif not itad_available():
            console.print(
                "[dim]historical low unavailable; set STEAM_CLI_ITAD_KEY to enable[/dim]"
            )

    @app.command()
    def news(appid: str, count: int = 5) -> None:
        """Show recent news for an app (requires a Web API key)."""
        client = SteamClient()
        try:
            resp = client.api.ISteamNews.GetNewsForApp(
                appid=appid, count=count, maxlength=300, format="json"
            )
        except (requests.RequestException, ValueError) as exc:
            raise NetworkError(detail=str(exc))

        items = (resp.get("appnews") or {}).get("newsitems", [])
        table = Table(title=f"news: {appid}")
        table.add_column("Date")
        table.add_column("Title")
        table.add_column("Author")
        for item in items:
            table.add_row(
                _format_ts(item.get("date")),
                item.get("title", ""),
                item.get("author", ""),
            )
        console.print(table)

    @app.command()
    def radar(
        wishlist: bool = False,
        library_never_played: bool = False,
    ) -> None:
        """Find sale items across your wishlist or unplayed library."""
        steam_id = auth.require_steam_id()

        if not wishlist and not library_never_played:
            wishlist = True

        candidates: list[int] = []

        if wishlist:
            session = auth.require_session()
            try:
                resp = session.get(
                    _WISHLIST.format(steamid=steam_id),
                    params={"p": 0},
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
            except (requests.RequestException, ValueError) as exc:
                raise NetworkError(detail=str(exc))
            for key in data:
                if str(key).isdigit():
                    candidates.append(int(key))

        if library_never_played:
            client = SteamClient()
            try:
                resp = client.api.IPlayerService.GetOwnedGames(
                    steamid=steam_id,
                    include_appinfo=1,
                    include_played_free_games=1,
                )
            except (requests.RequestException, ValueError) as exc:
                raise NetworkError(detail=str(exc))
            games = (resp.get("response") or {}).get("games", [])
            for game in games:
                if game.get("playtime_forever", 0) == 0:
                    appid = game.get("appid")
                    if appid is not None and appid not in candidates:
                        candidates.append(int(appid))

        candidates = candidates[:50]

        table = Table(title="steam radar")
        table.add_column("AppID")
        table.add_column("Name")
        table.add_column("Discount")
        table.add_column("Price")

        on_sale = 0
        for appid in candidates:
            try:
                info = current_price(appid)
            except NetworkError:
                time.sleep(0.1)
                continue
            if not info["on_sale"]:
                time.sleep(0.1)
                continue
            on_sale += 1
            table.add_row(
                str(appid),
                info["name"],
                f"-{info['discount_percent']}%",
                info["formatted"] or "-",
            )
            time.sleep(0.1)

        console.print(table)
        console.print(f"scanned {len(candidates)} apps, {on_sale} on sale")
