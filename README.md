# steam-cli

[![CI](https://github.com/crystal824/steam-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/crystal824/steam-cli/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://github.com/crystal824/steam-cli)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A safe, controllable Steam CLI for the [Hermes](https://agentskills.io) agent.

`steam-cli` lets an agent operate a user's Steam account through natural
language — search the store, manage the library and wishlist, activate CD keys,
post reviews, check friends and playtime, and more — while enforcing a strict
safety policy.

## Features

| Area | Commands |
|------|----------|
| Auth | `steam auth login / status / logout / set-key / refresh / revoke-all`, `steam doctor` |
| Proxy | `steam config proxy set / show / test / unset` |
| Store | `steam search`, `app`, `price`, `news`, `radar` |
| Library | `steam library list`, `library has` |
| Wishlist | `steam wishlist list / add / remove / on-sale` |
| Activation | `steam activate <cdk> [--batch file] [--dry-run] [--yes]` |
| Reviews | `steam review summary`, `steam review post`, `review list`, `review mine` |
| Friends | `steam friends list / playing / recently-played / invite-link`, `steam profile` |
| Stats | `steam stats summary`, `stats game` |
| More | `steam launch`, `achievements`, `recommend` |

## Install

```bash
pip install .
steam --help
```

Dependencies: `typer`, `rich`, `steam` (ValvePython), `httpx`, `keyring`.

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

# Price history needs an IsThereAnyDeal developer key (optional)
export STEAM_CLI_ITAD_KEY=<itad_key>
steam price 2358720                    # includes historical low
```

## Compatibility with current Steam (2026)

Valve retired several endpoints this CLI was originally built on — web login, CDK
activation, wishlist reads and batched app lookups. Those paths have been reworked;
the details, symptoms and one remaining server-side breakage are documented in
[docs/steam-endpoint-changes-2026.md](docs/steam-endpoint-changes-2026.md).

Practical consequences:

- **`steam login` may report success yet produce a session that authenticates
  nothing** (ValvePython still posts to the retired `/login/dologin/`). Use
  `tools/steam_modern_login.py` instead; afterwards
  `tools/steam_remint_session.py` re-authenticates from the stored refresh token
  with **no password and no 2FA**.
- **Verify activations** with `tools/check_licenses.py`, which reads the account
  licenses page (acquisition date + method). `GetOwnedGames` has no acquisition
  timestamp, so a library listing cannot prove when something was added.
- `steam friends invite-link` currently returns **403** — Steam changed that
  endpoint server-side.
- Store queries follow **your account's region and language** (detected from the
  account page, cached for a day): a Chinese account gets ¥ prices and Chinese
  store text. Override per call with `--cc/--lang` (e.g. `steam price 1144200 --cc us`)
  or permanently with `steam config region set cn --lang schinese`; `STEAM_CLI_CC` /
  `STEAM_CLI_LANG` do the same for one shell. `steam config region show` prints what is
  in use and where it came from.
- A couple of quirks in the installed `steam` package need local patches; see
  [`patches/`](patches/README.md).

## Proxy

Steam services can be unstable in some regions. Configure one proxy that
applies to **every** request (Web API, sessions, store, community):

```bash
steam config proxy set http://user:pass@127.0.0.1:7890   # full URL, or:
steam config proxy set --host 127.0.0.1 --port 7890 --username u --password p
steam config proxy test                                   # verify it reaches Steam
steam config proxy show                                   # masked view
steam config proxy unset
```

The proxy URL (credentials included) is stored in the OS keyring. Supported
schemes: `http`, `https`, `socks4`, `socks5`, `socks5h`.

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
pip install -e ".[dev]"     # 或：uv sync（使用 uv.lock 锁定版本）
pre-commit install          # 提交前自动检查

ruff check src tests        # 代码规范
ruff format --check src tests
mypy src                    # 类型检查
PYTHONPATH=src python3 -m pytest -q
```

## Release

The Python CLI and Hermes Skill are released as separate artifacts. Install the
release tooling and build both artifacts with:

```bash
python -m pip install build twine
python -m build --outdir dist/python
python scripts/build_skill.py --output-dir dist/skill
python -m twine check dist/python/*
```

The installed Python package contains only the runtime code under `src/`; the
Skill is published as `dist/skill/steam-skill-<version>.tar.gz`.

Testing principles: read-only features are safe to exercise against live
endpoints; write operations (especially `activate`) are **never** run against
the user's main account — use an isolated test account, and never run
automated tests on a primary account. Prefer HTTP recording/playback for CI.

CI (GitHub Actions) runs `ruff` + `mypy` + `pytest` and validates release
artifacts on every push; the
`v*` tag release workflow generates the CHANGELOG and publishes a GitHub
Release automatically. See `CONTRIBUTING.md` for details.

## Hermes Skill

The agent-facing Skill lives in
[`skill/steam/`](https://github.com/crystal824/steam-cli/tree/main/skill/steam)
and is released separately. Extract its archive to `~/.hermes/skills/steam/` to
expose these capabilities to Hermes.
