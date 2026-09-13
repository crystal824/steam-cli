"""The modern Steam login flow (what `steam login` now drives).

Everything here is offline: the HTTP layer is faked, so the tests pin the *shape* of
the flow — the fields Steam expects, the mandatory `steamID` in the settoken bodies,
and what gets persisted — without touching a real account.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
import requests

from steam_cli import auth, modern_login
from steam_cli.errors import LoginFailedError

RSA_KEY = {"publickey_mod": "b" * 64, "publickey_exp": "010001", "timestamp": "1700000000"}


class FakeResponse:
    def __init__(self, status_code=200, payload=None, url=""):
        self.status_code = status_code
        self._payload = payload
        self.url = url
        self.headers: dict = {}
        self.cookies: list = []

    def json(self):
        if self._payload is None:
            raise ValueError("response is not JSON")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    """Hands out queued responses and records every request that was made."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []
        self.headers: dict = {}
        self.cookies: list = []

    def _next(self, method, url, **kwargs):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "params": kwargs.get("params"),
                "data": kwargs.get("data"),
            }
        )
        return self._responses.pop(0)

    def get(self, url, **kwargs):
        return self._next("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self._next("POST", url, **kwargs)


def test_begin_auth_session_sends_what_steam_expects(monkeypatch):
    posted: list[tuple[str, dict]] = []
    encrypted_with: list[str] = []
    monkeypatch.setattr(modern_login, "_api_get", lambda *a, **kw: dict(RSA_KEY))

    def fake_encrypt(_mod, _exp, password):
        encrypted_with.append(password)
        return "ENCRYPTED"

    monkeypatch.setattr(modern_login, "encrypt_password", fake_encrypt)

    def fake_post(_session, method, payload):
        posted.append((method, payload))
        return {
            "client_id": "CID",
            "request_id": "RID",
            "steamid": "76561198121699884",
            "interval": 4.5,
            "allowed_confirmations": [
                {"confirmation_type": 2},
                {"confirmation_type": 3},
            ],
        }

    monkeypatch.setattr(modern_login, "_api_post", fake_post)
    began = modern_login.begin_auth_session(FakeSession([]), "someone", "hunter2")

    method, payload = posted[0]
    assert method == "BeginAuthSessionViaCredentials"
    assert payload["account_name"] == "someone"
    assert payload["encrypted_password"] == "ENCRYPTED"
    assert encrypted_with == ["hunter2"]  # the password reached the encryptor, not the wire
    assert payload["encryption_timestamp"] == 1700000000  # from the RSA response, as int
    assert payload["remember_login"] is True and payload["persistence"] == 1
    assert payload["device_friendly_name"] == "steam-cli"
    # the password itself must never be posted in the clear
    assert "hunter2" not in str(payload)
    assert began["confirmation_types"] == [2, 3]
    assert began["interval"] == 4.5


def test_begin_auth_session_reports_a_refusal_without_retrying(monkeypatch):
    monkeypatch.setattr(modern_login, "_api_get", lambda *a, **kw: dict(RSA_KEY))
    monkeypatch.setattr(modern_login, "encrypt_password", lambda *a: "ENC")
    monkeypatch.setattr(modern_login, "_api_post", lambda *a, **kw: {})
    with pytest.raises(LoginFailedError):
        modern_login.begin_auth_session(FakeSession([]), "someone", "wrong")


def test_begin_auth_session_needs_an_rsa_key(monkeypatch):
    monkeypatch.setattr(modern_login, "_api_get", lambda *a, **kw: {})
    with pytest.raises(LoginFailedError):
        modern_login.begin_auth_session(FakeSession([]), "someone", "pw")


def test_poll_returns_as_soon_as_tokens_arrive(monkeypatch):
    answers = [{}, {}, {"refresh_token": "RT", "access_token": "AT"}]
    monkeypatch.setattr(modern_login, "_api_post", lambda *a, **kw: answers.pop(0))
    slept: list[float] = []
    clock = iter([0.0, 1.0, 2.0, 3.0])
    began = {"client_id": "CID", "request_id": "RID", "interval": 5}

    polled = modern_login.poll_for_tokens(
        FakeSession([]), began, sleep=slept.append, now=lambda: next(clock)
    )
    assert polled["refresh_token"] == "RT"
    assert slept == [5.0, 5.0]  # interval from Steam, floored at 3s


def test_poll_times_out_with_an_actionable_message(monkeypatch):
    monkeypatch.setattr(modern_login, "_api_post", lambda *a, **kw: {})
    times = iter([0.0, 100.0, 400.0])
    with pytest.raises(LoginFailedError) as exc:
        modern_login.poll_for_tokens(
            FakeSession([]),
            {"client_id": "C", "request_id": "R", "interval": 5},
            timeout=180,
            sleep=lambda _s: None,
            now=lambda: next(times),
        )
    assert "mobile app" in exc.value.detail or "approve" in exc.value.message.lower()


def test_settoken_bodies_must_carry_steamid(monkeypatch):
    """Regression: without `steamID` Steam answers {"result": 8} and mints no cookie,
    which is exactly how the old flow "logged in" and authenticated nothing."""
    transfer = [
        {
            "url": "https://store.steampowered.com/login/settoken",
            "params": {"nonce": "n", "auth": "a"},
        },
        {"url": "https://steamcommunity.com/login/settoken", "params": {"nonce": "n", "auth": "a"}},
    ]
    session = FakeSession(
        [
            FakeResponse(200, payload={"result": 1, "rtExpiry": 1789386302}),
            FakeResponse(200, payload={"result": 1, "rtExpiry": 1789386261}),
        ]
    )
    results = modern_login.apply_transfers(session, transfer, "76561198121699884")
    assert len(results) == 2
    for call in session.calls:
        assert call["data"]["steamID"] == "76561198121699884"
        assert call["data"]["nonce"] == "n"
    assert results[0]["result"] == 1 and results[0]["rtExpiry"] == 1789386302


def test_finalize_login_rejects_a_non_json_body():
    session = FakeSession([FakeResponse(200, payload=None)])
    with pytest.raises(LoginFailedError):
        modern_login.finalize_login(session, "RT", "sid")


def test_finalize_login_rejects_missing_transfers():
    session = FakeSession([FakeResponse(200, payload={"steamID": "123"})])
    with pytest.raises(LoginFailedError):
        modern_login.finalize_login(session, "RT", "sid")


def _login_session(*, store_status=200, community_status=302):
    return FakeSession(
        [
            FakeResponse(
                200,
                payload={
                    "steamID": "76561198121699884",
                    "transfer_info": [
                        {
                            "url": "https://store.steampowered.com/login/settoken",
                            "params": {"nonce": "n"},
                        },
                    ],
                },
            ),
            FakeResponse(200, payload={"result": 1, "rtExpiry": 1789386302}),
            FakeResponse(store_status),
            FakeResponse(community_status),
        ]
    )


def test_login_runs_the_flow_and_persists_the_session(monkeypatch):
    monkeypatch.setattr(modern_login, "_api_get", lambda *a, **kw: dict(RSA_KEY))
    monkeypatch.setattr(modern_login, "encrypt_password", lambda *a: "ENC")
    monkeypatch.setattr(
        modern_login,
        "_api_post",
        lambda _s, method, payload: {
            "BeginAuthSessionViaCredentials": {
                "client_id": "CID",
                "request_id": "RID",
                "steamid": "76561198121699884",
                "interval": 0,
                "allowed_confirmations": [{"confirmation_type": 3}],
            },
            "UpdateAuthSessionWithSteamGuardCode": {},
            "PollAuthSessionStatus": {"refresh_token": "RT"},
        }[method],
    )
    saved: list[dict] = []
    monkeypatch.setattr(
        modern_login,
        "persist",
        lambda session, username, sessionid, steamid, token: saved.append(
            {"username": username, "steam_id": steamid, "token": token, "sid": sessionid}
        ),
    )
    result = modern_login.login("someone", password="pw", code="ABC123", session=_login_session())
    assert result["store_authed"] is True and result["saved"] is True
    assert result["steam_id"] == "76561198121699884"
    assert saved and saved[0]["username"] == "someone" and saved[0]["token"] == "RT"


def test_login_refuses_to_save_when_the_store_rejects_the_session(monkeypatch):
    monkeypatch.setattr(modern_login, "_api_get", lambda *a, **kw: dict(RSA_KEY))
    monkeypatch.setattr(modern_login, "encrypt_password", lambda *a: "ENC")
    monkeypatch.setattr(
        modern_login,
        "_api_post",
        lambda _s, method, payload: {
            "BeginAuthSessionViaCredentials": {"client_id": "C", "request_id": "R", "interval": 0},
            "PollAuthSessionStatus": {"refresh_token": "RT"},
        }[method],
    )
    saved: list = []
    monkeypatch.setattr(modern_login, "persist", lambda *a, **kw: saved.append(a))
    with pytest.raises(LoginFailedError):
        modern_login.login("someone", password="pw", session=_login_session(store_status=302))
    assert saved == []  # nothing half-broken is written


def test_remint_needs_a_stored_refresh_token(monkeypatch):
    monkeypatch.setattr(auth, "get_refresh_token", lambda: None)
    with pytest.raises(LoginFailedError) as exc:
        modern_login.remint_session()
    assert "steam login" in exc.value.detail


def test_remint_replays_the_transfers_with_the_stored_token(monkeypatch):
    monkeypatch.setattr(auth, "get_refresh_token", lambda: "STORED-RT")
    monkeypatch.setattr(auth, "get_username", lambda: "someone")
    saved: list[dict] = []
    monkeypatch.setattr(
        modern_login,
        "persist",
        lambda session, username, sessionid, steamid, token: saved.append(
            {"username": username, "token": token}
        ),
    )
    result = modern_login.remint_session(session=_login_session())
    assert result["store_authed"] is True
    assert saved and saved[0]["token"] == "STORED-RT"


def test_persist_session_writes_every_credential(monkeypatch):
    written: dict[str, str] = {}
    monkeypatch.setattr(auth, "_keyring_set", lambda key, value: written.__setitem__(key, value))
    auth.persist_session(
        {"steamLoginSecure": [{"value": "v", "domain": "store.steampowered.com", "path": "/"}]},
        username="someone",
        session_id="sid",
        steam_id="765",
        refresh_token="RT",
    )
    assert written[auth.KEY_SESSION_ID] == "sid"
    assert written[auth.KEY_STEAM_ID] == "765"
    assert written[auth.KEY_USERNAME] == "someone"
    assert written[auth.KEY_REFRESH_TOKEN] == "RT"


def test_logout_keeps_the_refresh_token_on_purpose(monkeypatch):
    """`steam logout` ends the session but must not kill password-less re-mint —
    that is what `steam revoke-all` is for."""
    deleted: list[str] = []
    monkeypatch.setattr(auth, "_keyring_delete", lambda key: deleted.append(key))
    auth.clear_session()
    assert auth.KEY_SESSION in deleted
    assert auth.KEY_REFRESH_TOKEN not in deleted


class FakeProbe:
    """Minimal stand-in for requests.Session in the validity probes."""

    def __init__(self, status_code, landed):
        self.status_code = status_code
        self.url = landed
        self.seen: list[dict] = []

    def get(self, url, **kwargs):
        self.seen.append(kwargs)
        return self


def test_session_probe_follows_redirects_and_ignores_a_bootstrap_302():
    """Regression: /account/ 302s to itself while the store bootstraps cookies; the old
    probe required a bare 200 and so reported healthy sessions as expired."""
    probe = FakeProbe(200, "https://store.steampowered.com/account/")
    assert auth.probe_authed(probe, "https://store.steampowered.com/account/") is True
    assert probe.seen[0]["allow_redirects"] is True


def test_session_probe_rejects_a_redirect_to_login():
    probe = FakeProbe(200, "https://store.steampowered.com/login/home/?goto=account")
    assert auth.probe_authed(probe, "https://store.steampowered.com/account/") is False


def test_verify_session_needs_the_landing_page_not_just_a_200():
    session = FakeSession(
        [
            FakeResponse(200),  # store: lands on the account page below
            FakeResponse(200),  # community
        ]
    )
    session._responses[0].url = "https://store.steampowered.com/account/"
    session._responses[1].url = "https://steamcommunity.com/profiles/76561198121699884/"
    state = modern_login.verify_session(session)
    assert state["https://store.steampowered.com/account/"]["authed"] is True
    assert state["https://steamcommunity.com/my/"]["authed"] is True


PAYLOAD = {
    "apilist": {
        "interfaces": [
            {
                "name": "IPlayerService",
                "methods": [
                    {
                        "name": "GetOwnedGames",
                        "version": 1,
                        "httpmethod": "GET",
                        "parameters": [
                            {"name": "key", "type": "string", "optional": False},
                            {"name": "steamid", "type": "uint64", "optional": False},
                            {"name": "appids_filter", "type": "string", "optional": False},
                        ],
                    }
                ],
            }
        ]
    }
}


def test_webapi_metadata_is_relaxed_on_import():
    """Regression: ValvePython enforces Steam's `GetSupportedAPIList` metadata, which
    marks parameters as required that the live endpoints accept as omitted, so a clean
    install could not run `stats summary` / `library list` without patching
    site-packages by hand (`Method requires 'appids_filter' to be set`).

    Exercised against the real library with a minimal API-list payload — no network.
    """
    from steam.webapi import WebAPI

    from steam_cli import WEBAPI_METADATA_RELAXED, _compat

    assert WEBAPI_METADATA_RELAXED is True
    assert getattr(WebAPI, "_steam_cli_relaxed", False) is True
    assert _compat.relax_webapi_param_validation() is True  # idempotent, never re-wraps

    api = WebAPI(key="not-used", auto_load_interfaces=False)
    api.load_interfaces(PAYLOAD)
    params = api.interfaces[0].methods[0].parameters
    assert params["appids_filter"]["optional"] is True  # was False in the metadata
    assert params["steamid"]["optional"] is True
