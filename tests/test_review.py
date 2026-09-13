import itertools
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import httpx
import pytest

from steam_cli.commands import review
from steam_cli.commands.review import (
    REVIEW_POST_URL,
    _post_payload,
    _post_review,
    parse_my_reviews,
)
from steam_cli.errors import NetworkError, ReviewRejectedError, SessionExpiredError


class FakeResponse:
    """recommendgame answers JSON; the retired page URL answers HTML."""

    def __init__(self, status_code=200, text="", payload=None):
        self.status_code = status_code
        self.text = text
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("response is not JSON")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.cookies = {"sessionid": "sid123"}
        self.last_post = None

    def post(self, *args, **kwargs):
        self.last_post = (args, kwargs)
        return self.response

    def get(self, *args, **kwargs):
        self.last_post = (args, kwargs)
        return self.response


def test_post_uses_the_recommendgame_endpoint_and_frontend_field_names():
    """Regression: .../profiles/<steamid>/recommended/ is only a page -- a POST
    there returns HTTP 200 + HTML and saves nothing, which is how the command
    used to print "Review posted." without publishing anything."""
    session = FakeSession(FakeResponse(200, payload={"success": True}))
    assert _post_review(session, "1867240", "A solid co-op shooter.", language="english") == (
        "recommended"
    )
    url, kwargs = session.last_post[0][0], session.last_post[1]
    assert url == REVIEW_POST_URL
    data = kwargs["data"]
    assert data["appid"] == data["steamworksappid"] == "1867240"
    assert data["comment"] == "A solid co-op shooter."
    assert data["rated_up"] == "true"
    assert data["is_public"] == "true"
    assert data["language"] == "english"
    assert data["sessionid"] == "sid123"
    assert "review_text" not in data and "recommendation" not in data
    assert kwargs["headers"]["X-Requested-With"] == "XMLHttpRequest"


def test_post_payload_flags():
    payload = _post_payload("1", "text", False, "english", True, "sid")
    assert payload["rated_up"] == "false"
    assert payload["is_public"] == "false"


def test_post_html_body_is_never_reported_as_success():
    session = FakeSession(FakeResponse(200, "<html>Activate a Product on Steam</html>"))
    with pytest.raises(NetworkError):
        _post_review(session, "1", "some review text here")


def test_post_strerror_becomes_review_rejected():
    session = FakeSession(
        FakeResponse(
            200,
            payload={
                "success": False,
                "strError": "You need to have used this product for at least 5 minutes "
                "before posting a review for it (0 minutes on record).",
            },
        )
    )
    with pytest.raises(ReviewRejectedError) as exc:
        _post_review(session, "1", "some review text here")
    assert exc.value.code == "review_rejected"
    assert "5 minutes" in exc.value.message


def test_post_failure_without_strerror_is_treated_as_a_session_problem():
    session = FakeSession(FakeResponse(200, payload={"success": False}))
    with pytest.raises(SessionExpiredError):
        _post_review(session, "1", "some review text here")


def test_post_http_error():
    session = FakeSession(FakeResponse(500, ""))
    with pytest.raises(NetworkError):
        _post_review(session, "1", "some review text here")


PAGE = """
<div class="review_box_content">
  <div class="leftcol"><a href="https://steamcommunity.com/app/2358720"></a></div>
  <div class="rightcol">
    <div class="vote_header"><div class="title"><a href="x">Recommended</a></div>
      <div class="hours"> 122.2 hrs on record (10.9 hrs at review time) </div></div>
    <div class="content ">黑神话悟空就像巧克力，人吃了高兴！</div>
    <div class="posted"> Posted 21 August, 2024. </div>
    <button type="button" class="trigger" id="V1_trigger">Public</button>
  </div>
</div>
<div class="review_box_content">
  <div class="leftcol"><a href="https://steamcommunity.com/app/1006510"></a></div>
  <div class="rightcol">
    <div class="vote_header"><div class="title"><a href="y">Not Recommended</a></div>
      <div class="hours"> 0.1 hrs on record </div></div>
    <div class="content ">Short &amp; not for me</div>
    <div class="posted"> Posted 22 February, 2019. </div>
    <button type="button" class="trigger" id="V2_trigger">Private</button>
  </div>
</div>
"""


