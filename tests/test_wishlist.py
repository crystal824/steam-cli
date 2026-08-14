import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


from steam_cli.commands.wishlist import _wishlist_modify


class FakeResponse:
    status_code = 200


class FakeSession:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.last = None

    def post(self, url, data=None, timeout=0):
        self.last = (url, data)
        resp = FakeResponse()
        resp.status_code = self.status_code
        return resp


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
