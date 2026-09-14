# steam-cli

[![CI](https://github.com/crystal824/steam-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/crystal824/steam-cli/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://github.com/crystal824/steam-cli)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**中文版** → [README.zh-CN.md](README.zh-CN.md)

Browse the Steam store, read a game's reception before buying, manage your library and
wishlist, activate CD keys, post reviews, and check friends and playtime — from the
terminal, behind a strict safety policy: it never touches money, purchases, trading, or
account security.

It is a plain command-line tool. [Hermes](https://agentskills.io) is optional: the
separately published Skill (see [Hermes Skill](#hermes-skill)) only teaches an agent the
same commands.

## What you need

- **Python ≥ 3.11.**
- **Nothing else** to browse the store, check prices, or read reviews.
- For *your* account data (library, stats, friends, wishlist) and for anything that
  writes: a **Steam Web API key** *and* a **signed-in session**. The key authorises the
  call; the session supplies your SteamID. `steam status` prints what is missing, and
  the errors name the command that fixes it.

## Install

```bash
python -m venv .venv && . .venv/bin/activate   # or any environment you like
pip install .                                  # from a checkout
steam --help
```

Or install a published wheel: grab `steam_cli-<version>-py3-none-any.whl` from the
[latest release](https://github.com/crystal824/steam-cli/releases/latest) and
`pip install` it. (Not on PyPI.)

No patching, no post-install steps. Two known quirks of the third-party `steam`
library are worked around inside the package —
[`src/steam_cli/_compat.py`](src/steam_cli/_compat.py) and, for login,
[`src/steam_cli/modern_login.py`](src/steam_cli/modern_login.py) — so a clean install
works as-is. [`patches/`](patches/README.md) keeps the original diffs for reference.

Dependencies: `typer`, `rich`, `steam` (ValvePython), `httpx`, `keyring`.

## Try it in 30 seconds

None of these need an account or any credentials:

```bash
steam search black myth            # multi-word names need no quoting
steam app 2358720
steam price 1144200                # in your region's currency
steam review summary 1144200       # score band + 好评/差评 samples, for a buying decision
steam profile 76561198121699884
```

## Connect your account

```bash
steam set-key <your_key>      # https://steamcommunity.com/dev/apikey — read-only queries
steam login                   # once: your password, then approve in the Steam app or type a code
steam status                  # what is configured, and whether the session still works
```

The session keeps a long-lived refresh token, so when it simply expires you rebuild it
**without a password or 2FA**:

```bash
steam refresh --remint
```

`steam logout` clears the session (and deliberately keeps the refresh token);
`steam revoke-all` wipes every credential. Credentials live in the OS keyring, or in
`~/.config/steam-cli/*.secret` (mode `0600`) where there is no keyring. The account
password is never stored.

## What it does

| Area | Commands | Needs |
|---|---|---|
| Auth | `login` `status` `logout` `set-key` `refresh [--remint]` `revoke-all` | — |
| Diagnostics | `doctor` | — |
| Store | `search` `app` `price` `profile` | — |
| | `news` `radar` | key (`radar` also a login) |
| Reviews | `review summary` `review list` | — |
| | `review mine` `review post` | login |
| Library | `library list` `library has` | key + login |
| Wishlist | `wishlist list` `add` `remove` `on-sale` | key + login |
| Friends | `friends list` `playing` `recently-played` | key + login |
| | `friends invite-link` | login (403 server-side, see below) |
| Stats | `stats summary` `stats game` | key + login |
| Achievements | `achievements` | key + login |
| Activation | `activate <cdk> [--batch file]` | login + confirmation |
| Settings | `config proxy …` `config region …` | — |
| More | `launch` `recommend` | key + login (`launch` needs a desktop Steam client) |

**There is no `steam auth …` subcommand** — every command is top-level. Older upstream
documentation (and some error strings in the third-party library) still spell them with
an `auth` prefix.

`--dry-run` previews any write operation without sending it. `steam <command> --help`
documents the options of each command.

## Reading a game's reception

`steam review summary <appid|title>` is the command to reach for when the question is
"is this game any good" — including for games you do not own:

- **the score band**, in Steam's English wording *and* the Chinese store's
  (`Overwhelmingly Positive` / `好评如潮`, `Mixed` / `褒贬不一`, …), with the positive
  share and the total review count
- **the recent picture**, sampled from the newest reviews
- **pros-and-cons material** — the most helpful positive and negative reviews, each with
  its vote count, language and the author's playtime

```bash
steam review summary 1144200                     # 8 samples per side; -s 12 for more
steam review summary Elden Ring -L schinese      # Chinese reviews only
steam review summary 1144200 --json              # structured, for scripts and agents
```

Real, trimmed output of `steam review summary 1144200 -s 1 --json` (counts move as
reviews come in):

```json
{
  "appid": "1144200",
  "language": "all",
  "overall": {
    "score": 6,
    "label": "多半好评 (Mostly Positive)",
    "positive": 272490,
    "negative": 73463,
    "total": 345953,
    "pct": 78.8
  },
  "recent": {"days": 30, "sampled": 400, "positive": 336, "pct": 84.0, "truncated": true},
  "samples": {
    "positive": [{"votes_up": 63, "language": "russian", "playtime_hours": 33.2, "text": "Ready or Not — это игра, где ты заходишь…"}],
    "negative": []
  }
}
```

The human-readable output labels its sections in Chinese (总评 / 近期 / 好评样本 / 差评样本)
and prints the band as `中文档位 (English band)`; `--json` is language-neutral.

The CLI does not summarise anything itself — it hands over the band, the numbers and the
samples. If an agent writes the summary, tell it to quote the band, the share and how
many samples it read, and for a Chinese-speaking user to run it twice (`-L all` and
`-L schinese`), because the two views can differ by a whole band.

## Store region and language

Store requests follow **your account**: the country is read from the account page's
`country_code` (cached for a day) and the language derived from it (cn → schinese,
jp → japanese, …). A Chinese account is quoted ¥ and gets Chinese store text.

```bash
steam status                                     # … Region: cn (schinese) — account
steam config region show                         # what is in use, and where it came from
steam config region set cn --lang schinese       # pin it instead of following the account
steam config region clear                        # follow the account again
steam price 1144200 --cc us                      # one-off: compare another region
```

`STEAM_CLI_CC` / `STEAM_CLI_LANG` do the same for a single shell.

## Safety

- **Refused outright**: purchases, payments, trading, changing email/phone, or any
  account-security change.
- `activate` is the only command that asks for confirmation (its own prompt, or `--yes`).
  Everything else that writes — `wishlist add/remove`, `review post` — publishes as soon
  as it runs and has **no prompt**, so make sure the intent (and, for a review, the
  wording) is settled first. `--dry-run` previews the request without sending it.
- `review post` reads the review back from your profile afterwards
  (`--verify/--no-verify`, on by default), because Steam answering `{"success": true}` is
  not proof the review is visible. Steam requires **at least 5 minutes of playtime** on
  the product.
- Login and activation challenges (captcha / Steam Guard / 2FA) are handed back to you —
  never auto-retried, never bypassed.
- Every write operation appends to `~/.config/steam-cli/audit.log` (local only).

## Troubleshooting

| Symptom | What it means |
|---|---|
| `not_authenticated: not logged in` | That command needs the session (and usually a key): `steam login` (and `steam set-key <key>`). |
| `session_expired` | Rebuild it without a password: `steam refresh --remint`. |
| `api_key_missing` | `steam set-key <key>` — https://steamcommunity.com/dev/apikey |
| `network_error` | Steam unreachable from here; see [Proxy](#proxy). |
| `review_rejected` | Steam's own reason, verbatim (e.g. under 5 minutes of playtime). |
| `already_activated` | The key was consumed earlier — that is a success, not a failure (see `tools/check_licenses.py`). |
| `steam friends invite-link` → 403 | Valve changed that endpoint server-side; not fixable locally. |
| A Chinese title finds nothing | Steam's search index lacks some translations (`二之国` → nothing, while `Ni no Kuni` works). Use the English title or the appid. |

Deeper background — what Valve retired and how each symptom was fixed — is in
[docs/steam-endpoint-changes-2026.md](docs/steam-endpoint-changes-2026.md).

### Proxy

If Steam is unreachable, configure one proxy that applies to **every** request:

```bash
steam config proxy set http://user:pass@127.0.0.1:7890   # full URL, or:
steam config proxy set --host 127.0.0.1 --port 7890 --username u --password p
steam config proxy test
steam config proxy show        # masked view
steam config proxy unset
```

Supported schemes: `http`, `https`, `socks4`, `socks5`, `socks5h` (SOCKS needs
`PySocks`/`socksio`).

## Repository layout

| Path | What it is | Needed to *use* the CLI? |
|---|---|---|
| `src/steam_cli/` | the CLI itself | it *is* the package |
| `skill/steam/` | the Hermes Skill (agent instructions) | no — for agents only |
| `tools/` | login/recovery helpers and a licence checker; wrappers over the same code | no |
| `patches/` | historical diffs against the `steam` library, superseded by `_compat.py` | no |
| `docs/` | endpoint/behaviour notes, the developer guide, per-version release notes | no |
| `tests/` | offline test suite (107 tests) | no |
| `scripts/`, `Makefile`, `.github/` | release tooling and CI | no |
| `cli`-side extras: `pyproject.toml`, `uv.lock`, `MANIFEST.in`, `cliff.toml` | packaging and the changelog generator | no |

## Hermes Skill

The agent-facing Skill lives in [`skill/steam/`](skill/steam) and ships as a separate
`steam-skill-<version>.tar.gz` artifact. Extract it to `~/.hermes/skills/steam/` to give
Hermes these capabilities — the Skill documents the same commands plus the
agent-oriented rules (when to ask first, what to verify, which traps have been paid for).

## Contributing

```bash
pip install -e ".[dev]"
ruff check src tests tools
ruff format --check src tests tools
mypy src
PYTHONPATH=src python -m pytest -q
```

Those four gates are what CI enforces. Read-only features are safe to exercise against
live endpoints; write operations — above all `activate` — are **never** run against a
primary account. See [CONTRIBUTING.md](CONTRIBUTING.md) for the commit conventions and
[docs/development.md](docs/development.md) for the code map, the region rules and the
traps that have already cost us time. Release notes are per-version files under
[docs/releases/](docs/releases) (see [its README](docs/releases/README.md)).

## License

MIT — see [LICENSE](LICENSE).
