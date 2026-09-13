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
| Reviews | `POST /profiles/<steamid>/recommended/` | `POST /friends/recommendgame` (JSON) | HTTP 200 + HTML counted as success — nothing was ever published |
| Store region | every store call sent `l=english&cc=us` | resolved from the account page (`country_code`), cached daily | a CN account was quoted USD and got English text |
| Recent review score | `appreviews?day_range=30` | parameter retired — sample the newest reviews client-side | "recent" numbers silently equal the all-time ones |
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
`patches/steam-1.4.4-webauth-transfer-info.patch` — kept for reference only: since
2026-09-13 `steam login` implements the flow itself (`src/steam_cli/modern_login.py`)
and no longer touches `WebAuth`, so neither this patch nor the one below is needed to
use the CLI.

### 2026-09-13 — the flow now lives in the CLI

`steam login` runs all of the above (app approval or Guard code → poll → finalize →
settoken), and `steam refresh --remint` replays the last three steps from the stored
refresh token, so an expired session is rebuilt without a password. The two scripts in
`tools/` are now thin JSON-emitting wrappers around the same code. Two traps surfaced
while wiring it:

- **A "is this session valid?" probe must follow redirects.** The store answers a first
  request to `/account/` with a 302 to itself while it bootstraps cookies, so the old
  "no redirects, require 200" check reported healthy sessions as expired
  (`steam status` → `Session valid: no`) and sent people off to re-login for nothing.
  It is `auth.probe_authed()` now: follow, then require 200 and a landing URL that is
  not `/login/`.
- **Any page parsed as HTML needs `?l=english`.** A re-minted session carries
  `Steam_Language` from the account, so `steamcommunity.com/profiles/<id>/recommended/`
  renders as 推荐 / 发布于 / 小时 / 可见性 and an English-only parser silently blanks the
  date, playtime and visibility columns (`steam review mine` did exactly that). The
  verdict is read from the `icon_thumbsUp/Down` files, which do not move between
  languages. `tools/check_licenses.py` pins `l=english` for the same reason.

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

## 3. Reviews — posting went nowhere

`steam review post` submitted to
`https://steamcommunity.com/profiles/<steamid>/recommended/`, which is only a
**page**: a POST there answers HTTP 200 with HTML and saves nothing. Because the
code tested nothing but `status_code == 200`, it printed `Review posted.` while
publishing nothing at all — a silent no-op that survived every earlier test
because it had only ever been run with `--dry-run`.

The real endpoint is the one the store front-end uses
(`public/javascript/main.js` → `RecommendGame()`):

```
POST https://store.steampowered.com/friends/recommendgame
     appid=<appid>&steamworksappid=<appid>&comment=<text>&rated_up=<true|false>
     &is_public=<true|false>&language=<steam language code>
     &received_compensation=0&disable_comments=0&saved_hardware_id=
     &sessionid=<sessionid>
     Referer: https://store.steampowered.com/app/<appid>/
     Origin:  https://store.steampowered.com
     X-Requested-With: XMLHttpRequest
```

- `{"success": true}` → published.
- `{"success": false, "strError": "..."}` → structured failure. Steam enforces its
  own rules here; the first one you meet is *"You need to have used this product
  for at least 5 minutes before posting a review for it"*.
- `{"success": false}` **without** `strError` → the session was not accepted
  (`session_expired`).
- A **non-JSON body** now raises `network_error` ("the endpoint may have moved")
  instead of counting as success, which is how the old code lied.

Reading reviews back is the other half of the fix. The public
`appreviews/<appid>` feed cannot answer "my review": it returns only the newest
page (top titles have >1M reviews) and filters by language, so the old `--mine`
filter could never match an account that writes Chinese. `steam review mine` and
`review list --mine` now parse the account's own
`/profiles/<steamid>/recommended/` page instead, which is authoritative.

### Reading the summary

`query_summary` still carries the useful part — `review_score` (band 0-9, e.g. 9 =
Overwhelmingly Positive / 好评如潮, 5 = Mixed / 褒贬不一) plus the positive/negative/total
counts. Two traps:

- **`day_range` is retired.** `appreviews/<appid>?day_range=30&num_per_page=0` answers the
  *all-time* summary, byte-identical to the same request without it, so a "recent reviews"
  figure taken from it is silently wrong. `steam review summary --days N` therefore samples
  client-side: `filter=recent` returns newest-first, so it walks pages until it crosses the
  cut-off (exact for the window, or flagged `truncated` when the window holds more than the
  400-review cap).
- **Review text is double-escaped.** Newlines arrive as the two characters `\n`, not as a
  line break, so anything that strips or re-wraps the text must normalise `\n`/`\r` first.
