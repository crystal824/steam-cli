---
name: steam
description: Operate the user's Steam account via steam-cli — activate CD keys, search store, manage wishlist and library, post reviews, check friends and playtime, generate friend invite links, get price history and recommendations. Use when user mentions Steam, game activation, wishlist, library, Steam friends, or game reviews.
---

# Steam

Operate the user's Steam account via the `steam` CLI.

## Operating rules

- Always run `steam auth status` first to confirm credentials (login session and/or Web API key).
- If Steam requests fail with `network_error` (or timeouts/connection refused), Steam access may be unstable in the user's region: ask the user for proxy server details (host, port, and optional username/password), then run `steam config proxy set <url>` or `steam config proxy set --host H --port P [--username U] [--password P]`, verify with `steam config proxy test`, and retry. Remove it later with `steam config proxy unset`.
- All write operations — `activate`, `wishlist add`/`remove`, `review post`, `friends invite-link --refresh` — require an explicit second confirmation of user intent, unless the user already said "直接执行" / "just do it". The CLI itself confirms single activations too; pass `--yes` to skip. Batch activation (`--batch`) shows the full preview and confirms once, never per-key.
- The login session is transparent to the user: they log in once (Steam Guard / email / captcha); the program keeps and refreshes the session; later CDK activations reuse it without re-login.
- If login or activation triggers a captcha or any other challenge, hand control back to the user. Never auto-retry or attempt programmatic bypass.
- Any request involving real money, purchases, trading, changing email/phone, or account security → refuse immediately and explain why (safety red line).
- Prefer CLI subcommands; do not hand-craft HTTP requests.
- Output concise tables/lists.
- On error, surface the structured error type (`invalid_format` / `already_activated` / `region_locked` / `invalid_key` / `network_error` / `session_expired` / `not_authenticated` / `api_key_missing`), plus the raw CLI output when useful.

## Command quick reference

Auth & status
- `steam auth login` — interactive login (Steam Guard / email / captcha)
- `steam auth status` — current login + API-key state
- `steam auth logout` — clear saved session
- `steam auth set-key <key>` — store Web API key (read-only queries)
- `steam auth refresh` — check / refresh session
- `steam auth revoke-all` — emergency wipe of all local credentials
- `steam doctor` — probe availability of endpoints

Proxy (network fallback)
- `steam config proxy set <url>` or `--host/--port [--username/--password]`
- `steam config proxy show` — masked view
- `steam config proxy test` — verify the proxy reaches Steam
- `steam config proxy unset`

Store & discovery
- `steam search <query> [--limit N] [--type game|dlc|software|all]`
- `steam app <appid|name>`
- `steam price <appid|name>`
- `steam news <appid> [--count N]`
- `steam radar [--wishlist] [--library-never-played]`

Library & wishlist
- `steam library list [--recent] [--never-played] [--sort name|playtime|added]`
- `steam library has <appid|name>`
- `steam wishlist list | add <id> | remove <id> | on-sale`

Activation & reviews
- `steam activate <cdk> [--batch <file>] [--dry-run] [--yes]`
- `steam review post <appid> --text "..." [--recommend|--not-recommend] [--dry-run]`
- `steam review list <appid> [--mine]`

Friends & profile
- `steam friends list [--online] | playing <appid> | recently-played | invite-link [--refresh]`
- `steam profile <steamid|vanity>`

Stats, launch & more
- `steam stats summary | game <appid>`
- `steam launch <appid|name>`
- `steam achievements <appid> [--missing] [--rarity]`
- `steam recommend [--based-on library|wishlist] [--limit N]` — genre-overlap recommendations

See `references/` for the API map, auth details, safety policy, and examples.