def test_parse_my_reviews_reads_every_field():
    got = parse_my_reviews(PAGE)
    assert [r["appid"] for r in got] == ["2358720", "1006510"]
    assert got[0]["verdict"] == "recommended"
    assert got[0]["text"] == "黑神话悟空就像巧克力，人吃了高兴！"
    assert got[0]["posted"] == "21 August, 2024."
    assert got[0]["hours"] == "122.2h"
    assert got[0]["visibility"] == "Public"
    assert got[1]["verdict"] == "not recommended"
    assert got[1]["text"] == "Short & not for me"
    assert got[1]["hours"] == "0.1h"
    assert got[1]["visibility"] == "Private"


def test_my_reviews_raises_when_the_page_is_not_yours():
    session = FakeSession(FakeResponse(200, "<html>Sign in to Steam</html>"))
    with pytest.raises(SessionExpiredError):
        review.my_reviews(session, "76561198121699884")


def test_my_reviews_accepts_a_genuinely_empty_profile():
    session = FakeSession(
        FakeResponse(200, "<html>profile 76561198121699884 has no reviews</html>")
    )
    assert review.my_reviews(session, "76561198121699884") == []


# --------------------------------------------------------------------------- #
# review summary (score band, recent window sampling, pros/cons samples)
# --------------------------------------------------------------------------- #


