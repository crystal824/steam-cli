"""Steam review commands."""

from __future__ import annotations

import html
import re
import time

import httpx
import requests
import typer
from rich.console import Console
from rich.table import Table

from .. import auth
from ..errors import (
    InvalidFormatError,
    NetworkError,
    ReviewRejectedError,
    SessionExpiredError,
)
from .wishlist import _app_names

console = Console()

# Reviews are published by the store front-end helper main.js::RecommendGame:
#   $J.post("https://store.steampowered.com/friends/recommendgame", params)
#   params = {appid, steamworksappid, comment, rated_up, is_public, language,
#             received_compensation, disable_comments, saved_hardware_id, sessionid}
#   -> {"success": true} | {"success": false, "strError": "..."}
#
# The URL this module used before (.../profiles/<steamid>/recommended/) is only a
# page: POSTing to it answers HTTP 200 with HTML and saves nothing, so the
# command printed "Review posted." while publishing nothing at all.
REVIEW_POST_URL = "https://store.steampowered.com/friends/recommendgame"
REVIEWS_URL = "https://store.steampowered.com/appreviews/{appid}"
MY_REVIEWS_URL = "https://steamcommunity.com/profiles/{steamid}/recommended/"

# Steam refuses a review for a product with under 5 minutes on record ("You need
# to have used this product for at least 5 minutes ..."), surfaced via strError.
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

_MIN_REVIEW_LEN = 12
_BANNED_WORDS = (
    "nigger",
    "faggot",
    "retard",
    "cunt",
    "spic",
    "kike",
)
# Word-boundary matching: plain substring checks also matched banned words
# embedded in ordinary words (e.g. "retard" inside "retardant", "spic" inside
# "despicable"/"conspicuous"), rejecting clean reviews as false positives.
_BANNED_WORDS_RE = re.compile(
    r"\b(" + "|".join(re.escape(word) for word in _BANNED_WORDS) + r")\b", re.IGNORECASE
)


