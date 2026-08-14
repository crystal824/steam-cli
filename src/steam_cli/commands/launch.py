"""Launch a game via the steam:// run URI."""

from __future__ import annotations

import webbrowser

import typer
from rich.console import Console

from ..client import resolve_appid

console = Console()


def register(app: typer.Typer) -> None:
    @app.command()
    def launch(appid_or_name: str) -> None:
        """Launch a game through Steam."""
        appid = resolve_appid(appid_or_name)
        uri = f"steam://run/{appid}"
        console.print(uri)
        if not webbrowser.open(uri):
            console.print(f"[yellow]Could not open a browser; run `{uri}` manually.[/yellow]")