class FakeClient:
    """Stands in for httpx.Client: answers queued responses, records requests."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    def get(self, url, params=None, headers=None):
        self.requests.append({"url": url, "params": params or {}})
        return self._responses.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def summary_payload(score=5, desc="Mixed", positive=100, negative=60):
    return {
        "query_summary": {
            "review_score": score,
            "review_score_desc": desc,
            "total_positive": positive,
            "total_negative": negative,
            "total_reviews": positive + negative,
        }
    }


def review_payload(reviews, cursor=""):
    return {"reviews": reviews, "cursor": cursor}


_RID = itertools.count(1)


def a_review(voted_up=True, votes_up=10, when=0, text="fine", language="schinese"):
    return {
        "recommendationid": str(next(_RID)),
        "voted_up": voted_up,
        "votes_up": votes_up,
        "language": language,
        "timestamp_created": when,
        "review": text,
        "author": {"playtime_forever": 600},
    }


def test_score_label_maps_steam_bands():
    assert review.score_label(9, "Overwhelmingly Positive") == "好评如潮 (Overwhelmingly Positive)"
    assert review.score_label("5", "Mixed") == "褒贬不一 (Mixed)"
    assert review.score_label(6, "Mostly Positive") == "多半好评 (Mostly Positive)"
    assert review.score_label(0, "Need more user reviews to generate a score").startswith(
        "评测不足"
    )
    # unknown band: fall back to whatever Steam said rather than inventing a label
    assert review.score_label(None, "Mixed") == "Mixed"


def test_strip_bbcode_and_one_line():
    assert review.strip_bbcode("[b]good[/b] [url=http://x]link[/url] [*]item") == "good link item"
    assert review.one_line("a  b\n\nc", 40) == "a b c"
    assert review.one_line("abcdefgh", 5) == "abcd…"


def test_lang_label_known_and_unknown():
    assert review.lang_label("schinese") == "中文"
    assert review.lang_label("english") == "英语"
    assert review.lang_label("klingon") == "klingon"


def test_fetch_summary_asks_for_the_all_time_summary():
    client = FakeClient([FakeResponse(200, payload=summary_payload())])
    got = review.fetch_summary(client, "2807960", language="all")
    assert got["review_score"] == 5 and got["total_reviews"] == 160
    params = client.requests[0]["params"]
    assert params["num_per_page"] == "0" and params["filter"] == "all"
    assert client.requests[0]["url"].endswith("/appreviews/2807960")


def test_fetch_reviews_passes_review_type_and_cursor():
    client = FakeClient([FakeResponse(200, payload=review_payload([a_review()], cursor="NEXT"))])
    reviews, cursor = review.fetch_reviews(
        client, "1", review_type="negative", limit=500, filter_by="all", cursor="PREV"
    )
    params = client.requests[0]["params"]
    assert params["review_type"] == "negative"
    assert params["num_per_page"] == "100"  # clamped to Steam's maximum
    assert params["cursor"] == "PREV"
    assert cursor == "NEXT" and len(reviews) == 1


def test_sample_recent_counts_only_reviews_inside_the_window():
    now = int(time.time())
    page = [
        a_review(voted_up=True, when=now - 3600),
        a_review(voted_up=False, when=now - 7200),
        a_review(voted_up=True, when=now - 40 * 86400),  # older than the window
    ]
    client = FakeClient([FakeResponse(200, payload=review_payload(page, cursor="MORE"))])
    got = review.sample_recent(client, "1", language="all", days=30)
    assert got["sampled"] == 2 and got["positive"] == 1 and got["pct"] == 50.0
    assert got["truncated"] is False
    assert len(client.requests) == 1  # stopped at the cut-off, no extra page fetched


def test_sample_recent_reports_truncation_when_the_window_is_too_big():
    now = int(time.time())
    page = [a_review(when=now - 60) for _ in range(3)]
    client = FakeClient([FakeResponse(200, payload=review_payload(page, cursor="MORE"))])
    got = review.sample_recent(client, "1", language="all", days=30, cap=2)
    assert got["sampled"] == 3 and got["truncated"] is True


def test_sample_review_extracts_display_fields():
    row = review.sample_review(
        {
            "voted_up": False,
            "votes_up": 916,
            "language": "schinese",
            "review": "[b]bad[/b]  balance\n\nis broken",
            "timestamp_created": 1700000000,
            "steam_purchase": True,
            "refunded": False,
            "author": {"playtime_forever": 24893},
        }
    )
    assert row["votes_up"] == 916 and row["voted_up"] is False
    assert row["text"] == "bad balance is broken"
    assert row["playtime_hours"] == 414.9
    assert row["language"] == "schinese"


def test_review_digest_assembles_overall_recent_and_samples(monkeypatch):
    now = int(time.time())
    client = FakeClient(
        [
            FakeResponse(200, payload=summary_payload(5, "Mixed", 100, 60)),
            # recent window: one review inside it, no further cursor
            FakeResponse(200, payload=review_payload([a_review(True, when=now - 60)], cursor="")),
            # collect_samples: helpfulness page (poor on obscure titles), then recent
            FakeResponse(200, payload=review_payload([a_review(True, votes_up=42)], cursor="")),
            FakeResponse(200, payload=review_payload([], cursor="")),
        ]
    )
    monkeypatch.setattr(review.httpx, "Client", lambda *a, **kw: client)
    digest = review.review_digest("2807960", language="all", samples=1, days=30)
    assert digest["overall"]["label"] == "褒贬不一 (Mixed)"
    assert digest["overall"]["pct"] == 62.5
    assert digest["recent"]["sampled"] == 1 and digest["recent"]["pct"] == 100.0
    assert len(digest["samples"]["positive"]) == 1
    assert digest["samples"]["positive"][0]["votes_up"] == 42


def test_collect_samples_splits_by_voted_up_and_ranks_by_votes():
    """Regression: the samples used to be labelled by request (`review_type=positive`)
    instead of by each review's own `voted_up`, so a page of down-voted reviews could
    be presented as "好评". Steam does not honour review_type consistently."""
    page = [
        a_review(True, votes_up=5, text="up-5"),
        a_review(False, votes_up=900, text="down-900"),
        a_review(True, votes_up=99, text="up-99"),
    ]
    client = FakeClient(
        [
            FakeResponse(200, payload=review_payload(page, cursor="")),
            FakeResponse(200, payload=review_payload([], cursor="")),
        ]
    )
    sides = review.collect_samples(client, "1", language="all", want=1)
    assert [r["text"] for r in sides["positive"]] == ["up-99"]
    assert [r["text"] for r in sides["negative"]] == ["down-900"]


def test_collect_samples_recovers_from_an_empty_helpfulness_list():
    """Wenjia (374 reviews) ranks exactly ONE review under filter=all, while
    filter=recent returns a full page — merging the two is what makes small games work."""
    helpful = [a_review(True, votes_up=3, text="featured")]
    recent = [
        a_review(True, votes_up=99, text="newest-up"),
        a_review(False, votes_up=13, text="newest-down"),
    ]
    client = FakeClient(
        [
            FakeResponse(200, payload=review_payload(helpful, cursor="")),
            FakeResponse(200, payload=review_payload(recent, cursor="")),
        ]
    )
    sides = review.collect_samples(client, "933450", language="all", want=1)
    assert [r["text"] for r in sides["positive"]] == ["newest-up"]
    assert [r["text"] for r in sides["negative"]] == ["newest-down"]


def test_sample_recent_stops_when_the_cursor_stops_advancing():
    """Steam can answer with the same single review + the same cursor forever; without
    this guard the sampler would spin until the 400-review cap."""
    now = int(time.time())
    stuck = review_payload([a_review(True, when=now - 60)], cursor="SAME")
    client = FakeClient([FakeResponse(200, payload=stuck), FakeResponse(200, payload=stuck)])
    got = review.sample_recent(client, "1", language="all", days=30)
    assert got["sampled"] == 1  # counted once, not once per page
    assert len(client.requests) == 2  # second page added nothing -> stop


def test_sample_recent_asks_the_first_page_to_start_at_the_top_of_the_list():
    now = int(time.time())
    client = FakeClient(
        [FakeResponse(200, payload=review_payload([a_review(when=now - 60)], cursor=""))]
    )
    review.sample_recent(client, "1", language="all", days=30)
    assert client.requests[0]["params"]["cursor"] == "*"


CHINESE_PAGE = """
<div class="review_box_content">
  <div class="rightcol">
    <div class="vote_header">
      <a href="x"><img src=".../userreviews/icon_thumbsUp.png"></a>
      <div class="title"><a href="x">推荐</a></div>
      <div class="hours"> 122.2 小时（评测时 10.9 小时） </div>
    </div>
    <div class="content ">黑神话悟空就像巧克力，人吃了高兴！</div>
    <div class="posted"> 发布于 2024 年 8 月 21 日 </div>
    <button type="button" class="trigger" id="V_trigger">公开</button>
  </div>
