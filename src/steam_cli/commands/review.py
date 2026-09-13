"""Steam review commands."""

from __future__ import annotations

import html
import json
import re
import time

import httpx
import requests
import typer
from rich.console import Console
from rich.table import Table

from .. import auth, region
from ..client import resolve_appid, resolve_name
from ..errors import (
    InvalidFormatError,
    NetworkError,
    ReviewRejectedError,
    SessionExpiredError,
    SteamError,
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
        # Judge from the thumb icon first: the profile page renders in the account's
        # language (a Chinese account gets 推荐/不推荐), while the icon file names do
        # not move. 不推荐 must be tested before 推荐 -- it contains it.
        if "icon_thumbsDown" in block or "Not Recommended" in block or "不推荐" in block:
            verdict = "not recommended"
        elif "icon_thumbsUp" in block or "Recommended" in block or "推荐" in block:
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
        # `l=english` is deliberate: this page is parsed as HTML, and a session whose
        # Steam_Language is not English renders it in that language ("发布于", "小时",
        # "可见性"), which would silently blank the date/playtime/visibility columns.
        # The verdict does not depend on it any more (see parse_my_reviews).
        resp = session.get(url, params={"l": "english"}, headers={"User-Agent": _UA}, timeout=20)
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


# Steam's own review-score bands (query_summary.review_score) and the wording the
# Chinese store shows for them. 0 means "not enough reviews to score".
_SCORE_ZH = {
    0: "评测不足",
    1: "差评如潮",
    2: "特别差评",
    3: "差评",
    4: "多半差评",
    5: "褒贬不一",
    6: "多半好评",
    7: "好评",
    8: "特别好评",
    9: "好评如潮",
}
# Review language codes -> 中文 label, for the sample listing.
_LANG_ZH = {
    "arabic": "阿拉伯语",
    "brazilian": "葡语(巴西)",
    "bulgarian": "保加利亚语",
    "czech": "捷克语",
    "danish": "丹麦语",
    "dutch": "荷兰语",
    "english": "英语",
    "finnish": "芬兰语",
    "french": "法语",
    "german": "德语",
    "greek": "希腊语",
    "hungarian": "匈牙利语",
    "indonesian": "印尼语",
    "italian": "意大利语",
    "japanese": "日语",
    "koreana": "韩语",
    "latam": "西语(拉美)",
    "norwegian": "挪威语",
    "polish": "波兰语",
    "portuguese": "葡语",
    "romanian": "罗马尼亚语",
    "russian": "俄语",
    "schinese": "中文",
    "spanish": "西语",
    "swedish": "瑞典语",
    "tchinese": "繁中",
    "thai": "泰语",
    "turkish": "土耳其语",
    "ukrainian": "乌克兰语",
    "vietnamese": "越南语",
}
# BBCode the store wraps review text in; only the words matter for a digest.
_BBCODE_RE = re.compile(
    r"\[/?(?:b|i|u|s|strike|h1|h2|h3|p|list|olist|\*|table|tr|td|th|quote|code|noparse|spoiler"
    r"|hr|url|img|video|previewyoutube|previewfile)(?:=[^\]]{0,300})?\]",
    re.IGNORECASE,
)
_WINDOW_CAP = 400
_SAMPLE_LIMIT = 200


def _int_or(value: object, default: int = 0) -> int:
    if not isinstance(value, (int, float, str)):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def score_label(review_score: object, desc: str = "") -> str:
    """`9` + "Overwhelmingly Positive" -> "好评如潮 (Overwhelmingly Positive)"."""
    zh = _SCORE_ZH.get(_int_or(review_score, -1))
    english = (desc or "").strip()
    if not zh:
        return english or "unknown"
    if not english or english.lower() in zh.lower():
        return zh
    return f"{zh} ({english})"


def strip_bbcode(text: str) -> str:
    # The appreviews API double-escapes newlines ("\n" arrives as backslash + n),
    # so normalise those before anything else looks at the text.
    raw = re.sub(r"\\r\\n|\\n|\\r", "\n", text or "")
    return re.sub(r"[ \t]{2,}", " ", _BBCODE_RE.sub(" ", raw)).strip()


def one_line(text: str, limit: int = _SAMPLE_LIMIT) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def lang_label(code: str) -> str:
    return _LANG_ZH.get((code or "").lower(), code or "?")


def _api_get(client: httpx.Client, appid: object, params: dict[str, str]) -> dict:
    try:
        resp = client.get(
            REVIEWS_URL.format(appid=appid), params=params, headers={"User-Agent": _UA}
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise NetworkError(detail=str(exc))
    if not isinstance(data, dict):
        raise NetworkError(detail=f"unexpected reply from {REVIEWS_URL.format(appid=appid)}")
    return data


def fetch_summary(client: httpx.Client, appid: object, *, language: str = "all") -> dict:
    """Overall review score: {review_score, review_score_desc, totals}."""
    return (
        _api_get(
            client,
            appid,
            {
                "json": "1",
                "language": language,
                "purchase_type": "all",
                "num_per_page": "0",
                "filter": "all",
            },
        ).get("query_summary")
        or {}
    )


def fetch_reviews(
    client: httpx.Client,
    appid: object,
    *,
    language: str = "all",
    review_type: str = "all",
    limit: int = 20,
    filter_by: str = "all",
    cursor: str = "",
) -> tuple[list[dict], str]:
    """One page of reviews (helpfulness order when filter_by="all"); returns (reviews, cursor)."""
    params = {
        "json": "1",
        "language": language,
        "purchase_type": "all",
        "filter": filter_by,
        "review_type": review_type,
        "num_per_page": str(max(1, min(limit, 100))),
    }
    if cursor:
        params["cursor"] = cursor
    data = _api_get(client, appid, params)
    return list(data.get("reviews") or []), str(data.get("cursor") or "")


def sample_recent(
    client: httpx.Client,
    appid: object,
    *,
    language: str = "all",
    days: int,
    cap: int = _WINDOW_CAP,
) -> dict:
    """Walk the newest reviews until `days` back, and count the positive share.

    Steam retired the `day_range` parameter (it answers the all-time summary no
    matter what), so the recent picture is sampled client-side: `filter=recent`
    returns newest-first, which makes "stop when older than the cut-off" exact —
    unless the window holds more than `cap` reviews, which sets `truncated`.

    The first page is requested with `cursor=*` (start of the list): without an
    explicit cursor Steam answers with a single "featured" review on some titles.
    """
    cutoff = int(time.time()) - days * 86400
    seen = positive = 0
    cursor = ""
    truncated = False
    seen_ids: set[str] = set()
    while seen < cap:
        batch, cursor = fetch_reviews(
            client,
            appid,
            language=language,
            filter_by="recent",
            limit=min(100, cap - seen),
            cursor=cursor or "*",
        )
        if not batch:
            break
        reached_cutoff = False
        fresh = 0
        for review in batch:
            key = str(review.get("recommendationid") or "")
            if key:
                if key in seen_ids:
                    continue
                seen_ids.add(key)
            fresh += 1
            if _int_or(review.get("timestamp_created")) < cutoff:
                reached_cutoff = True
                continue
            seen += 1
            if review.get("voted_up"):
                positive += 1
        # A cursor that stopped advancing would otherwise spin until `cap`.
        if reached_cutoff or not cursor or not fresh:
            break
        if seen >= cap:
            truncated = True
            break
    return {
        "days": days,
        "sampled": seen,
        "positive": positive,
        "pct": round(positive / seen * 100, 1) if seen else None,
        "truncated": truncated,
    }


def sample_review(review: dict) -> dict:
    author = review.get("author") or {}
    return {
        "votes_up": _int_or(review.get("votes_up")),
        "voted_up": bool(review.get("voted_up")),
        "language": review.get("language") or "",
        "playtime_hours": round(_int_or(author.get("playtime_forever")) / 60, 1),
        "text": one_line(strip_bbcode(review.get("review") or ""), _SAMPLE_LIMIT),
        "timestamp": _int_or(review.get("timestamp_created")),
        "steam_purchase": bool(review.get("steam_purchase")),
        "refunded": bool(review.get("refunded")),
    }


def collect_samples(
    client: httpx.Client, appid: object, *, language: str = "all", want: int = 8
) -> dict:
    """Up to `want` most-helpful 好评 and 差评 samples.

    Nothing here trusts Steam's parameters, because on this endpoint they are not
    trustworthy for obscure titles (measured 2026-09-13 on Wenjia, 374 reviews):

    - `filter=all` ("最有帮助" order) can be all but empty -- it ranked exactly ONE
      review there, which is how the first version of this command managed to report
      "8 条" while showing a single sample. A `filter=recent` page is merged in.
    - `review_type=positive` is not honoured consistently (a "negative" request once
      answered with three up-voted reviews). The split is done here from each
      review's own `voted_up` instead.
    """
    pool: dict[str, dict] = {}

    def absorb(batch: list[dict]) -> None:
        for review in batch:
            key = str(review.get("recommendationid") or "") or f"anonymous-{len(pool)}"
            pool.setdefault(key, review)

    # 1) Steam's "most helpful" ranking. Thin or empty on obscure titles.
    batch, _ = fetch_reviews(
        client, appid, language=language, review_type="all", limit=100, filter_by="all"
    )
    absorb(batch)
    # 2) The newest page (complete and chronological) -- this is what makes small
    #    games work at all. `cursor=*` starts at the top of the list; without an
    #    explicit cursor Steam sometimes answers with one "featured" review.
    batch, cursor = fetch_reviews(
        client,
        appid,
        language=language,
        review_type="all",
        limit=100,
        filter_by="recent",
        cursor="*",
    )
    absorb(batch)
    # 3) One more page of the newest reviews, only if Steam handed us a cursor.
    if cursor:
        batch, _ = fetch_reviews(
            client,
            appid,
            language=language,
            review_type="all",
            limit=100,
            filter_by="recent",
            cursor=cursor,
        )
        absorb(batch)
    sides: dict[str, list[dict]] = {"positive": [], "negative": []}
    for review in pool.values():
        sides["positive" if review.get("voted_up") else "negative"].append(review)
    for side, rows in sides.items():
        rows.sort(
            key=lambda r: (_int_or(r.get("votes_up")), _int_or(r.get("timestamp_created"))),
            reverse=True,
        )
        sides[side] = [sample_review(r) for r in rows[:want]]
    return sides


def review_digest(
    appid: object,
    *,
    language: str = "all",
    samples: int = 8,
    days: int = 30,
) -> dict:
    """Everything a summary needs: the score, the recent picture, and samples."""
    with httpx.Client(timeout=25) as client:
        summary = fetch_summary(client, appid, language=language)
        digest: dict = {
            "appid": str(appid),
            "language": language,
            "overall": {
                "score": _int_or(summary.get("review_score")),
                "label": score_label(
                    summary.get("review_score"), str(summary.get("review_score_desc") or "")
                ),
                "positive": _int_or(summary.get("total_positive")),
                "negative": _int_or(summary.get("total_negative")),
                "total": _int_or(summary.get("total_reviews")),
            },
            "recent": None,
            "samples": {"positive": [], "negative": []},
        }
        total = digest["overall"]["total"]
        if total:
            digest["overall"]["pct"] = round(digest["overall"]["positive"] / total * 100, 1)
        if days > 0:
            digest["recent"] = sample_recent(client, appid, language=language, days=days)
        if samples > 0 and total:
            digest["samples"] = collect_samples(client, appid, language=language, want=samples)
    return digest


def register(app: typer.Typer) -> None:
    group = typer.Typer()
    app.add_typer(group, name="review")

    @group.command()
    def post(
        appid: str,
        text: str = typer.Option(..., "--text", help="Review body"),
        recommend: bool = typer.Option(True, "--recommend/--not-recommend"),
        language: str = typer.Option(
            None,
            "--language",
            "-L",
            help="Language the text is written in (default: your store language)",
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
        language = language or region.language()
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
        language: str = typer.Option(
            None, "--language", "-L", help="Language, or 'all' (default: your store language)"
        ),
        limit: int = typer.Option(20, "--limit", "-n", help="How many reviews (1-100)"),
    ):
        """List recent public reviews for a game."""
        language = language or region.language()
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
        table = Table(title=f"Reviews for app {appid} · language={language}")
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

    @group.command("summary")
    def summary(
        appid: str = typer.Argument(..., help="AppID or game title"),
        language: str = typer.Option("all", "--language", "-L", help="Language, or 'all'"),
        samples: int = typer.Option(
            8, "--samples", "-s", help="Positive/negative samples (0 = none)"
        ),
        days: int = typer.Option(30, "--days", "-d", help="Recent window in days (0 = skip)"),
        as_json: bool = typer.Option(False, "--json", help="Machine-readable output"),
    ):
        """Review score (好评如潮 / 褒贬不一 …) plus most-helpful pros/cons samples."""
        resolved = resolve_appid(appid)
        try:
            name = resolve_name(int(resolved))
        except SteamError:
            name = str(resolved)
        digest = review_digest(resolved, language=language, samples=samples, days=days)
        digest["name"] = name

        if as_json:
            # soft_wrap: rich would otherwise fold the long lines itself and put raw
            # newlines inside JSON strings, which makes the output unparseable.
            console.print(
                json.dumps(digest, ensure_ascii=False, indent=2),
                markup=False,
                highlight=False,
                soft_wrap=True,
            )
            return

        overall = digest["overall"]
        console.print(f"[bold]{name}[/bold] ({resolved})", soft_wrap=True)
        if not overall["total"]:
            console.print("  暂无评测", soft_wrap=True)
            return
        console.print(
            f"  总评：{overall['label']} — 好评率 {overall.get('pct', 0)}%"
            f"（好评 {overall['positive']:,} / 差评 {overall['negative']:,}，共 {overall['total']:,} 条）",
            soft_wrap=True,
        )
        recent = digest["recent"]
        if recent is not None:
            if recent["sampled"]:
                basis = (
                    f"最新 {recent['sampled']} 条（窗口内评测更多，未全量）"
                    if recent["truncated"]
                    else f"全部 {recent['sampled']} 条"
                )
                console.print(
                    f"  近期：近 {recent['days']} 天 {basis}，好评率 {recent['pct']}%",
                    soft_wrap=True,
                )
            else:
                console.print(f"  近期：近 {recent['days']} 天没有新评测", soft_wrap=True)
        console.print(f"  样本语言筛选：{language}", soft_wrap=True)
        for kind, title in (("positive", "好评"), ("negative", "差评")):
            rows = digest["samples"][kind]
            console.print(f"\n[bold]{title}样本[/bold]（Steam 最有帮助排序，{len(rows)} 条）")
            if not rows:
                console.print("  （无）", markup=False)
                continue
            for index, row in enumerate(rows, 1):
                label = lang_label(row["language"])
                console.print(
                    f"  {index}. 👍{row['votes_up']} · {label} · {row['playtime_hours']}h · {row['text']}",
                    markup=False,
                    soft_wrap=True,
                )
