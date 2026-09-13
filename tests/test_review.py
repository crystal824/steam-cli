import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

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
