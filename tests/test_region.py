import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from steam_cli import region

USERINFO_PAGE = (
    '<div id="account_pulldown" data-userinfo="{&quot;logged_in&quot;:true,'
    '&quot;country_code&quot;:&quot;CN&quot;,&quot;excluded_content_descriptors&quot;:[3,4]}"></div>'
)


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(region, "CACHE_FILE", tmp_path / "region.json")
    monkeypatch.delenv("STEAM_CLI_CC", raising=False)
    monkeypatch.delenv("STEAM_CLI_LANG", raising=False)
    yield


def test_parse_country_reads_the_userinfo_blob():
    assert region.parse_country(USERINFO_PAGE) == "cn"
    assert region.parse_country('"country_code": "JP"') == "jp"
    assert region.parse_country("") is None
    assert region.parse_country("<html>no userinfo here</html>") is None


def test_language_follows_the_country(monkeypatch):
    monkeypatch.setattr(region, "detected_country", lambda **kw: ("cn", "account"))
    assert region.country() == "cn"
    assert region.language() == "schinese"
    assert region.store_params({"term": "x"}) == {"cc": "cn", "l": "schinese", "term": "x"}


def test_unknown_country_falls_back_to_english(monkeypatch):
    monkeypatch.setattr(region, "detected_country", lambda **kw: ("zz", "account"))
    assert region.language() == "english"


def test_explicit_override_beats_detection(monkeypatch):
    monkeypatch.setattr(region, "detected_country", lambda **kw: ("cn", "account"))
    monkeypatch.setenv("STEAM_CLI_CC", "JP")
    monkeypatch.setenv("STEAM_CLI_LANG", "english")
    assert region.country() == "jp"
    # An explicit language wins over the country -> language mapping.
    assert region.language() == "english"
    assert region.store_params() == {"cc": "jp", "l": "english"}


def test_call_site_language_wins_over_the_default(monkeypatch):
    monkeypatch.setattr(region, "detected_country", lambda **kw: ("cn", "account"))
    assert region.store_params({"l": "english", "cc": "cn"}) == {"cc": "cn", "l": "english"}


def test_detection_is_cached_and_reused(monkeypatch):
    calls: list[int] = []

    def fake_fetch():
        calls.append(1)
        return "cn"

    monkeypatch.setattr(region, "fetch_account_country", fake_fetch)
    monkeypatch.setattr(region.auth, "is_logged_in", lambda: True)
    assert region.detected_country() == ("cn", "account")
    assert region.detected_country() == ("cn", "account")  # served from the cache
    assert len(calls) == 1


def test_no_session_falls_back_to_the_default(monkeypatch):
    monkeypatch.setattr(region.auth, "is_logged_in", lambda: False)
    assert region.detected_country() == (None, "anonymous")
    assert region.country() == "us"
    assert region.language() == "english"


def test_set_and_clear_region(monkeypatch):
    monkeypatch.setattr(region.auth, "is_logged_in", lambda: False)
    region.set_region("jp", "japanese")
    assert (region.country(), region.language()) == ("jp", "japanese")
    region.clear_region()
    assert region.country() == "us"


def test_region_info_reports_the_source(monkeypatch):
    monkeypatch.setattr(region, "detected_country", lambda **kw: ("cn", "account"))
    info = region.region_info()
    assert info["source"] == "account"
    assert (info["country"], info["language"]) == ("cn", "schinese")


def test_explicit_none_does_not_unset_the_resolved_region(monkeypatch):
    """Regression: `steam price` passed cc=None down the stack and the merge let it
    clobber the resolved country, so no cc/l was sent at all and Steam answered from
    the proxy's IP (CDN$ instead of ¥)."""
    monkeypatch.setattr(region, "detected_country", lambda **kw: ("cn", "account"))
    assert region.store_params({"cc": None, "l": None}) == {"cc": "cn", "l": "schinese"}
    assert region.store_params({"appids": 1144200, "cc": None}) == {
        "cc": "cn",
        "l": "schinese",
        "appids": "1144200",
    }
