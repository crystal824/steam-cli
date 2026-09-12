#!/usr/bin/env python3
"""Re-mint steam-cli session cookies from the stored refresh token (2026-09-11).

Real Steam web sessions come from login.steampowered.com/jwt/finalizelogin plus
the transfer_info settoken URLs. Two empirical findings, both required:

  * the settoken POST body must carry `steamID` (top-level of the finalize
    response) in addition to nonce+auth. Without it Steam answers
    {"result":8} and mints nothing; with it, {"result":1,"rtExpiry":<unix>}
    and steamLoginSecure appears.
  * a fresh refresh token is not needed for every re-mint: the stored token
    keeps working until rtExpiry, so re-login needs no password and no 2FA code.

Use this whenever `steam status` reports the session is no longer valid.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from base64 import b64encode  # noqa: F401  (kept for symmetry with the login tool)
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from steam_cli import auth

FINALIZE = "https://login.steampowered.com/jwt/finalizelogin"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def dump(**kw) -> None:
    print(json.dumps(kw, ensure_ascii=False), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", required=True, help="Steam account name")
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    refresh_token = auth._keyring_get("refresh_token")
    if not refresh_token:
        dump(step="token", ok=False, note="no stored refresh_token; run steam_modern_login.py")
        return 1

    s = requests.Session()
    s.headers["User-Agent"] = UA
    sessionid = secrets.token_hex(12)

    fin = s.post(
        FINALIZE,
        data={
            "nonce": refresh_token,
            "sessionid": sessionid,
            "redir": "https://steamcommunity.com/login/home/?goto=",
        },
        timeout=25,
    )
    data = fin.json()
    transfer = data.get("transfer_info") or []
    steamid = str(data.get("steamID") or "")
    dump(step="finalize", http=fin.status_code, steamid=steamid, transfers=len(transfer))

    results = []
    for item in transfer:
        url = item.get("url")
        body = dict(item.get("params") or {})
        body["steamID"] = steamid
        r = s.post(url, data=body, timeout=25)
        try:
            rj = r.json()
        except ValueError:
            rj = {}
        results.append((url, rj.get("result"), rj.get("rtExpiry")))
        dump(
            step="settoken",
            url=url,
            http=r.status_code,
            result=rj.get("result"),
            rtExpiry=rj.get("rtExpiry"),
        )

    verified = {}
    for url in ("https://store.steampowered.com/account/", "https://steamcommunity.com/my/"):
        v = s.get(url, timeout=25, allow_redirects=False)
        verified[url] = v.status_code == 200
        dump(step="verify", url=url, http=v.status_code, authed=v.status_code == 200)

    # The CLI's own "session valid" probe (and its wishlist commands) target the
    # store domain, so store auth is the bar for saving. Community auth is
    # reported but not required (a community settoken can still land on 302).
    store_ok = verified.get("https://store.steampowered.com/account/", False)
    ok = store_ok and any(x[1] == 1 for x in results)
    dump(
        step="result",
        ok=ok,
        store_authed=store_ok,
        community_authed=verified.get("https://steamcommunity.com/my/", False),
        cookies=[(c.name, c.domain) for c in s.cookies],
    )

    if ok and args.save:
        cookies: dict[str, list[dict]] = {}
        for c in s.cookies:
            cookies.setdefault(c.name, []).append(
                {"value": c.value, "domain": c.domain or "", "path": c.path or "/"}
            )
        auth._keyring_set(auth.KEY_SESSION, json.dumps(cookies))
        auth._keyring_set(auth.KEY_SESSION_ID, sessionid)
        auth._keyring_set(auth.KEY_USERNAME, args.username)
        if steamid:
            auth._keyring_set(auth.KEY_STEAM_ID, steamid)
        auth._invalidate_status()
        dump(step="save", saved=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
