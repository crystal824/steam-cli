"""Steam review commands."""

from __future__ import annotations

import httpx
import requests
import typer
from rich.console import Console
from rich.table import Table

from .. import auth
from ..errors import (
    ForbiddenError,
    InvalidFormatError,
    NetworkError,
    SessionExpiredError,
)

console = Console()

REVIEW_POST_URL = "https://steamcommunity.com/profiles/{steamid}/recommended/"
REVIEWS_URL = "https://store.steampowered.com/appreviews/{appid}"

_MIN_REVIEW_LEN = 12
_BANNED_WORDS = (
    "nigger",
    "faggot",
    "retard",
    "cunt",
    "spic",
    "kike",
)


def filter_review_text(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return "review is empty"
    if len(stripped) < _MIN_REVIEW_LEN:
        return f"review is too short ({len(stripped)} characters; minimum {_MIN_REVIEW_LEN})"
    lowered = stripped.lower()
    for word in _BANNED_WORDS:
        if word in lowered:
            return "review contains a disallowed word"
    return None


def register(app: typer.Typer) -> None:
    group = typer.Typer()
    app.add_typer(group, name="review")

    @group.command()
    def post(
        appid: str,
        text: str = typer.Option(..., "--text", help="Review body"),
        recommend: bool = typer.Option(True, "--recommend/--not-recommend"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview only"),
    ):
        """Post a review for a game."""
        session = auth.require_session()
        steamid = auth.require_steam_id()
        reason = filter_review_text(text)
        if reason:
            raise InvalidFormatError(reason)
        if dry_run:
            verdict = "recommended" if recommend else "not recommended"
            console.print(
                f"[yellow]dry-run[/yellow] would post a '{verdict}' review for app {appid}:"
            )
            console.print(f"  {text}")
            return
        sessionid = session.cookies.get("sessionid") or ""
        url = REVIEW_POST_URL.format(steamid=steamid)
        data = {
            "appid": appid,
            "review_text": text,
            "recommendation": "recommended" if recommend else "notrecommended",
            "sessionid": sessionid,
            "json": "1",
        }
        try:
            resp = session.post(url, data=data, timeout=20)
        except requests.RequestException as exc:
            raise NetworkError(detail=str(exc))
        if resp.status_code == 401:
            raise SessionExpiredError()
        if resp.status_code == 403:
            raise ForbiddenError(
                "review post was rejected (403); the session may be expired or the "
                "review flagged — re-login and try again"
            )
        if resp.status_code != 200:
            raise NetworkError(detail=f"HTTP {resp.status_code}")
        console.print("[green]Review posted.[/green]")
        auth.log_audit("review.post", appid, "ok")

    @group.command("list")
    def list_reviews(
        appid: str,
        mine: bool = typer.Option(False, "--mine", help="Only show your own reviews"),
    ):
        """List recent public reviews for a game."""
        url = REVIEWS_URL.format(appid=appid)
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(
                    url,
                    params={
                        "json": "1",
                        "language": "english",
                        "filter": "recent",
                        "purchase_type": "all",
                    },
                    headers={"User-Agent": "steam-cli/0.1"},
                )
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise NetworkError(detail=str(exc))
        reviews = data.get("reviews", [])
        if mine:
            steamid = auth.require_steam_id()
            reviews = [r for r in reviews if str(r.get("author", {}).get("steamid")) == steamid]
        if not reviews:
            console.print("no reviews found")
            return
        table = Table(title=f"Reviews for app {appid}")
        table.add_column("Author")
        table.add_column("Recommended")
        table.add_column("Review")
        for r in reviews:
            author = r.get("author", {}).get("steamid", "")
            text = (r.get("review", "") or "").replace("\n", " ").strip()
            if len(text) > 120:
                text = text[:120] + "…"
            table.add_row(
                str(author),
                "yes" if r.get("voted_up") else "no",
                text,
            )
        console.print(table)
