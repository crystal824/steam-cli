#!/usr/bin/env python3
"""Modern Steam web login for steam-cli (2026-09-11).

Problem
-------
steam-cli authenticates through ValvePython's `steam.webauth.WebAuth`, which
talks to the retired community `/login/dologin/` flow. Steam still answers that
call (success + login_complete after a correct password + 2FA code) but no
longer mints any usable session with it: the resulting cookies 302 straight back
to the login page on both steamcommunity.com and store.steampowered.com.

What the real web client does now
---------------------------------
  1. GET  IAuthenticationService/GetPasswordRSAPublicKey/v1/
  2. POST IAuthenticationService/BeginAuthSessionViaCredentials/v1/
         -> client_id / request_id / allowed_confirmations
  3. (Steam Guard) user taps "approve" in the mobile app  -or-  types the code
     and we POST UpdateAuthSessionWithSteamGuardCode/v1/
  4. POST IAuthenticationService/PollAuthSessionStatus/v1/
         -> refresh_token + access_token
  5. POST https://login.steampowered.com/jwt/finalizelogin
         -> transfer_info[{url, params}]  (settoken transfers)
  6. POST each transfer_info url -> real steamLoginSecure JWT cookies per domain

This script implements exactly that, then persists the cookies in the format
steam-cli expects. Because step 4 yields a refresh token, later re-logins can be
done by re-running with --refresh-token (no password, no 2FA code).

Secrets come from prompts / env only, never from argv.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import secrets
import sys
import time
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from steam.core.crypto import pkcs1v15_encrypt, rsa_publickey

API = "https://api.steampowered.com/IAuthenticationService"
STORE = "https://store.steampowered.com"
COMMUNITY = "https://steamcommunity.com"
FINALIZE = "https://login.steampowered.com/jwt/finalizelogin"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def dump(**kw) -> None:
    print(json.dumps(kw, ensure_ascii=False), flush=True)


def api_get(s: requests.Session, method: str, payload: dict) -> dict:
    r = s.get(f"{API}/{method}/v1/", params={"input_json": json.dumps(payload)}, timeout=25)
    r.raise_for_status()
    return r.json().get("response", {})


def api_post(s: requests.Session, method: str, payload: dict) -> dict:
    r = s.post(f"{API}/{method}/v1/", data={"input_json": json.dumps(payload)}, timeout=25)
    r.raise_for_status()
    return r.json().get("response", {})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", required=True, help="Steam account name")
    ap.add_argument("--save", action="store_true")
    ap.add_argument(
        "--refresh-token", default="", help="reuse a stored refresh token (skips password + 2FA)"
    )
    args = ap.parse_args()

    s = requests.Session()
    s.headers["User-Agent"] = UA

    steamid = ""
    refresh_token = args.refresh_token

    if refresh_token:
        dump(step="auth", mode="refresh_token")
    else:
        # 1) RSA key
        key_info = api_get(s, "GetPasswordRSAPublicKey", {"account_name": args.username})
        key = rsa_publickey(int(key_info["publickey_mod"], 16), int(key_info["publickey_exp"], 16))
        ts = key_info["timestamp"]
        password = getpass.getpass(f"Password for {args.username}: ")
        enc_pw = base64.b64encode(pkcs1v15_encrypt(key, password.encode("ascii"))).decode()
        dump(step="rsa", ok=True)

        # 2) begin session
        began = api_post(
            s,
            "BeginAuthSessionViaCredentials",
            {
                "account_name": args.username,
                "encrypted_password": enc_pw,
                "encryption_timestamp": int(ts),
                "remember_login": True,
                "platform_type": 2,
                "persistence": 1,
                "website_id": "Community",
                "device_friendly_name": "steam-cli",
            },
        )
        client_id = began.get("client_id")
        request_id = began.get("request_id")
        steamid = str(began.get("steamid") or "")
        interval = float(began.get("interval") or 5)
        confs = began.get("allowed_confirmations") or []
        types = [c.get("confirmation_type") for c in confs if isinstance(c, dict)]
        dump(
            step="begin",
            ok=bool(client_id),
            steamid=steamid,
            interval=interval,
            confirmation_types=types,
        )

        # 3) Steam Guard: prefer app approval (type 2); fall back to typed code (type 3)
        if 2 in types:
            print("👉 Steam 手机 App 里会弹出登录确认，请点「批准」/「Approve」", flush=True)
        if 3 in types:
            code = input("Enter Steam Guard code from the mobile app: ").strip()
            if code:
                api_post(
                    s,
                    "UpdateAuthSessionWithSteamGuardCode",
                    {
                        "client_id": client_id,
                        "steamid": steamid,
                        "code": code,
                        "code_type": 3,
                    },
                )
                dump(step="guard_code", submitted=True)

        # 4) poll
        polled = {}
        deadline = time.time() + 180
        while time.time() < deadline:
            try:
                polled = api_post(
                    s, "PollAuthSessionStatus", {"client_id": client_id, "request_id": request_id}
                )
            except requests.HTTPError as exc:
                dump(step="poll", error=str(exc)[:80])
            if polled.get("refresh_token") or polled.get("access_token"):
                break
            time.sleep(max(interval, 3))
        refresh_token = polled.get("refresh_token") or ""
        if not refresh_token:
            dump(step="poll", ok=False, keys=sorted(polled.keys()), note="no refresh_token")
            return 1
        if polled.get("new_guard_data"):
            dump(step="poll", note="new_guard_data present")
        dump(
            step="poll",
            ok=True,
            got_refresh_token=True,
            got_access_token=bool(polled.get("access_token")),
        )

    # 5) finalize login -> transfer_info
    sessionid = secrets.token_hex(12)
    fin = s.post(
        FINALIZE,
        data={
            "nonce": refresh_token,
            "sessionid": sessionid,
            "redir": f"{COMMUNITY}/login/home/?goto=",
        },
        timeout=25,
    )
    try:
        fin_json = fin.json()
    except ValueError:
        dump(step="finalize", ok=False, http=fin.status_code, note="non-JSON")
        return 1
    transfer = fin_json.get("transfer_info") or []
    steamid = str(fin_json.get("steamID") or steamid)
    dump(
        step="finalize",
        ok=bool(transfer),
        http=fin.status_code,
        steamid=steamid,
        transfers=[t.get("url") for t in transfer],
    )

    # 6) settoken per domain
    for item in transfer:
        url, params = item.get("url"), item.get("params") or {}
        # Steam requires steamID in the settoken body: without it the endpoint
        # answers {"result":8} and mints no cookie (measured 2026-09-11).
        body = dict(params)
        body["steamID"] = steamid
        try:
            t = s.post(url, data=body, timeout=25)
            try:
                rb = t.json()
            except ValueError:
                rb = {}
            dump(
                step="settoken",
                url=url,
                http=t.status_code,
                result=rb.get("result"),
                set_cookies=sorted({c.name for c in t.cookies}),
            )
        except requests.RequestException as exc:
            dump(step="settoken", url=url, error=type(exc).__name__)

    # 7) verify
    for url in (f"{STORE}/account/", f"{COMMUNITY}/my/"):
        v = s.get(url, timeout=25, allow_redirects=False)
        dump(
            step="verify",
            url=url,
            http=v.status_code,
            authed=v.status_code == 200,
            redirect=(v.headers.get("Location", "") or "")[:70],
        )

    cookie_names = sorted({c.name for c in s.cookies})
    dump(step="cookies", names=cookie_names)

    if args.save:
        from steam_cli import auth

        cookies: dict[str, list[dict]] = {}
        for c in s.cookies:
            cookies.setdefault(c.name, []).append(
                {"value": c.value, "domain": c.domain or "", "path": c.path or "/"}
            )
        auth._keyring_set(auth.KEY_SESSION, json.dumps(cookies))
        auth._keyring_set(auth.KEY_USERNAME, args.username)
        auth._keyring_set(auth.KEY_SESSION_ID, sessionid)
        if steamid:
            auth._keyring_set(auth.KEY_STEAM_ID, steamid)
        auth._keyring_set("refresh_token", refresh_token)
        auth._invalidate_status()
        dump(step="save", saved=True, steam_id=bool(steamid), refresh_token_saved=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
