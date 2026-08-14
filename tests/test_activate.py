import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from steam_cli.commands.activate import _activate_key, _raise_for_result
from steam_cli.errors import (
    AlreadyActivatedError,
    EndpointUnavailableError,
    InvalidKeyError,
    NetworkError,
    RegionLockedError,
)


class FakeResponse:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


class FakeSession:
    def __init__(self, status_code=200, text=""):
        self.response = FakeResponse(status_code, text)

    def post(self, *args, **kwargs):
        return self.response


def test_activate_already_activated():
    session = FakeSession(
        200, "This product code has already been activated by a different account"
    )
    assert _activate_key(session, "K", "s") == "already_activated"


def test_activate_already_owns():
    session = FakeSession(200, "Sorry, you already own this product.")
    assert _activate_key(session, "K", "s") == "already_activated"


def test_activate_invalid():
    session = FakeSession(200, "This product code is not valid or is incomplete.")
    assert _activate_key(session, "K", "s") == "invalid"


def test_activate_region_locked():
    session = FakeSession(200, "This product key is not available in your country.")
    assert _activate_key(session, "K", "s") == "region_locked"


def test_activate_unknown_page_is_not_ok():
    session = FakeSession(200, "<html>some unrelated page content</html>")
    assert _activate_key(session, "K", "s") == "unknown"


def test_activate_http_error():
    session = FakeSession(500, "")
    assert _activate_key(session, "K", "s") == "http:500"


def test_raise_for_result_mapping():
    with pytest.raises(AlreadyActivatedError):
        _raise_for_result("already_activated", "K")
    with pytest.raises(RegionLockedError):
        _raise_for_result("region_locked", "K")
    with pytest.raises(InvalidKeyError):
        _raise_for_result("invalid", "K")
    with pytest.raises(NetworkError):
        _raise_for_result("rate_limited", "K")
    with pytest.raises(EndpointUnavailableError):
        _raise_for_result("unknown", "K")
    with pytest.raises(NetworkError):
        _raise_for_result("http:500", "K")


def test_raise_for_result_ok_noop():
    _raise_for_result("ok", "K")
