import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import re

import pytest

from steam_cli.client import resolve_appid
from steam_cli.commands import review
from steam_cli.commands.activate import validate_cdk_format
from steam_cli.commands.review import filter_review_text
from steam_cli.errors import (
    AlreadyActivatedError,
    InvalidFormatError,
)


def test_cdk_3x5_valid():
    assert validate_cdk_format("ABCDE-12345-ZYXWV") is True


def test_cdk_5x5_valid():
    assert validate_cdk_format("ABCDE-FGHIJ-KLMNO-PQRST-UVWXY") is True


def test_cdk_invalid_short():
    assert validate_cdk_format("ABCDE-1234") is False


def test_cdk_invalid_chars():
    assert validate_cdk_format("ABC!E-12345-ZYXWV") is False


def test_cdk_invalid_empty():
    assert validate_cdk_format("") is False


def test_resolve_appid_by_id():
    assert resolve_appid("2358720") == 2358720


def test_review_filter_ok():
    assert filter_review_text("A very fun game with great combat.") is None


def test_review_filter_empty():
    assert filter_review_text("") is not None


def test_review_filter_allows_words_containing_banned_substrings():
    # Regression: plain substring matching used to reject these because
    # "retard" sits inside "retardant" and "spic" sits inside "despicable"/
    # "conspicuous" -- neither is actually a banned word on its own.
    assert (
        filter_review_text("The flame-retardant walls make for a despicable villain lair.") is None
    )
    assert filter_review_text("A conspicuous but auspicious start to the campaign.") is None


def test_review_filter_still_blocks_whole_word_matches(monkeypatch):
    # Verify the matching *mechanism* (word boundaries) without hardcoding a
    # real slur into the test suite: swap in a synthetic banned word.
    monkeypatch.setattr(review, "_BANNED_WORDS_RE", re.compile(r"\b(bogus)\b", re.IGNORECASE))
    assert filter_review_text("this game is a bogus mess and not worth it") is not None
    assert filter_review_text("this game has a bogusword typo but is otherwise fine") is None


def test_error_types():
    err = AlreadyActivatedError()
    assert err.code == "already_activated"
    assert InvalidFormatError().code == "invalid_format"


def test_resolve_appid_sends_cjk_titles_to_the_chinese_store_search(monkeypatch):
    """The community SearchApps index answers [] for 艾尔登法环 and can even return
    a knock-off for 黑神话; the Chinese store search returns the real app."""
    from steam_cli import client

    calls: list[tuple[str, dict]] = []

    def fake_store_search(term, lang="english", cc="us"):
        calls.append((term, {"lang": lang, "cc": cc}))
        return [{"appid": 2358720, "name": "黑神话：悟空"}] if lang == "schinese" else []

    monkeypatch.setattr(client, "_store_search", fake_store_search)
    monkeypatch.setattr(client, "_search_apps", lambda term: [])
    client.resolve_appid.cache_clear()
    try:
        assert client.resolve_appid("黑神话") == 2358720
        assert calls[0] == ("黑神话", {"lang": "schinese", "cc": "cn"})
    finally:
        client.resolve_appid.cache_clear()


def test_resolve_appid_keeps_english_terms_on_the_community_search(monkeypatch):
    from steam_cli import client

    monkeypatch.setattr(client, "_search_apps", lambda term: [{"appid": 2807960, "name": "BF6"}])
    monkeypatch.setattr(
        client, "_store_search", lambda *a, **kw: pytest.fail("should not hit storesearch")
    )
    client.resolve_appid.cache_clear()
    try:
        assert client.resolve_appid("Battlefield") == 2807960
    finally:
        client.resolve_appid.cache_clear()
