"""Wishlist commands.

LOCAL PATCH 2026-09-11: the store wishlist endpoints this shipped with are gone.
`https://store.steampowered.com/wishlist/profiles/<id>/wishlistdata/` now answers
302 for every request (verified with a valid session and with/without an XHR
header), so `wishlist list` / `on-sale` failed with a JSON decode error. Current
Steam serves wishlists through the Web API:

    GET https://api.steampowered.com/IWishlistService/GetWishlist/v1/?steamid=<id>
    -> {"response": {"items": [{"appid": 110800, "priority": 1, "date_added": ...}]}}

The add/remove endpoints are unchanged.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import requests
import typer
from rich.console import Console
from rich.table import Table

from .. import USER_AGENT, auth, region
from ..client import join_terms, resolve_appid
from ..errors import ForbiddenError, NetworkError
from ..utils.price import current_price

console = Console()

WISHLIST_API = "https://api.steampowered.com/IWishlistService/GetWishlist/v1/"
APPNAME_CACHE = auth.CONFIG_DIR / "appnames.json"
STORE_DETAILS_URL = "https://store.steampowered.com/api/appdetails"
ADD_TO_WISHLIST_URL = "https://store.steampowered.com/api/addtowishlist"
REMOVE_FROM_WISHLIST_URL = "https://store.steampowered.com/api/removefromwishlist"


def _session_id(session: requests.Session) -> str:
    sid = auth.cookie_value(session, "sessionid")
    if sid:
        return sid
    state = auth.load_session()
    return state.session_id if state else ""


def _wishlist_items(session: requests.Session, steamid: str) -> list[dict]:
    """Return the raw wishlist items (newest Steam API)."""
    params: dict[str, str] = {"steamid": steamid}
    api_key = auth.get_api_key()
    if api_key:
        params["key"] = api_key
    try:
        resp = session.get(WISHLIST_API, params=params, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        raise NetworkError(detail=str(exc))
    items = (payload.get("response") or {}).get("items")
    if items is None:
        raise NetworkError("unexpected wishlist response")
    return [i for i in items if isinstance(i, dict) and i.get("appid")]


def wishlist_appids() -> list[int]:
    """AppIDs on the signed-in account's wishlist, via IWishlistService.

    The old store `wishlistdata` endpoint is retired (HTTP 302 for every request).
    """
    session = auth.require_session()
    steamid = auth.require_steam_id()
    return [int(i["appid"]) for i in _wishlist_items(session, steamid)]


def _load_name_cache() -> dict[str, str]:
    try:
        data = json.loads(APPNAME_CACHE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_name_cache(cache: dict[str, str]) -> None:
    try:
        APPNAME_CACHE.parent.mkdir(parents=True, exist_ok=True)
        APPNAME_CACHE.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass


def _fetch_name(appid: int) -> tuple[int, str]:
    """One appid -> name. Batched appdetails was retired by Steam (400 on any
    comma-separated list), so this is deliberately single-appid, run concurrently."""
    try:
        resp = requests.get(
            STORE_DETAILS_URL,
            params=region.store_params({"appids": str(appid)}),
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        payload = resp.json()
    except (requests.RequestException, ValueError):
        return appid, ""
    entry = payload.get(str(appid)) if isinstance(payload, dict) else None
    if isinstance(entry, dict) and entry.get("success"):
        return appid, (entry.get("data") or {}).get("name") or ""
    return appid, ""


def _app_names(session: requests.Session, appids: list[int]) -> dict[int, str]:
    cache = _load_name_cache()
    names: dict[int, str] = {}
    missing: list[int] = []
    for appid in appids:
        cached = cache.get(str(appid))
        if cached:
            names[appid] = cached
        else:
            missing.append(appid)
    if missing:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for appid, name in pool.map(_fetch_name, missing):
                if name:
                    names[appid] = name
                    cache[str(appid)] = name
        _save_name_cache(cache)
    return names


def _wishlist_map(session: requests.Session, steamid: str) -> dict[int, dict]:
    """appid -> {name, priority} for the whole wishlist."""
    items = _wishlist_items(session, steamid)
    appids = [int(i["appid"]) for i in items]
    names = _app_names(session, appids)
    out: dict[int, dict] = {}
    for item in items:
        appid = int(item["appid"])
        out[appid] = {
            "name": names.get(appid, str(appid)),
            "priority": item.get("priority") or 0,
        }
    return out


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
        entries = _wishlist_map(session, steamid)
        if not entries:
            console.print("wishlist is empty")
            return
        table = Table(title=f"Wishlist ({len(entries)} items)")
        table.add_column("AppID")
        table.add_column("Name")
        for appid, info in sorted(entries.items(), key=lambda kv: kv[1]["priority"]):
            table.add_row(str(appid), info["name"])
        console.print(table)

    @group.command()
    def add(
        appid_or_name: list[str],
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview only"),
    ):
        """Add a game to your wishlist."""
        appid = resolve_appid(join_terms(appid_or_name))
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
        appid_or_name: list[str],
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview only"),
    ):
        """Remove a game from your wishlist."""
        appid = resolve_appid(join_terms(appid_or_name))
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
        entries = _wishlist_map(session, steamid)
        if not entries:
            console.print("wishlist is empty")
            return
        table = Table(title="Wishlist on sale")
        table.add_column("AppID")
        table.add_column("Name")
        table.add_column("Discount")
        table.add_column("Price")
        shown = 0
        for appid, info in sorted(entries.items(), key=lambda kv: kv[1]["priority"]):
            try:
                price = current_price(appid)
            except NetworkError:
                continue
            if not price["on_sale"]:
                continue
            shown += 1
            table.add_row(
                str(appid),
                price["name"] or info["name"],
                f"{price['discount_percent']}%",
                price["formatted"] or "-",
            )
        if shown == 0:
            console.print("no wishlisted games are on sale right now")
            return
        console.print(table)
