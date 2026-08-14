# steam-cli

A safe, controllable Steam CLI for the [Hermes](https://agentskills.io) agent.

`steam-cli` lets an agent operate a user's Steam account through natural
language — search the store, manage the library and wishlist, activate CD keys,
post reviews, check friends and playtime, and more — while enforcing a strict
safety policy.

## Features

| Area | Commands |
|------|----------|
| Auth | `steam auth login / status / logout / set-key / refresh / revoke-all`, `steam doctor` |
| Store | `steam search`, `app`, `price`, `news`, `radar` |
| Library | `steam library list`, `library has` |
| Wishlist | `steam wishlist list / add / remove / on-sale` |
| Activation | `steam activate <cdk> [--batch file] [--dry-run]` |
| Reviews | `steam review post`, `review list` |
| Friends | `steam friends list / playing / recently-played / invite-link`, `steam profile` |
| Stats | `steam stats summary`, `stats game` |
| More | `steam launch`, `achievements`, `recommend` |

## Install

```bash
pip install .
steam --help
```

Dependencies: `typer`, `rich`, `steam` (ValvePython), `httpx`, `beautifulsoup4`,
`keyring`.

## Quick start

```bash
# Read-only store queries need no credentials
steam search "black myth" --limit 5
steam app 2358720
steam price 2358720

# Library / friends / stats need a Web API key (read-only)
steam auth set-key <your_key>          # from https://steamcommunity.com/dev/apikey

# Wishlist writes, CDK activation, reviews, invite links need a login session
steam auth login                       # one-time Steam Guard / captcha flow
steam library list
steam activate XXXXX-XXXXX-XXXXX
steam wishlist add "Elden Ring"
```

## Safety policy

- **Forbidden**: purchases, payments, trading, changing email/phone, or any
  account-security change. The CLI refuses these outright.
- Write operations (`activate`, `wishlist add/remove`, `review post`,
  `friends invite-link --refresh`) support `--dry-run` and require confirmation.
- Batch activation (`--batch`) previews the whole batch and confirms once, with
  pacing between keys.
- Login and activation challenges (captcha / Steam Guard / 2FA) are always
  handed back to the user — never auto-retried or bypassed.
- All sensitive credentials live in the OS keyring; only low-sensitivity caches
  touch local files. A local audit log records every write operation.

## Technical layers

- **① Public API** — official Web API key (search, library, friends, stats,
  news, achievements). Stable and documented.
- **② Session API** — read operations that need a logged-in session
  (wishlist list).
- **③ Web-session simulation** — CDK activation, wishlist writes, review
  posting, friend invite links. These have no public API and rely on calling the
  endpoints the official web front-end uses. They are the least stable and the
  most ToS-sensitive; the endpoints may change at any time.

Run `steam doctor` to probe endpoint availability.

## Development

```bash
PYTHONPATH=src python3 -m steam_cli.main --help
PYTHONPATH=src python3 -m pytest
```

## Hermes Skill

The agent-facing Skill lives in [`skill/steam/`](skill/steam/). Install it to
`~/.hermes/skills/steam/` to expose these capabilities to Hermes.
