---
name: steam
description: Operate the user's Steam account via steam-cli — activate CD keys, search store, manage wishlist and library, post reviews, check friends and playtime, generate friend invite links, get price history and recommendations. Use when user mentions Steam, game activation, wishlist, library, Steam friends, or game reviews.
---

# Steam

Operate the user's Steam account via the `steam` CLI.

## Command names — top level, NOT `steam auth …`

The commands are top-level: there is **no `auth` subcommand** (`steam auth status`
fails with "No such command 'auth'"). Run `steam status` on its own.

- `steam login [--username NAME]` — interactive login
- `steam status` — login + Web API key state (run this first)
- `steam logout` / `steam refresh` / `steam revoke-all`
- `steam set-key <web_api_key>` — Web API key for read-only queries
- `steam doctor` — probe the endpoints this CLI depends on

## Operating rules

- Always start with `steam status`; a session that has gone invalid is re-minted
  (no password, no 2FA) with `steam refresh --remint` — the tools script of the same
  name is a JSON-emitting wrapper around that code path.
- Public store queries (`search`, `app`, `price`, `radar`) need no credentials at
  all. Library / wishlist / friends / stats / news / achievements need a Web API key.
- Write operations — `activate`, `wishlist add`/`remove`, `review post`,
  `friends invite-link --refresh` — require explicit user intent; batch activation
  previews the whole batch and confirms once, never per key.
- `steam review post` publishes **immediately** — there is no confirmation prompt, so
  draft the wording and get the user's approval first. Steam requires **at least 5
  minutes of playtime** on the product before it accepts a review, and the review's
  language is set with `-L` (default: the store language resolved from the account —
  `schinese` for a Chinese account). Note that `activate` is the **only** command with
  a CLI confirmation prompt; the rest of this list publishes as soon as it runs.
- A message that is *only* a product key (`XXXXX-XXXXX-XXXXX`, or 5 groups of 5)
  means "activate this": validate with `--dry-run` first, then activate, then report
  the product name or the structured reason. Never echo the full key back.
- If a captcha or another challenge appears, hand control back to the user — never
  auto-retry and never attempt a programmatic bypass.
- Money, purchases, trading, and account-security changes are refused outright.
- Prefer CLI subcommands over hand-crafted HTTP requests.
- Surface the structured error type (`invalid_format` / `already_activated` /
  `already_owned` / `region_locked` / `invalid_key` / `rate_limited` /
  `network_error` / `session_expired` / `not_authenticated` / `api_key_missing`)
  along with the raw CLI output when useful.

## Activation semantics

`already_activated` and `already_owned` (Steam result code 9) mean the key **was
consumed earlier** — report them as "already in your library", never as a failure.
Re-submitting a key is therefore a safe check: if the key had never worked, the
response would be `invalid`.

## Verifying that something landed

`GetOwnedGames` carries no acquisition timestamp, and playtime can predate a key
(the account may have played a Playtest build), so a library listing cannot prove
*when* something was added. Use the licenses page instead — it carries the date and
method (`Retail` = key/CDK, `Steam Store` = purchase, `Gift/Guest Pass` = gift):

```bash
.venv/bin/python tools/check_licenses.py --grep "<PRODUCT>"
```

## Command quick reference

Auth & status
- `steam login` · `steam status` · `steam logout` · `steam set-key <key>` ·
  `steam refresh` · `steam revoke-all` · `steam doctor`

Proxy (network fallback)
- `steam config proxy set <url>` or `--host/--port [--username/--password]`
- `steam config proxy show | test | unset`

Price history
- `steam price <appid|name>` shows the historical low only when the env var
  `STEAM_CLI_ITAD_KEY` is set (IsThereAnyDeal developer key).

Store & discovery
- `steam search <query> [--limit N] [--type game|dlc|software|all]`
- `steam app <appid|name>` · `steam price <appid|name>` · `steam news <appid> [--count N]`
- `steam radar [--wishlist] [--library-never-played]`
- `steam profile <steamid|vanity>`

Library & wishlist
- `steam library list [--recent] [--never-played] [--sort name|playtime|added]`
- `steam library has <appid|name>`
- `steam wishlist list | add <id> [--dry-run] | remove <id> | on-sale`

Activation & reviews
- `steam activate <cdk> [--batch <file>] [--dry-run] [--yes]`
- `steam review post <appid> --text "..." [--recommend|--not-recommend] [--language/-L <code>] [--private] [--verify/--no-verify] [--dry-run]`
- `steam review list <appid> [--mine] [--language/-L <code>|all] [--limit/-n N]`
- `steam review mine` — every review this account has posted
- `steam review summary <appid|title> [--language/-L all] [--samples/-s 8] [--days/-d 30] [--json]`
  — the review score band (好评如潮 / 特别好评 / 褒贬不一 …), the recent picture, and the
  most-helpful positive/negative reviews. Use it to answer "how is this game received": read the
  samples and distill 好在哪 / 不好在哪 yourself; real appids (2807960) and titles ("黑神话", "Elden
  Ring") both work.

Friends, stats & more
- `steam friends list [--online] | playing <appid> | recently-played | invite-link [--refresh]`
- `steam stats summary | game <appid>`
- `steam achievements <appid> [--missing] [--rarity]`
- `steam recommend [--based-on library|wishlist] [--limit N]`
- `steam launch <appid|name>`

## Known limitations (current Steam backend)

- **Login runs Steam's current flow** (`IAuthenticationService` → `finalizelogin` →
  settoken; the retired `/login/dologin/` path is gone). Approve in the mobile app or
  pass the Guard code; an expired session is rebuilt with `steam refresh --remint`
  (refresh token, no password, no 2FA). `steam status` is the probe to trust — it
  follows redirects, so it no longer cries "expired" during a store bootstrap 302.
- `steam friends invite-link` returns **403** (`steamcommunity.com/actions/QuickInviteLink`
  changed server-side). Do not retry-loop it.
- Store requests follow the account's store region and language (auto-detected,
  cached a day; `steam config region set|show|clear`, or `--cc/--lang` per call).
  For a region whose search index lacks a translated name, fall back to the English
  title or an appid; do not
  conclude "the game does not exist" from an empty Chinese search.
- `steam launch` needs a desktop Steam client, so it is pointless on a headless host.
- `steam recommend` / `radar` issue one price request per appid and are slow.

See [`../../docs/steam-endpoint-changes-2026.md`](../../docs/steam-endpoint-changes-2026.md)
for the full endpoint-by-endpoint breakdown.