def filter_review_text(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return "review is empty"
    if len(stripped) < _MIN_REVIEW_LEN:
        return f"review is too short ({len(stripped)} characters; minimum {_MIN_REVIEW_LEN})"
    if _BANNED_WORDS_RE.search(stripped):
        return "review contains a disallowed word"
    return None


def _post_payload(
    appid: str,
    text: str,
    recommend: bool,
    language: str,
    private: bool,
    sessionid: str,
) -> dict[str, str]:
    """The exact params main.js::RecommendGame sends (booleans as jQuery strings)."""
    return {
        "appid": str(appid),
        "steamworksappid": str(appid),
        "comment": text,
        "rated_up": "true" if recommend else "false",
        "is_public": "false" if private else "true",
        "language": language,
        "received_compensation": "0",
        "disable_comments": "0",
        "saved_hardware_id": "",
        "sessionid": sessionid,
    }


def _post_review(
    session: requests.Session,
    appid: str,
    text: str,
    *,
    recommend: bool = True,
    language: str = "schinese",
    private: bool = False,
) -> str:
    """Publish the review; raises a typed error on anything but a real success."""
    payload = _post_payload(
        appid, text, recommend, language, private, auth.cookie_value(session, "sessionid")
    )
    headers = {
        "User-Agent": _UA,
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://store.steampowered.com",
        "Referer": f"https://store.steampowered.com/app/{appid}/",
    }
    try:
        resp = session.post(REVIEW_POST_URL, data=payload, headers=headers, timeout=25)
    except requests.RequestException as exc:
        raise NetworkError(detail=str(exc))
    if resp.status_code in (401, 403):
        raise SessionExpiredError(detail=f"HTTP {resp.status_code} from {REVIEW_POST_URL}")
    if resp.status_code != 200:
        raise NetworkError(detail=f"HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError:
        # An HTML body on this URL means the endpoint moved again. Never report
        # success on it -- that is exactly how this command used to lie.
        raise NetworkError(
            detail=f"{REVIEW_POST_URL} answered HTTP 200 with a non-JSON body; "
            "the endpoint may have moved"
        )
    if data.get("success"):
        return "recommended" if recommend else "not recommended"
    error_text = str(data.get("strError") or "").strip()
    if not error_text:
        # No success and no strError: Steam did not accept the session.
        raise SessionExpiredError()
    raise ReviewRejectedError(error_text)


def _strip_tags(raw: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", raw))).strip()


def parse_my_reviews(page: str) -> list[dict]:
    """Review blocks on a profile's /recommended/ page."""
    out: list[dict] = []
    for block in re.split(r'<div class="review_box', page)[1:]:
        appid = re.search(r"/app/(\d+)", block)
        text = re.search(r'<div class="content\s*">(.*?)</div>', block, re.DOTALL)
        posted = re.search(r"Posted ([^<]+)<", block)
        hours = re.search(r"([\d.]+) hrs on record", block)
        visibility = re.search(r'class="trigger"[^>]*>\s*([A-Za-z]+)\s*</button>', block)
        if "Not Recommended" in block:
            verdict = "not recommended"
        elif "Recommended" in block:
            verdict = "recommended"
        else:
            verdict = "unknown"
        out.append(
            {
                "appid": appid.group(1) if appid else "",
                "verdict": verdict,
                "text": _strip_tags(text.group(1)) if text else "",
                "posted": posted.group(1).strip() if posted else "",
                "hours": f"{hours.group(1)}h" if hours else "",
                "visibility": visibility.group(1) if visibility else "",
            }
        )
    return out


def my_reviews(session: requests.Session, steamid: str) -> list[dict]:
    """Reviews the account has posted, read from its own profile page.

    The public appreviews feed cannot answer "my review": it only returns the
    newest page of a game's feed (Elden Ring has >1M reviews) and filters by
    language, so a `--mine` filter over it silently never matched.
    """
    url = MY_REVIEWS_URL.format(steamid=steamid)
    try:
        resp = session.get(url, headers={"User-Agent": _UA}, timeout=20)
    except requests.RequestException as exc:
        raise NetworkError(detail=str(exc))
    if resp.status_code != 200:
        raise NetworkError(detail=f"HTTP {resp.status_code} reading {url}")
    reviews = parse_my_reviews(resp.text)
    if not reviews and steamid not in resp.text:
        # A logged-out page also answers 200 and has no review blocks; do not
        # report "you have no reviews" for it.
        raise SessionExpiredError(detail=f"{url} did not look like your own profile page")
    return reviews


def _format_ts(value: object) -> str:
    if not isinstance(value, (int, str)):
        return ""
    try:
        return time.strftime("%Y-%m-%d", time.localtime(int(value)))
    except (TypeError, ValueError):
        return ""


def _print_my_table(
    reviews: list[dict], *, title: str, names: dict[int, str] | None = None
) -> None:
    table = Table(title=title)
    table.add_column("Game")
    table.add_column("Verdict")
    table.add_column("Posted")
    table.add_column("Playtime")
    table.add_column("Visibility")
    table.add_column("Review")
    for r in reviews:
        appid = str(r["appid"])
        name = names.get(int(appid), "") if (names and appid.isdigit()) else ""
        text = str(r["text"])
        if len(text) > 80:
            text = text[:80] + "…"
        table.add_row(
            name or f"app {appid}",
            str(r["verdict"]),
            str(r["posted"]),
            str(r["hours"]),
            str(r["visibility"]),
            text,
        )
    console.print(table)


def register(app: typer.Typer) -> None:
    group = typer.Typer()
    app.add_typer(group, name="review")

    @group.command()
    def post(
        appid: str,
        text: str = typer.Option(..., "--text", help="Review body"),
        recommend: bool = typer.Option(True, "--recommend/--not-recommend"),
        language: str = typer.Option(
            "schinese",
            "--language",
            "-L",
            help="Language the text is written in (steam code: schinese, english, ...)",
        ),
        private: bool = typer.Option(False, "--private", help="Post with 'Private' visibility"),
        verify: bool = typer.Option(
            True, "--verify/--no-verify", help="Read your reviews back after posting"
        ),
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview only"),
    ):
        """Post a review for a game (Steam requires >=5 minutes of playtime)."""
        session = auth.require_session()
        steamid = auth.require_steam_id()
        reason = filter_review_text(text)
        if reason:
            raise InvalidFormatError(reason)
        if dry_run:
            console.print(f"[yellow]dry-run[/yellow] would POST {REVIEW_POST_URL}")
            preview = _post_payload(appid, text, recommend, language, private, "<redacted>")
            for key, value in preview.items():
                console.print(f"  {key} = {value}")
            return
        try:
            verdict = _post_review(
                session, appid, text, recommend=recommend, language=language, private=private
            )
        except ReviewRejectedError as exc:
            auth.log_audit("review.post", appid, f"rejected:{exc.message[:80]}")
            raise
        except SessionExpiredError:
            auth.log_audit("review.post", appid, "rejected:session")
            raise
        auth.log_audit("review.post", appid, f"ok:{verdict}")
        console.print(f"[green]Review posted.[/green] app {appid} ({verdict})")
        if verify:
            hit = next((r for r in my_reviews(session, steamid) if r["appid"] == str(appid)), None)
            if hit:
                console.print(
                    f"[green]Verified[/green] on your profile: {hit['verdict']} · "
                    f"{hit['posted']} · {hit['visibility']}"
                )
            else:
                console.print(
                    "[yellow]Not on your profile yet[/yellow] — that page can lag a little; "
                    "re-check with `steam review mine`."
                )

    @group.command("list")
    def list_reviews(
        appid: str,
        mine: bool = typer.Option(False, "--mine", help="Only your own review for this app"),
        language: str = typer.Option("english", "--language", "-L", help="Language, or 'all'"),
        limit: int = typer.Option(20, "--limit", "-n", help="How many reviews (1-100)"),
    ):
        """List recent public reviews for a game."""
        if mine:
            session = auth.require_session()
            steamid = auth.require_steam_id()
            hits = [r for r in my_reviews(session, steamid) if r["appid"] == str(appid)]
            if not hits:
                console.print(
                    f"no review by you for app {appid}; `steam review mine` lists all of them"
                )
                return
            _print_my_table(hits, title=f"Your review for app {appid}")
            return
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.get(
                    REVIEWS_URL.format(appid=appid),
                    params={
                        "json": "1",
                        "language": language,
                        "filter": "recent",
                        "purchase_type": "all",
                        "num_per_page": str(max(1, min(limit, 100))),
                    },
                    headers={"User-Agent": _UA},
                )
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise NetworkError(detail=str(exc))
        reviews = data.get("reviews", [])
        if not reviews:
            console.print("no reviews found")
            return
        table = Table(title=f"Reviews for app {appid}")
        table.add_column("Author")
        table.add_column("Recommended")
        table.add_column("Posted")
        table.add_column("Review")
        for r in reviews:
            author = r.get("author", {}).get("steamid", "")
            text = (r.get("review", "") or "").replace("\n", " ").strip()
            if len(text) > 120:
                text = text[:120] + "…"
            table.add_row(
                str(author),
                "yes" if r.get("voted_up") else "no",
                _format_ts(r.get("timestamp_created")),
                text,
            )
        console.print(table)

    @group.command("mine")
    def my_reviews_cmd():
        """List every review you have posted (with game names when cached)."""
        session = auth.require_session()
        steamid = auth.require_steam_id()
        reviews = my_reviews(session, steamid)
        if not reviews:
            console.print("you have not posted any reviews")
            return
        names = _app_names(session, [int(r["appid"]) for r in reviews if str(r["appid"]).isdigit()])
        _print_my_table(reviews, title="Your Steam reviews", names=names)
