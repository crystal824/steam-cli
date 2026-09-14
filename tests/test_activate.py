import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from steam_cli.commands.activate import (
    _activate_batch,
    _activate_key,
    _mask_key,
    _raise_for_result,
)
from steam_cli.errors import (
    AlreadyActivatedError,
    EndpointUnavailableError,
    InvalidKeyError,
    NetworkError,
    RegionLockedError,
)


class FakeResponse:
    """Steam's ajaxregisterkey answers JSON; rejection paths may answer HTML."""

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


def receipt(name):
    return {
        "success": 1,
        "purchase_receipt_info": {"line_items": [{"line_item_description": name}]},
    }


def rejected(code):
    return {"success": 0, "purchase_result_details": code}


def test_activate_success_returns_product_name():
    session = FakeSession(FakeResponse(200, payload=receipt("SAMPLE GAME (CN)")))
    assert _activate_key(session, "K", "sid123") == ("ok", "SAMPLE GAME (CN)")


def test_activate_posts_to_ajax_endpoint_with_xhr_headers():
    """Regression: /account/registerkey is only the HTML form page; the real
    endpoint is /account/ajaxregisterkey/ and it needs the XHR headers."""
    session = FakeSession(FakeResponse(200, payload=receipt("X")))
    _activate_key(session, "K", "sid123")
    args, kwargs = session.last_post
    assert args[0].endswith("/account/ajaxregisterkey/")
    assert kwargs["data"] == {"product_key": "K", "sessionid": "sid123"}
    assert kwargs["headers"]["X-Requested-With"] == "XMLHttpRequest"


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (15, "already_activated"),
        (9, "already_owned"),
        (14, "invalid"),
        (13, "region_locked"),
        (53, "rate_limited"),
        (24, "base_game_required"),
        (4, "retry_later"),
        (999, "unknown"),
    ],
)
def test_activate_maps_purchase_result_codes(code, expected):
    session = FakeSession(FakeResponse(200, payload=rejected(code)))
    assert _activate_key(session, "K", "s") == (expected, None)


def test_activate_non_json_phrases_still_map():
    session = FakeSession(
        FakeResponse(
            200, "<html>This product code has already been activated by a different account</html>"
        )
    )
    assert _activate_key(session, "K", "s") == ("already_activated", None)


def test_activate_unknown_page_is_not_ok():
    session = FakeSession(FakeResponse(200, "<html>some unrelated page content</html>"))
    assert _activate_key(session, "K", "s") == ("unknown", None)


def test_activate_http_error():
    session = FakeSession(FakeResponse(500, ""))
    assert _activate_key(session, "K", "s") == ("http:500", None)


def test_raise_for_result_mapping():
    with pytest.raises(AlreadyActivatedError):
        _raise_for_result("already_activated")
    with pytest.raises(AlreadyActivatedError):
        _raise_for_result("already_owned")
    with pytest.raises(RegionLockedError):
        _raise_for_result("region_locked")
    with pytest.raises(InvalidKeyError):
        _raise_for_result("invalid")
    with pytest.raises(InvalidKeyError):
        _raise_for_result("base_game_required")
    with pytest.raises(NetworkError):
        _raise_for_result("rate_limited")
    with pytest.raises(NetworkError):
        _raise_for_result("retry_later")
    with pytest.raises(NetworkError):
        _raise_for_result("http:500")
    with pytest.raises(EndpointUnavailableError):
        _raise_for_result("unknown")


def test_raise_for_result_ok_noop():
    _raise_for_result("ok")


def test_activate_batch_logs_masked_key_not_raw_key(monkeypatch, tmp_path):
    from steam_cli import auth

    raw_key = "ABCDE-12345-ZYXWV"
    batch_file = tmp_path / "keys.txt"
    batch_file.write_text(raw_key + "\n")

    logged: list[tuple[str, str, str]] = []
    session = FakeSession(FakeResponse(200, "<html>you already own this product</html>"))
    monkeypatch.setattr(auth, "require_session", lambda: session)
    monkeypatch.setattr(auth, "log_audit", lambda *args: logged.append(args))
    monkeypatch.setattr("builtins.input", lambda *_: "y")  # in case confirm falls back to input

    _activate_batch(str(batch_file), dry_run=False, yes=True)

    assert len(logged) == 1
    _command, target, _result = logged[0]
    assert target == _mask_key(raw_key)
    assert raw_key not in target
