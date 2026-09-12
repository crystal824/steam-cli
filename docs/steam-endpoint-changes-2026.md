# Steam endpoint & behaviour changes (2026) — what broke and how it is fixed

Valve has retired or reworked a number of endpoints this CLI was built on. Several
failures looked like "bad credentials" or "bad key" but were actually dead
endpoints, so this document records **what changed, how each symptom presents, and
where the fix lives**.

Summary:

| Area | Was | Now | Symptom when unfixed |
|---|---|---|---|
| Web login | community `/login/dologin/` (ValvePython `WebAuth`) | `IAuthenticationService` + `login.steampowered.com/jwt/finalizelogin` | login "succeeds", session authenticates nothing |
| Store login helpers | store `/login/getrsakey/`, `/login/dologin/` | retired (HTML/404) | non-JSON response / `Method Not Allowed` |
| CDK activation | `POST /account/registerkey` | `POST /account/ajaxregisterkey/` (JSON) | `endpoint_unavailable`, "unrecognized response" |
| Wishlist read | `/wishlist/profiles/<id>/wishlistdata/` | `IWishlistService/GetWishlist/v1/` | HTTP 302 → JSON decode error |
| Store app names | batched `api/appdetails?appids=1,2,3` | **one appid per request** | HTTP 400 on any list |
| Full app list | `ISteamApps/GetAppList` | 404/403 (retired/restricted) | 404 |
| Session cookies | `session.cookies.get(name)` | iterate the jar — see `auth.cookie_value()` | `CookieConflictError` |
| Achievements | `percent` float | `percent` **string** | `ValueError: Unknown format code 'f'` |
| Friend invite link | `steamcommunity.com/actions/QuickInviteLink` | 403 (changed server-side) | `endpoint_unavailable` / 403 |

## 1. Login — the whole flow had to be rebuilt

`steam login` used ValvePython's `steam.webauth.WebAuth`, which posts to the
community `/login/dologin/`. Steam still answers that call — after a correct
password and Steam Guard code it returns `success` + `login_complete` — **but it no
longer mints a usable session**: every protected page redirects back to the login
page. `steam status` reports `Session valid: no`, and session-based commands fail
with `not_authenticated`. `steam` 1.4.4 is the newest release on PyPI, so there is
no upgrade that fixes it.

The current flow, implemented in `tools/steam_modern_login.py`:

1. `GET  IAuthenticationService/GetPasswordRSAPublicKey/v1/` — RSA key + timestamp
2. `POST IAuthenticationService/BeginAuthSessionViaCredentials/v1/` — encrypted
   password; the response carries `client_id`, `request_id`, `steamid`,
   `interval`, and `allowed_confirmations` (`3` = code from the mobile app,
   `4` = approve in the mobile app)
3. either `POST UpdateAuthSessionWithSteamGuardCode/v1/` with the code, or have the
   user approve the login in the Steam mobile app
4. `POST IAuthenticationService/PollAuthSessionStatus/v1/` → **`refresh_token`**
5. `POST login.steampowered.com/jwt/finalizelogin` → `transfer_info` (settoken URLs)
6. `POST` each settoken URL to mint `steamLoginSecure` for store / community /
   help / checkout / steam.tv

**The one-parameter blocker:** the settoken request body must contain
`steamID` *in addition to* the `nonce` and `auth` returned by `finalizelogin`.
Without it Steam replies `{"result":8}` and sets **no** cookie, which is exactly
how you end up with a "successful" login that authenticates nothing. With it the
response is `{"result":1,"rtExpiry":<unix>}` and the cookie appears. This was
found by sweeping seven request shapes; only the `steamID` variant mints.

Because step 4 yields a refresh token, later re-authentication needs **no password
and no 2FA**:

```bash
.venv/bin/python tools/steam_remint_session.py --username <account> --save
```

Use this whenever `steam status` reports the session is invalid. The full login
(needing the password plus app approval or a Steam Guard code) is only required
when the refresh token itself has expired (`rtExpiry` in the settoken response).

### Local patch to the installed library

`steam/webauth.py::_finalize_login` assumed the legacy
`login_response['transfer_parameters']['steamid']`, which now raises
`KeyError: 'transfer_parameters'` **after** a successful password + 2FA login. The
patched version accepts both shapes (`transfer_parameters` and `transfer_info`),
never raises, and can recover the SteamID from the `steamLoginSecure` cookie —
whose value is URL-encoded `<steamid>%7C%7C<token>`. See
`patches/steam-1.4.4-webauth-transfer-info.patch`.

