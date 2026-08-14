"""Self-check for the non-official web-session endpoints."""

from __future__ import annotations

import httpx
from rich.console import Console
from rich.table import Table

console = Console()

PROBES = {
    "store search (official)": ("GET", "https://store.steampowered.com/api/storesearch/?term=x&l=english&cc=us"),
    "app details (official)": ("GET", "https://store.steampowered.com/api/appdetails?appids=10&l=english&cc=us"),
    "community search (official)": ("GET", "https://steamcommunity.com/actions/SearchApps/x"),
    "wishlist endpoint": ("GET", "https://store.steampowered.com/wishlist/profiles/0/wishlistdata/"),
    "account page": ("GET", "https://store.steampowered.com/account/"),
    "friend invite page": ("GET", "https://steamcommunity.com/my/friends/"),
    "activation page": ("GET", "https://store.steampowered.com/account/registerkey"),
}


def run_doctor() -> None:
    table = Table(title="steam doctor")
    table.add_column("Endpoint")
    table.add_column("Status")
    table.add_column("HTTP")
    with httpx.Client(timeout=10, follow_redirects=True) as client:
        for name, (method, url) in PROBES.items():
            try:
                resp = client.request(method, url)
                ok = resp.status_code == 200
                table.add_row(name, "[green]ok[/green]" if ok else "[red]fail[/red]", str(resp.status_code))
            except httpx.HTTPError as exc:
                table.add_row(name, "[red]fail[/red]", str(exc.__class__.__name__))
    console.print(table)
