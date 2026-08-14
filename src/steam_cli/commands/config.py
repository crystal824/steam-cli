"""Central configuration commands (currently: proxy settings).

Proxy applies to every Steam request (WebAPI, WebAuth sessions and httpx
calls) via the HTTP_PROXY / HTTPS_PROXY environment variables.
"""

from __future__ import annotations

import urllib.parse

import httpx
import typer
from rich.console import Console

from .. import auth
from ..errors import InvalidFormatError

console = Console()

_SUPPORTED_SCHEMES = ("http", "https", "socks4", "socks5", "socks5h")
_TEST_URL = "https://store.steampowered.com/"


def validate_proxy_url(url: str) -> str:
    url = url.strip()
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in _SUPPORTED_SCHEMES:
        raise InvalidFormatError(
            f"unsupported proxy scheme {parsed.scheme!r}",
            detail=f"supported schemes: {', '.join(_SUPPORTED_SCHEMES)}",
        )
    if not parsed.hostname:
        raise InvalidFormatError("proxy URL is missing a host", detail=url)
    return url


def build_proxy_url(host: str, port: int, username: str = "", password: str = "") -> str:
    userinfo = ""
    if username:
        encoded_user = urllib.parse.quote(username, safe="")
        encoded_pass = urllib.parse.quote(password, safe="")
        userinfo = f"{encoded_user}:{encoded_pass}@" if password else f"{encoded_user}@"
    return f"http://{userinfo}{host}:{port}"


def mask_proxy_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    if parsed.username:
        user = urllib.parse.quote(parsed.username, safe="")
        netloc = f"{user}:***@{host}{port}"
    else:
        netloc = f"{host}{port}"
    return f"{parsed.scheme}://{netloc}"


def _warn_socks_deps(scheme: str) -> None:
    if not scheme.startswith("socks"):
        return
    missing: list[str] = []
    try:
        import socks  # noqa: F401
    except ImportError:
        missing.append("PySocks")
    try:
        import socksio  # noqa: F401
    except ImportError:
        missing.append("socksio")
    if missing:
        console.print(
            f"[yellow]warning: {scheme} proxy requires: pip install {' '.join(missing)}[/yellow]"
        )


def register(app: typer.Typer) -> None:
    group = typer.Typer(help="steam-cli settings")
    app.add_typer(group, name="config")

    proxy_group = typer.Typer(help="Configure an HTTP(S)/SOCKS proxy for all Steam requests")
    group.add_typer(proxy_group, name="proxy")

    @proxy_group.command("set")
    def proxy_set(
        proxy_url: str = typer.Argument(
            None, help="e.g. http://user:pass@127.0.0.1:7890"
        ),
        host: str = typer.Option(None, "--host", help="proxy host"),
        port: int = typer.Option(None, "--port", help="proxy port"),
        username: str = typer.Option(None, "--username", help="proxy user (optional)"),
        password: str = typer.Option(None, "--password", help="proxy password (optional)"),
    ):
        """Set the proxy (either a full URL or --host/--port)."""
        if proxy_url and host:
            raise InvalidFormatError("provide either a proxy URL or --host/--port, not both")
        if not proxy_url and not host:
            raise InvalidFormatError("provide a proxy URL or --host/--port")
        if host and not port:
            raise InvalidFormatError("--host requires --port")
        url = (
            validate_proxy_url(proxy_url)
            if proxy_url
            else build_proxy_url(host, port, username or "", password or "")
        )
        _warn_socks_deps(urllib.parse.urlparse(url).scheme)
        auth.set_proxy(url)
        console.print(f"[green]Proxy set:[/green] {mask_proxy_url(url)}")

    @proxy_group.command("show")
    def proxy_show():
        """Show the configured proxy (password masked)."""
        url = auth.get_proxy()
        if not url:
            console.print("No proxy configured.")
            return
        console.print(mask_proxy_url(url))

    @proxy_group.command("unset")
    def proxy_unset():
        """Remove the configured proxy."""
        auth.clear_proxy()
        console.print("Proxy cleared.")

    @proxy_group.command("test")
    def proxy_test():
        """Verify the configured proxy can reach Steam."""
        url = auth.get_proxy()
        if not url:
            console.print("[yellow]No proxy configured.[/yellow]")
            raise typer.Exit(code=1)
        try:
            with httpx.Client(proxy=url, timeout=15) as client:
                resp = client.get(_TEST_URL)
        except httpx.HTTPError as exc:
            console.print(f"[red]proxy test failed:[/red] {exc.__class__.__name__}: {exc}")
            raise typer.Exit(code=1)
        if resp.status_code == 200:
            console.print(
                f"[green]Proxy works[/green] ({_TEST_URL} -> HTTP {resp.status_code})"
            )
        else:
            console.print(f"[red]proxy test failed:[/red] HTTP {resp.status_code}")
            raise typer.Exit(code=1)