## 2. CDK activation — wrong endpoint, not a bad key

`POST https://store.steampowered.com/account/registerkey` is only the HTML form
page; posting a key to it returns the ~50 KB "Activate a Product on Steam" form, so
the response matcher found no keywords and reported `unknown` →
`endpoint_unavailable`. **The key is not rejected — the old code never reached the
real API.**

The real endpoint (what the store front-end `registerkey.js` calls):

```
POST https://store.steampowered.com/account/ajaxregisterkey/
     product_key=<KEY>&sessionid=<sessionid>
     Referer: https://store.steampowered.com/account/registerkey
     Origin:  https://store.steampowered.com
     X-Requested-With: XMLHttpRequest
```

Responses:

- `{"success":1,"purchase_receipt_info":{"line_items":[{"line_item_description":"<PRODUCT>"}]}}`
  → activated. The product name is printed and logged as `ok:<name>`.
- `{"success":0,"purchase_result_details":N}` → map `N` via `_PURCHASE_RESULTS`:
  `14` invalid · `15` already activated by another account · `53` rate limited ·
  `13` region locked · **`9` already owned by this account** · `24` base game
  required · `4` retry after 30 minutes.

Code `9` means the key **was** consumed earlier (by this account) — report it as
success-with-caveat. Re-submitting a key is therefore a safe idempotency check:
`already_activated` / code `9` proves an earlier attempt landed.

## 3. Wishlist — endpoint replaced

`https://store.steampowered.com/wishlist/profiles/<steamid>/wishlistdata/` now
returns **302 for every request** (with a valid session, with and without an
`X-Requested-With` header). Current Steam serves wishlists from the Web API:

```
GET https://api.steampowered.com/IWishlistService/GetWishlist/v1/?steamid=<id>
-> {"response": {"items": [{"appid": 110800, "priority": 1, "date_added": ...}]}}
```

The response contains **no names**, and the endpoints previously used to resolve
them are gone: batched `api/appdetails?appids=1,2,3` returns HTTP 400 for any
comma-separated list, and `ISteamApps/GetAppList` returns 404/403. Names are
therefore resolved with **one request per appid**, run through a small thread pool
and cached in `~/.config/steam-cli/appnames.json` (~14 s cold for 98 items, ~3 s
warm).

## 4. Session cookies — `CookieConflictError`

`requests` rejects `session.cookies.get("sessionid")` when the same cookie name
exists for several domains — which is the normal state of a Steam session, because
the login mirrors cookies onto store / community / help. Every lookup now goes
through `steam_cli.auth.cookie_value(session, name)`, which iterates the jar
instead. Call sites that used to crash: `activate` (×2), `friends`, `review`,
`wishlist`.

## 5. Steam's published API metadata is unreliable

ValvePython's `WebAPI` validates calls against `GetSupportedAPIList` and refuses
to send when a parameter marked "required" is missing. That metadata now disagrees
with the live endpoints: `IPlayerService/GetOwnedGames` demands `appids_filter`,
then `include_free_sub`, while the identical request without them returns HTTP 200
and the complete library. The local patch
(`patches/steam-1.4.4-webapi-required-params.patch`) skips absent parameters and
lets Steam do the real validation.

## 6. Verifying that something landed

`GetOwnedGames` has **no acquisition timestamp**, and playtime can predate a key
(the user may have played a Playtest build), so neither the library list nor a CLI
success line proves an activation. The authoritative source is the account
licenses page, where each row carries the acquisition **date and method**
(`Retail` = key/CDK, `Steam Store` = purchase, `Gift/Guest Pass` = gift):

```bash
.venv/bin/python tools/check_licenses.py --grep "<PRODUCT NAME>"
```

## 7. Still broken upstream

- `friends invite-link` → **403** from
  `steamcommunity.com/actions/QuickInviteLink`; the server-side endpoint changed.
  Do not retry-loop it.
- `steam launch` uses the `steam://` protocol, which is meaningless on a headless
  host.
- Store requests hardcode `l=english&cc=us`, so results and prices are US/English
  regardless of the account's region.

## Reproducing the checks locally

```bash
steam doctor                        # probe the endpoints this CLI depends on
steam status                        # session + Web API key state
.venv/bin/python -m pytest -q       # unit tests
.venv/bin/ruff check src tests tools
.venv/bin/mypy src
```
