"""Steam's current web login flow — what `steam login` drives.

ValvePython's ``steam.webauth.WebAuth`` (what this command used before) posts to the
community ``/login/dologin/`` endpoint Valve retired. Steam still answers that call —
success + ``login_complete`` after a correct password and 2FA code — but mints **no
usable session**, so the command could report success and authenticate nothing.

The flow the web client actually uses, implemented here:

1. `GetPasswordRSAPublicKey` — RSA key + timestamp
2. `BeginAuthSessionViaCredentials` — client_id / request_id / allowed_confirmations
3. approve in the Steam app (confirmation type 2) **or**
   `UpdateAuthSessionWithSteamGuardCode` (type 3)
4. `PollAuthSessionStatus` — yields a long-lived **refresh_token**
5. `login.steampowered.com/jwt/finalizelogin` — one settoken URL per domain
6. POST each settoken URL **with ``steamID`` in the body** — without it Steam answers
   ``{"result": 8}`` and mints no cookie (measured 2026-09-11; this single missing
   parameter is why every earlier attempt "logged in" and authenticated nothing)

Because step 4 yields a refresh token, later re-authentication needs neither password
nor 2FA: :func:`remint_session` replays steps 5-6 with the stored token until it
expires (``rtExpiry`` from the settoken response).

Passwords are read with :func:`getpass.getpass` (or passed in by a caller) and never
appear in argv, logs, or the audit trail.
"""

from __future__ import annotations

import base64
import getpass
import json
import secrets
import time
from collections.abc import Callable

import requests
from steam.core.crypto import pkcs1v15_encrypt, rsa_publickey

from . import auth
from .errors import LoginFailedError, NetworkError

API = "https://api.steampowered.com/IAuthenticationService"
STORE = "https://store.steampowered.com"
COMMUNITY = "https://steamcommunity.com"
FINALIZE = "https://login.steampowered.com/jwt/finalizelogin"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_INTERVAL = 5.0
POLL_TIMEOUT = 180.0
# Confirmation types Steam may allow: 2 = approve in the mobile app, 3 = typed code.
CONFIRM_APP = 2
CONFIRM_CODE = 3

Event = Callable[..., None]


def _noop(**_kwargs: object) -> None:
    """Default event sink: the flow stays silent unless a caller wants progress."""


def new_session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = UA
    return session


def _api_get(session: requests.Session, method: str, payload: dict) -> dict:
    try:
        resp = session.get(
            f"{API}/{method}/v1/", params={"input_json": json.dumps(payload)}, timeout=25
        )
        resp.raise_for_status()
        return resp.json().get("response", {}) or {}
    except (requests.RequestException, ValueError) as exc:
        raise NetworkError(detail=f"{method}: {exc}")


def _api_post(session: requests.Session, method: str, payload: dict) -> dict:
    try:
        resp = session.post(
            f"{API}/{method}/v1/", data={"input_json": json.dumps(payload)}, timeout=25
        )
        resp.raise_for_status()
        return resp.json().get("response", {}) or {}
    except (requests.RequestException, ValueError) as exc:
        raise NetworkError(detail=f"{method}: {exc}")


def encrypt_password(publickey_mod: str, publickey_exp: str, password: str) -> str:
    """PKCS#1 v1.5 encrypt the password with the key Steam just handed out."""
    key = rsa_publickey(int(publickey_mod, 16), int(publickey_exp, 16))
    return base64.b64encode(pkcs1v15_encrypt(key, password.encode("utf-8"))).decode()


def begin_auth_session(
    session: requests.Session,
    account_name: str,
    password: str,
    *,
    on_event: Event = _noop,
) -> dict:
    """Steps 1-2: fetch the RSA key and open an auth session with the credentials."""
    key_info = _api_get(session, "GetPasswordRSAPublicKey", {"account_name": account_name})
    if not key_info.get("publickey_mod"):
        raise LoginFailedError(
            f"Steam did not return an RSA key for {account_name!r}",
            detail="the account name may be wrong, or Steam is asking for a captcha",
        )
    encrypted = encrypt_password(key_info["publickey_mod"], key_info["publickey_exp"], password)
    on_event(step="rsa", ok=True)

    began = _api_post(
        session,
        "BeginAuthSessionViaCredentials",
        {
            "account_name": account_name,
            "encrypted_password": encrypted,
            "encryption_timestamp": int(key_info["timestamp"]),
            "remember_login": True,
            "platform_type": 2,
            "persistence": 1,
            "website_id": "Community",
            "device_friendly_name": "steam-cli",
        },
    )
    if not began.get("client_id"):
        # Steam answers an empty response (or eresult) for a wrong password / blocked
        # account. Do not retry: repeated failures are what trips Steam's rate limits.
        raise LoginFailedError(
            f"Steam refused the credentials for {account_name!r}",
            detail=json.dumps(began) if began else "empty response",
        )
    began = dict(began)
    began["steamid"] = str(began.get("steamid") or "")
    began["interval"] = float(began.get("interval") or DEFAULT_INTERVAL)
    began["confirmation_types"] = confirmation_types(began)
    on_event(
        step="begin",
        ok=True,
        steamid=began["steamid"],
        interval=began["interval"],
        confirmation_types=began["confirmation_types"],
    )
    return began


