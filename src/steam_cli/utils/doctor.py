"""Self-check for the non-official web-session endpoints."""

from __future__ import annotations

import httpx
from rich.console import Console
from rich.table import Table

from .. import region

console = Console()

# (method, url, params); params are merged with the resolved store region.
PROBES = {
    "store search (official)": (
        "GET",
        "https://store.steampowered.com/api/storesearch/",
        {"term": "x"},
    ),
    "app details (official)": (
        "GET",
        "https://store.steampowered.com/api/appdetails",
        {"appids": "10"},
    ),
    "community search (official)": ("GET", "https://steamcommunity.com/actions/SearchApps/x", None),
    "wishlist endpoint": (
        "GET",
        "https://store.steampowered.com/wishlist/profiles/0/wishlistdata/",
        None,
    ),
    "account page": ("GET", "https://store.steampowered.com/account/", None),
    "friend invite page": ("GET", "https://steamcommunity.com/my/friends/", None),
    "activation page": ("GET", "https://store.steampowered.com/account/registerkey", None),
}


def run_doctor() -> None:
    table = Table(title="steam doctor")
    table.add_column("Endpoint")
    table.add_column("Status")
    table.add_column("HTTP")
    with httpx.Client(timeout=10, follow_redirects=True) as client:
        for name, (method, url, params) in PROBES.items():
            try:
                resp = client.request(
                    method, url, params=region.store_params(params) if params else None
                )
                ok = resp.status_code == 200
                table.add_row(
                    name, "[green]ok[/green]" if ok else "[red]fail[/red]", str(resp.status_code)
                )
            except httpx.HTTPError as exc:
                table.add_row(name, "[red]fail[/red]", str(exc.__class__.__name__))
    console.print(table)
