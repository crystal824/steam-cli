import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import json  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import requests  # noqa: E402
from steam.steamid import SteamID  # noqa: E402

from steam_cli import auth  # noqa: E402


class FakeKeyring:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


def make_fixture(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(auth, "_keyring_get", fake.get)
    monkeypatch.setattr(auth, "_keyring_set", fake.set)
    monkeypatch.setattr(auth, "_keyring_delete", fake.delete)
    auth._invalidate_status()
    return fake


def test_session_roundtrip_preserves_domains(monkeypatch):
    make_fixture(monkeypatch)
    session = requests.Session()
    session.cookies.set("sessionid", "abc123", domain="store.steampowered.com", path="/")
    session.cookies.set("steamLoginSecure", "token", domain="steamcommunity.com", path="/")
    wa = SimpleNamespace(session=session, session_id="sid", steam_id=SteamID(76561198000000000))
    auth.save_session(wa, "tester")

    state = auth.load_session()
    assert state is not None
    assert state.username == "tester"
    assert state.steam_id == "76561198000000000"

    restored = auth.restore_webauth(state)
    domains = {c.domain for c in restored.session.cookies if c.name == "sessionid"}
    assert domains == {"store.steampowered.com"}
    assert restored.session.cookies.get("steamLoginSecure") == "token"


def test_domainless_cookies_bind_to_steam_domains(monkeypatch):
    make_fixture(monkeypatch)
    session = requests.Session()
    session.cookies.set("hostonly", "x", path="/")
    wa = SimpleNamespace(session=session, session_id="sid", steam_id=None)
    auth.save_session(wa, "tester")

    restored = auth.restore_webauth(auth.load_session())
    domains = {c.domain for c in restored.session.cookies if c.name == "hostonly"}
    assert "steamcommunity.com" in domains
    assert "store.steampowered.com" in domains


def test_legacy_cookie_format_still_loads(monkeypatch):
    fake = make_fixture(monkeypatch)
    fake.set(auth.KEY_SESSION, json.dumps({"sessionid": "oldvalue"}))
    fake.set(auth.KEY_USERNAME, "tester")
    state = auth.load_session()
    assert state is not None
    assert state.cookies["sessionid"] == [{"value": "oldvalue", "domain": "", "path": "/"}]


def test_status_cached_and_invalidated(monkeypatch):
    fake = make_fixture(monkeypatch)
    first = auth.status()
    second = auth.status()
    assert first is second
    auth.set_api_key("testkey")
    third = auth.status()
    assert third is not first