def confirmation_types(began: dict) -> list[int]:
    """The confirmation types Steam allows for this session (2 = app, 3 = code)."""
    allowed = began.get("allowed_confirmations") or []
    return [
        int(item["confirmation_type"])
        for item in allowed
        if isinstance(item, dict) and item.get("confirmation_type") is not None
    ]


def submit_guard_code(session: requests.Session, began: dict, code: str) -> None:
    """Step 3b: hand Steam the code the user typed from the mobile app."""
    _api_post(
        session,
        "UpdateAuthSessionWithSteamGuardCode",
        {
            "client_id": began.get("client_id"),
            "steamid": began.get("steamid"),
            "code": code,
            "code_type": CONFIRM_CODE,
        },
    )


def poll_for_tokens(
    session: requests.Session,
    began: dict,
    *,
    timeout: float = POLL_TIMEOUT,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.time,
    on_event: Event = _noop,
) -> dict:
    """Step 4: poll until Steam hands back the tokens (or we run out of time)."""
    interval = max(float(began.get("interval") or DEFAULT_INTERVAL), 3.0)
    deadline = now() + timeout
    polled: dict = {}
    while now() < deadline:
        try:
            polled = _api_post(
                session,
                "PollAuthSessionStatus",
                {"client_id": began.get("client_id"), "request_id": began.get("request_id")},
            )
        except NetworkError as exc:  # transient: keep polling until the deadline
            on_event(step="poll", error=str(exc)[:80])
            polled = {}
        if polled.get("refresh_token") or polled.get("access_token"):
            on_event(
                step="poll",
                ok=True,
                got_refresh_token=bool(polled.get("refresh_token")),
                got_access_token=bool(polled.get("access_token")),
            )
            return polled
        sleep(interval)
    raise LoginFailedError(
        "timed out waiting for Steam to confirm the login",
        detail="approve the prompt in the Steam mobile app (or re-run and enter the code)",
    )


def finalize_login(
    session: requests.Session, refresh_token: str, sessionid: str
) -> tuple[list[dict], str]:
    """Step 5: exchange the refresh token for the per-domain settoken transfers."""
    try:
        resp = session.post(
            FINALIZE,
            data={
                "nonce": refresh_token,
                "sessionid": sessionid,
                "redir": f"{COMMUNITY}/login/home/?goto=",
            },
            timeout=25,
        )
    except requests.RequestException as exc:
        raise NetworkError(detail=f"finalizelogin: {exc}")
    try:
        payload = resp.json()
    except ValueError:
        raise LoginFailedError(
            "finalizelogin answered a non-JSON body",
            detail=f"HTTP {resp.status_code} — the refresh token is probably expired",
        )
    transfer = payload.get("transfer_info") or []
    if not transfer:
        raise LoginFailedError(
            "finalizelogin returned no transfers",
            detail=json.dumps(payload)[:200],
        )
    return transfer, str(payload.get("steamID") or "")


def apply_transfers(
    session: requests.Session, transfer: list[dict], steamid: str, *, on_event: Event = _noop
) -> list[dict]:
    """Step 6: POST each settoken URL. ``steamID`` is mandatory in the body."""
    results: list[dict[str, object]] = []
    for item in transfer:
        url = str(item.get("url") or "")
        if not url:
            continue
        body = dict(item.get("params") or {})
        body["steamID"] = steamid
        result: dict[str, object]
        try:
            resp = session.post(url, data=body, timeout=25)
            try:
                payload = resp.json()
            except ValueError:
                payload = {}
            result = {
                "url": url,
                "http": resp.status_code,
                "result": payload.get("result"),
                "rtExpiry": payload.get("rtExpiry"),
            }
        except requests.RequestException as exc:
            result = {"url": url, "error": type(exc).__name__}
        results.append(result)
        on_event(step="settoken", **result)
    return results


def verify_session(session: requests.Session) -> dict:
    """Probe the store and community domains with the freshly minted cookies.

    Redirects are followed on purpose: the store 302s a first request to `/account/`
    to itself while it bootstraps cookies, so a non-following probe calls a healthy
    session dead (that mistake cost a round of pointless re-logins). Store auth is the
    bar; community is reported too.
    """
    state: dict[str, dict[str, object]] = {}
    for url in (f"{STORE}/account/", f"{COMMUNITY}/my/"):
        try:
            resp = session.get(url, timeout=25, allow_redirects=True)
            authed = resp.status_code == 200 and "/login/" not in str(resp.url)
            state[url] = {"http": resp.status_code, "landed": str(resp.url), "authed": authed}
        except requests.RequestException as exc:
            state[url] = {"http": None, "authed": False, "error": type(exc).__name__}
    return state


