import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from steam_cli.commands.wishlist import WISHLIST_API, _wishlist_modify, wishlist_appids


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        if self._payload is None:
            raise ValueError("not JSON")
        return self._payload


class FakeSession:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.last = None
        self.gets = []

    def post(self, url, data=None, timeout=0):
        self.last = (url, data)
        resp = FakeResponse()
        resp.status_code = self.status_code
        return resp

    def get(self, url, params=None, timeout=0):
        self.gets.append((url, params))
        return FakeResponse(200, {"response": {"items": [{"appid": 1144200}, {"appid": 2358720}]}})


def test_wishlist_modify_sends_appid_and_sessionid():
    fs = FakeSession()
    result = _wishlist_modify(
        fs, "https://store.steampowered.com/api/addtowishlist", 2358720, "sid123"
    )
    assert result == "ok"
    assert fs.last is not None
    _url, data = fs.last
    assert data == {"appid": 2358720, "sessionid": "sid123"}


def test_wishlist_modify_forbidden():
    fs = FakeSession(status_code=403)
    result = _wishlist_modify(fs, "https://x", 1, "s")
    assert result == "forbidden"


def test_wishlist_appids_uses_iwishlistservice(monkeypatch):
    """radar/recommend share this path; the old wishlistdata endpoint is dead."""
    session = FakeSession()
    monkeypatch.setattr("steam_cli.commands.wishlist.auth.require_session", lambda: session)
    monkeypatch.setattr("steam_cli.commands.wishlist.auth.require_steam_id", lambda: "7656")
    monkeypatch.setattr("steam_cli.commands.wishlist.auth.get_api_key", lambda: "key123")

    appids = wishlist_appids()

    assert appids == [1144200, 2358720]
    assert session.gets, "expected a GET against the wishlist API"
    url, params = session.gets[0]
    assert url == WISHLIST_API
    assert params == {"steamid": "7656", "key": "key123"}
