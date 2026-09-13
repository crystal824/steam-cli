# Auth & credentials

## Web API key (read-only, layer ①)

Some commands (search, app, price, news, achievements) work with just a Web API key.

1. Have the user open https://steamcommunity.com/dev/apikey (must be signed into Steam in the browser).
2. Fill in a domain (any string is accepted) and agree to the terms.
3. Store it: `steam set-key <key>`.

Verify with `steam status` (shows "Web API key: set" and whether it is valid).

**Optional: IsThereAnyDeal key for price history.** `steam price` shows the
historical low only when `STEAM_CLI_ITAD_KEY` is set (register at
isthereanydeal.com → developer). Without it the CLI prints a hint instead of
failing.

## Login session (layer ②/③)

Write operations and personal reads need a login session:

```bash
steam login            # or: steam login --username <name>
```

**Since 2026-09-13** `steam login` drives Steam's current flow itself
(`IAuthenticationService` → `finalizelogin` → per-domain settoken); ValvePython's
retired `/login/dologin/` path is no longer involved. If a session merely expired,
`steam refresh --remint` rebuilds it from the stored refresh token with no password and
no 2FA — a full login is only needed once that token expires. The prompts below apply:

- **Steam Guard mobile code** — user enters the code from the Steam app.
- **Email code** — user enters the code sent to their email.
- **Captcha / other challenges** — the CLI stops and hands control back to the user.

Rule: never auto-retry or attempt to bypass these challenges programmatically. If one appears, ask the user and pass the input through.

After a successful login the session cookies **plus a long-lived refresh token** are stored, so subsequent operations (`activate`, wishlist writes, reviews, invite links) reuse them without re-login. `steam status` / `steam refresh` check the session; when it has gone invalid, re-mint it from the refresh token with `tools/steam_remint_session.py --save` — no password and no 2FA. A full login is only needed once the refresh token itself expires.

## Session storage

High-sensitivity secrets (Web API key, session cookies, session id, steam id, username) are stored through the OS keyring via the `keyring` library under the service name `steam-cli` (Keychain / Credential Manager / Secret Service). If the keyring is unavailable it falls back to local `.secret` files under `~/.config/steam-cli` (override with `$STEAM_CLI_HOME`), created with mode 0600. Low-sensitivity caches (e.g. appid index) are plain local files.

**Headless hosts:** without a Secret Service (servers, containers, NAS), `keyring`
resolves to the *fail* backend and every secret lands in `~/.config/steam-cli/<key>.secret`
with mode 0600. That fallback is expected — check the state with `steam status`.

## Proxy

Steam services can be unstable in some regions (e.g. mainland China). Ask the user for their proxy server details and configure a single proxy that applies to every Steam request (Web API, sessions, store, community):

```bash
steam config proxy set http://user:pass@127.0.0.1:7890   # full URL, or:
steam config proxy set --host 127.0.0.1 --port 7890 --username u --password p
steam config proxy test                                   # verify it reaches Steam
steam config proxy show                                   # masked view
steam config proxy unset                                  # remove it
```

The proxy URL (including credentials) is stored in the OS keyring like the other secrets. Supported schemes: `http`, `https`, `socks4`, `socks5`, `socks5h` (SOCKS needs `PySocks`/`socksio` installed). The proxy also applies to `steam login`.

## Emergency wipe

If credentials are suspected leaked:

```bash
steam revoke-all
```

This clears every locally stored credential (session and API key). Log out of a single session with `steam logout`.