</div>
<div class="review_box_content">
  <div class="rightcol">
    <div class="vote_header">
      <a href="y"><img src=".../userreviews/icon_thumbsDown.png"></a>
      <div class="title"><a href="y">不推荐</a></div>
    </div>
    <div class="content ">失望</div>
  </div>
</div>
"""


def test_parse_my_reviews_reads_verdicts_from_the_icons_not_the_language():
    """Regression: the page renders in the account's Steam language, so the English
    words ("Recommended", "Posted") disappear for a Chinese account. The thumb icon
    file names do not move, so the verdict is taken from those."""
    got = parse_my_reviews(CHINESE_PAGE)
    assert [r["appid"] for r in got] == ["", ""]  # no /app/ links in this fixture
    assert got[0]["verdict"] == "recommended"
    assert got[0]["text"] == "黑神话悟空就像巧克力，人吃了高兴！"
    assert got[1]["verdict"] == "not recommended"  # not swallowed by the 推荐 substring


def test_my_reviews_asks_for_the_english_rendering():
    """The date/playtime/visibility columns are parsed from English labels, so the
    request pins `l=english` instead of trusting the session's Steam_Language."""
    page = '<div class="review_box_content"><div class="content ">x</div></div>'
    session = FakeSession(FakeResponse(200, page))
    review.my_reviews(session, "76561198121699884")
    _, kwargs = session.last_post
    assert kwargs["params"] == {"l": "english"}
