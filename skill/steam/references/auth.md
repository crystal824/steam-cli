# Auth & credentials

## Web API key (read-only, layer ①)

Some commands (search, app, price, news, achievements) work with just a Web API key.

1. Have the user open https://steamcommunity.com/dev/apikey (must be signed into Steam in the browser).
2. Fill in a domain (any string is accepted) and agree to the terms.
3. Store it: `steam auth set-key <key>`.

Verify with `steam auth status` (shows "Web API key: set" and whether it is valid).

**Optional: IsThereAnyDeal key for price history.** `steam price` shows the
historical low only when `STEAM_CLI_ITAD_KEY` is set (register at
isthereanydeal.com → developer). Without it the CLI prints a hint instead of
failing.

## Login session (layer ②/③)

Write operations and personal reads need a login session:

```bash
steam auth login            # or: steam auth login --username <name>
```

The CLI uses `steam.webauth.WebAuth` to log in interactively. It prompts for the password and handles:

- **Steam Guard mobile code** — user enters the code from the Steam app.
- **Email code** — user enters the code sent to their email.
- **Captcha / other challenges** — the CLI stops and hands control back to the user.

Rule: never auto-retry or attempt to bypass these challenges programmatically. If one appears, ask the user and pass the input through.

After a successful login the session cookies are stored, so subsequent operations (`activate`, wishlist writes, reviews, invite links) reuse it without re-login. `steam auth refresh` checks the session; if it has gone invalid, re-run `steam auth login`.

## Session storage

High-sensitivity secrets (Web API key, session cookies, session id, steam id, username) are stored through the OS keyring via the `keyring` library under the service name `steam-cli` (Keychain / Credential Manager / Secret Service). If the keyring is unavailable it falls back to local `.secret` files under `~/.config/steam-cli` (override with `$STEAM_CLI_HOME`), created with mode 0600. Low-sensitivity caches (e.g. appid index) are plain local files.

## Proxy

Steam services can be unstable in some regions (e.g. mainland China). Ask the user for their proxy server details and configure a single proxy that applies to every Steam request (Web API, sessions, store, community):

```bash
steam config proxy set http://user:pass@127.0.0.1:7890   # full URL, or:
steam config proxy set --host 127.0.0.1 --port 7890 --username u --password p
steam config proxy test                                   # verify it reaches Steam
steam config proxy show                                   # masked view
steam config proxy unset                                  # remove it
```

The proxy URL (including credentials) is stored in the OS keyring like the other secrets. Supported schemes: `http`, `https`, `socks4`, `socks5`, `socks5h` (SOCKS needs `PySocks`/`socksio` installed). The proxy also applies to `steam auth login`.

## Emergency wipe

If credentials are suspected leaked:

```bash
steam auth revoke-all
```

This clears every locally stored credential (session and API key). Log out of a single session with `steam auth logout`.