- **The review listing collapses on obscure titles — three traps, all found by trying a small
  game (Wenjia, 374 reviews; 2026-09-13):**
  1. `filter=all` (the "most helpful" ranking) can be **all but empty**: Wenjia ranks exactly
     **one** review that way, while `filter=recent` returns a full, correctly-sized page (100
     of its 374, 65 up / 35 down). Anything that reads only `filter=all` will show a single
     "sample" and look broken. Merge both filters.
  2. `review_type=positive|negative` is **not honoured consistently** — a request for
     `negative` has answered with three *up-voted* reviews. Split the samples client-side on
     each review's own `voted_up`; never label a list by the parameter you asked for.
  3. **The first page needs an explicit `cursor=*`.** Without a cursor Steam can answer with a
     single "featured" review and a cursor that never advances, so paging loops forever on the
     same item. Seed with `cursor=*` and stop when a page adds nothing new.

Titles: the community `SearchApps` index cannot be trusted for CJK (`艾尔登法环` → `[]`,
`黑神话` → a knock-off), so `resolve_appid()` sends CJK terms to
`storesearch` with `l=schinese&cc=cn` first — that returns the real game (`黑神话` →
2358720, `艾尔登法环` → 1245620).

Verify a **just**-published review against that profile page or against the
review's own permalink (`/profiles/<steamid>/recommended/<appid>/`) fetched
**without cookies** — the public feed lags by minutes, and the profile page can
briefly serve a cached copy whose review block has an empty body.

## 4. Wishlist — endpoint replaced

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

## 5. Session cookies — `CookieConflictError`

`requests` rejects `session.cookies.get("sessionid")` when the same cookie name
exists for several domains — which is the normal state of a Steam session, because
the login mirrors cookies onto store / community / help. Every lookup now goes
through `steam_cli.auth.cookie_value(session, name)`, which iterates the jar
instead. Call sites that used to crash: `activate` (×2), `friends`, `review`,
`wishlist`.

## 6. Steam's published API metadata is unreliable

ValvePython's `WebAPI` validates calls against `GetSupportedAPIList` and refuses
to send when a parameter marked "required" is missing. That metadata now disagrees
with the live endpoints: `IPlayerService/GetOwnedGames` demands `appids_filter`,
then `include_free_sub`, while the identical request without them returns HTTP 200
and the complete library. The workaround now ships **inside the package**: `src/steam_cli/_compat.py` marks every
parameter `optional` right after the metadata is loaded, so absent parameters are simply
not sent and Steam validates for real. Without it, a clean `pip install` could not run
`stats summary` / `library list` at all (`Method requires 'appids_filter' to be set`) —
which is precisely why it no longer lives in a patch a user has to apply by hand
(`patches/steam-1.4.4-webapi-required-params.patch` is the historical diff).

## 7. Verifying that something landed

`GetOwnedGames` has **no acquisition timestamp**, and playtime can predate a key
(the user may have played a Playtest build), so neither the library list nor a CLI
success line proves an activation. The authoritative source is the account
licenses page, where each row carries the acquisition **date and method**
(`Retail` = key/CDK, `Steam Store` = purchase, `Gift/Guest Pass` = gift):

```bash
.venv/bin/python tools/check_licenses.py --grep "<PRODUCT NAME>"
```

## 8. Still broken upstream

- `friends invite-link` → **403** from
  `steamcommunity.com/actions/QuickInviteLink`; the server-side endpoint changed.
  Do not retry-loop it.
- `steam launch` uses the `steam://` protocol, which is meaningless on a headless
  host.
- Store requests used to hardcode `l=english&cc=us`; they now follow the account
  (see the region row above).

## 9. Store region and language — no longer hardcoded

Every store call sent `l=english&cc=us`, so a Chinese account was quoted USD prices
and English names. Two things had to be established first (measured 2026-09-13):

- **Steam does not reliably infer the region when `cc` is omitted.** With a logged-in
  session, `appdetails?appids=1144200` answers **CNY**, the same request for appid 220
  answers **USD**, and adding `filters=price_overview` flips 1144200 back to **USD**.
  Never rely on "let Steam decide".
- **The account page is authoritative**: `store.steampowered.com/account/` embeds
  `data-userinfo="{...&quot;country_code&quot;:&quot;CN&quot;...}"` (plus a visible
  `Country:` row), and it is the page `is_session_valid()` already fetches.

`steam_cli/region.py` resolves region/language as: explicit override
(`STEAM_CLI_CC` / `STEAM_CLI_LANG`, or `steam config region set`) → the account page
(cached for a day in `<config>/region.json`) → `us` / `english`. Language defaults to
the country's store language (`cn` → `schinese`, `jp` → `japanese`, …). Call sites pass
`region.store_params({...})` instead of literal `cc`/`l`.

## Reproducing the checks locally

```bash
steam doctor                        # probe the endpoints this CLI depends on
steam status                        # session + Web API key state
.venv/bin/python -m pytest -q       # unit tests
.venv/bin/ruff check src tests tools
.venv/bin/mypy src
```