def _cookies_of(session: requests.Session) -> dict[str, list[dict]]:
    cookies: dict[str, list[dict]] = {}
    for cookie in session.cookies:
        cookies.setdefault(cookie.name, []).append(
            {"value": cookie.value, "domain": cookie.domain or "", "path": cookie.path or "/"}
        )
    return cookies


def persist(
    session: requests.Session, username: str, sessionid: str, steamid: str, refresh_token: str
) -> None:
    auth.persist_session(
        _cookies_of(session),
        username=username,
        session_id=sessionid,
        steam_id=steamid,
        refresh_token=refresh_token or None,
    )


def login(
    username: str | None = None,
    *,
    password: str | None = None,
    code: str | None = None,
    save: bool = True,
    session: requests.Session | None = None,
    timeout: float = POLL_TIMEOUT,
    on_event: Event = _noop,
) -> dict:
    """Full interactive login (steps 1-6) and, by default, persist the session.

    The password is prompted with :func:`getpass.getpass` when not supplied, and the
    Steam Guard code likewise (an empty answer means "I will approve it in the app").
    """
    account = (username or "").strip()
    if not account:
        account = input("Steam account name: ").strip()
        if not account:
            raise LoginFailedError("no account name given")

    session = session or new_session()
    secret = password if password is not None else getpass.getpass(f"Password for {account}: ")
    began = begin_auth_session(session, account, secret, on_event=on_event)

    allowed = began.get("confirmation_types") or []
    if CONFIRM_APP in allowed:
        on_event(
            step="guard",
            note="approve the login in the Steam mobile app (or type the code below)",
        )
    if CONFIRM_CODE in allowed:
        typed = code if code is not None else input("Steam Guard code (empty = approve in app): ")
        typed = (typed or "").strip()
        if typed:
            submit_guard_code(session, began, typed)
            on_event(step="guard_code", submitted=True)

    polled = poll_for_tokens(session, began, timeout=timeout, on_event=on_event)
    refresh_token = str(polled.get("refresh_token") or "")
    if not refresh_token:
        raise LoginFailedError(
            "Steam did not return a refresh token",
            detail=f"poll keys: {sorted(polled.keys())}",
        )
    steamid = str(polled.get("steamid") or began.get("steamid") or "")

    sessionid = secrets.token_hex(12)
    transfer, final_steamid = finalize_login(session, refresh_token, sessionid)
    steamid = final_steamid or steamid
    on_event(step="finalize", ok=True, steamid=steamid, transfers=len(transfer))

    results = apply_transfers(session, transfer, steamid, on_event=on_event)
    state = verify_session(session)
    store_ok = state[f"{STORE}/account/"]["authed"]
    minted = any(item.get("result") == 1 for item in results)
    if not (store_ok and minted):
        raise LoginFailedError(
            "the session was not accepted by the store after login",
            detail=json.dumps(state),
        )
    if save:
        persist(session, account, sessionid, steamid, refresh_token)
        on_event(step="save", saved=True, steam_id=bool(steamid))
    return {
        "username": account,
        "steam_id": steamid,
        "session_id": sessionid,
        "refresh_token": refresh_token,
        "store_authed": store_ok,
        "community_authed": state[f"{COMMUNITY}/my/"]["authed"],
        "saved": save,
    }


def remint_session(
    username: str | None = None,
    *,
    refresh_token: str | None = None,
    save: bool = True,
    session: requests.Session | None = None,
    on_event: Event = _noop,
) -> dict:
    """Re-authenticate from the stored refresh token — no password, no 2FA."""
    token = refresh_token or auth.get_refresh_token()
    if not token:
        raise LoginFailedError(
            "no refresh token stored",
            detail="run `steam login` once (password + Steam Guard) to obtain one",
        )
    account = (username or auth.get_username() or "").strip()
    session = session or new_session()
    sessionid = secrets.token_hex(12)
    transfer, steamid = finalize_login(session, token, sessionid)
    on_event(step="finalize", ok=True, steamid=steamid, transfers=len(transfer))

    results = apply_transfers(session, transfer, steamid, on_event=on_event)
    state = verify_session(session)
    store_ok = state[f"{STORE}/account/"]["authed"]
    minted = any(item.get("result") == 1 for item in results)
    if not (store_ok and minted):
        raise LoginFailedError(
            "re-minting did not authenticate the store session",
            detail="the refresh token may have expired (rtExpiry) — run `steam login`",
        )
    if save:
        persist(session, account, sessionid, steamid, token)
        on_event(step="save", saved=True)
    return {
        "username": account,
        "steam_id": steamid,
        "session_id": sessionid,
        "store_authed": store_ok,
        "community_authed": state[f"{COMMUNITY}/my/"]["authed"],
        "saved": save,
    }
