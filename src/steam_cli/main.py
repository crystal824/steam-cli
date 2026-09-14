"""typer entrypoint for steam-cli."""

from __future__ import annotations

import sys

import typer
from rich.console import Console

from . import auth, modern_login, region
from .errors import NotAuthenticatedError, SteamError

app = typer.Typer(
    name="steam",
    help="Operate a Steam account safely: search, library, wishlist, CDK activation, reviews, friends.",
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=False,
)
console = Console()


@app.command()
def login(
    username: str = typer.Option(None, "--username", "-u", help="Steam account name"),
    code: str = typer.Option(
        None, "--code", help="Steam Guard code (omit to approve in the Steam app instead)"
    ),
):
    """Log in through Steam's current web flow (app approval or Steam Guard code)."""

    def progress(**event: object) -> None:
        step = str(event.get("step") or "")
        if step == "guard":
            console.print(f"[yellow]{event.get('note')}[/yellow]")
        elif step == "guard_code":
            console.print("Steam Guard code submitted; waiting for Steam…")
        elif step == "settoken" and event.get("result") == 1:
            console.print(f"  [dim]minted {str(event.get('url')).split('/')[2]}[/dim]")

    result = modern_login.login(username=username, code=code, save=True, on_event=progress)
    auth.log_audit("auth.login", result["username"], "ok")
    console.print(
        f"[green]Logged in as {result['username']}[/green] "
        f"(SteamID {result['steam_id']}, store session verified)"
    )


@app.command()
def status():
    """Show current auth state."""
    s = auth.status()
    rows = [("Login", "yes" if s["logged_in"] else "no")]
    if s["username"]:
        rows.append(("Username", s["username"]))
        rows.append(("SteamID", s["steam_id"] or "unknown"))
        rows.append(("Session valid", "yes" if s["session_valid"] else "no"))
    rows.append(("Web API key", "set" if s["api_key"] else "not set"))
    if s["api_key"]:
        rows.append(("API key valid", "yes" if s["api_key_valid"] else "no"))
    for k, v in rows:
        console.print(f"{k}: {v}")
    info = region.region_info()
    console.print(
        f"Region: {info['country']} ({info['language']})"
        + (f" [dim]— {info['source']}[/dim]" if info["source"] else "")
    )


@app.command()
def logout():
    """Clear the saved login session."""
    auth.clear_session()
    auth.log_audit("auth.logout", "-", "ok")
    console.print("Logged out.")


@app.command("set-key")
def set_key(
    web_api_key: str = typer.Argument(
        ..., help="Web API key from https://steamcommunity.com/dev/apikey"
    ),
):
    """Store a Web API key for read-only queries."""
    auth.set_api_key(web_api_key)
    console.print("Web API key saved.")


@app.command()
def refresh(
    remint: bool = typer.Option(
        False,
        "--remint",
        help="Re-authenticate from the stored refresh token (no password, no 2FA)",
    ),
):
    """Check the saved session; `--remint` rebuilds it from the refresh token."""
    if remint:
        result = modern_login.remint_session(save=True)
        auth.log_audit("auth.remint", result["username"] or "-", "ok")
        console.print(
            f"[green]Session re-minted[/green] "
            f"(SteamID {result['steam_id']}, store session verified)"
        )
        return
    if not auth.is_logged_in():
        raise NotAuthenticatedError()
    if auth.is_session_valid():
        console.print("Session is still valid.")
    else:
        console.print(
            "[yellow]Session has expired.[/yellow] Rebuild it with `steam refresh --remint` "
            "(no password needed) or sign in again with `steam login`."
        )
        raise NotAuthenticatedError()


@app.command("revoke-all")
def revoke_all():
    """Emergency wipe of all locally stored credentials (key, session, refresh token, proxy)."""
    auth.clear_api_key()
    auth.clear_session()
    auth.clear_refresh_token()
    auth.clear_proxy()
    auth.log_audit("auth.revoke-all", "-", "ok")
    console.print("All local credentials cleared.")


@app.command()
def doctor():
    """Probe the availability of non-official endpoints."""
    from .utils.doctor import run_doctor

    run_doctor()


from .commands import (
    achievements,
    activate,
    config,
    friends,
    launch,
    library,
    recommend,
    review,
    stats,
    store,
    wishlist,
)

for _mod in (
    store,
    library,
    wishlist,
    friends,
    review,
    activate,
    stats,
    launch,
    recommend,
    achievements,
    config,
):
    _mod.register(app)


def main() -> None:
    auth.apply_proxy()
    try:
        app()
    except SteamError as exc:
        console.print(f"[bold red]{exc.code}[/bold red]: {exc.message}")
        if exc.detail:
            console.print(f"[dim]{exc.detail}[/dim]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("[yellow]Aborted.[/yellow]")
        sys.exit(130)


if __name__ == "__main__":
    main()
