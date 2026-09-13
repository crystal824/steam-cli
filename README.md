# steam-cli

[![CI](https://github.com/crystal824/steam-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/crystal824/steam-cli/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://github.com/crystal824/steam-cli)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**中文版** → [README.zh-CN.md](README.zh-CN.md)

A safe, controllable Steam CLI for the [Hermes](https://agentskills.io) agent.

`steam-cli` lets an agent operate a Steam account in plain language: search the store,
read a game's reception before buying, manage the library and wishlist, activate CD
keys, post reviews, check friends and playtime — behind a strict safety policy, and
without ever touching money or account security.

## What it does

| Area | Commands | Credentials |
|---|---|---|
| Auth | `login` `status` `logout` `set-key` `refresh` `revoke-all` | — |
| Diagnostics | `doctor` | — |
| Store | `search` `app` `price` `news` `radar` `profile` | key for `news`/`radar` |
| Reviews | `review summary` `review list` `review mine` `review post` | session for `mine`/`post` |
| Library | `library list` `library has` | key |
| Wishlist | `wishlist list` `add` `remove` `on-sale` | key; session for `add`/`remove` |
| Activation | `activate <cdk> [--batch file]` | session + confirmation |
| Friends | `friends list` `playing` `recently-played` `invite-link` | key; session for `invite-link` |
| Stats | `stats summary` `stats game` | key |
| Achievements | `achievements` | key + session |
| Settings | `config proxy …` `config region …` | — |
| More | `launch` `recommend` | key for `recommend` |

"key" is a Steam Web API key (read-only, `steam set-key`); "session" is a logged-in
session (`steam login`), required by anything that writes. Run `steam status` to see
what is configured. Store queries (`search`, `app`, `price`, `profile`,
`review summary`, `review list`) need no credentials at all.

**There is no `steam auth …` subcommand.** Upstream documentation predates the
shipped CLI — every command above is top-level.

## Install

From a checkout:

```bash
pip install .
steam --help
```

Or from a release wheel — `steam_cli-<version>-py3-none-any.whl` on the
[latest release](https://github.com/crystal824/steam-cli/releases/latest). (Not on
PyPI.)

Requires Python ≥ 3.11. Dependencies: `typer`, `rich`, `steam` (ValvePython),
`httpx`, `keyring`.

## Quick start

```bash
# Store queries need no credentials
steam search "black myth" --limit 5
steam app 2358720
steam price 2358720                       # in your account's region and currency

# Read a game's reception before buying (no credentials either)
steam review summary 1144200

# Read-only account data needs a Web API key
steam set-key <your_key>                  # https://steamcommunity.com/dev/apikey
steam library list --sort playtime
steam wishlist on-sale

# Anything that writes needs a login session
steam login                               # Steam Guard / captcha, once
steam activate XXXXX-XXXXX-XXXXX
steam review post 2807960 --text "It comes with a wheel on every seat."

# Optional: historical lows need an IsThereAnyDeal developer key
export STEAM_CLI_ITAD_KEY=<itad_key>
steam price 2358720
```

## Reading a game's reception

`steam review summary <appid|title>` is the command to reach for when the question is
"is this game any good" — including for games you do not own, which is what makes it
usable for a purchase recommendation:

- **the score band**, in Steam's English wording *and* the Chinese store's
  (`Overwhelmingly Positive` / `好评如潮`, `Mixed` / `褒贬不一`, …), with the positive
  share and the total review count
- **the recent picture** — sampled client-side from the newest reviews, because Steam
  retired the `day_range` parameter (it answers the all-time numbers verbatim)
- **pros-and-cons material** — the most helpful positive and negative reviews, each
  with its vote count, language and the author's playtime

```bash
steam review summary 1144200                     # 8 samples per side; -s 12 for more
steam review summary "Elden Ring" -L schinese    # Chinese reviews only
steam review summary 1144200 --json              # for an agent to parse
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

The human-readable output labels its sections in Chinese (好友/差评 samples, 总评, 近期) and
prints the score band as `中文档位 (English band)` — this CLI is driven from a
Chinese-language account. `--json` is language-neutral.

The CLI does not summarise anything itself: it hands over the band, the numbers and the
samples, and the agent writes the "what's good / what's bad". Two habits matter when you
do — quote the band, the share and how many samples you actually read; and for a
Chinese-speaking user run it twice (`-L all` and `-L schinese`), because the two views
can differ by a whole band (they did for the *Ni no Kuni* games and for *Ready or Not*).

## Store region and language

Store requests follow **your account**: the country is read from the account page's
`country_code` (cached for a day) and the language derived from it (cn → schinese,
jp → japanese, …). A Chinese account is quoted ¥ and gets Chinese store text, instead
of the USD and English every request used to hardcode.

```bash
steam status                                     # … Region: cn (schinese) — account
steam config region show                         # what is in use, and where it came from
steam config region set cn --lang schinese       # pin it instead of following the account
steam config region clear                        # follow the account again
steam price 1144200 --cc us                      # one-off: compare another region
```

`STEAM_CLI_CC` / `STEAM_CLI_LANG` do the same for a single shell.

## Credentials

- `steam set-key <key>` stores a Web API key for read-only account queries.
- `steam login` runs Steam's current web login (RSA key exchange,
  `IAuthenticationService`, app approval or a Steam Guard code) and keeps both a session
  and a long-lived **refresh token** — so a session that simply expired is rebuilt with
  `steam refresh --remint`: no password, no 2FA. `steam logout` clears the session but
  keeps that token on purpose; `steam revoke-all` wipes everything.
- Credentials live in the OS keyring; where there is none (a headless NAS, say), they
  fall back to `~/.config/steam-cli/*.secret` with mode `0600`. The account password is
  never stored.
- `steam logout` clears the session; `steam revoke-all` wipes every stored credential.
- Write operations append to `~/.config/steam-cli/audit.log`.

## Safety policy

- **Refused outright**: purchases, payments, trading, changing email/phone, or any
  account-security change.
- `activate` is the only command that asks for confirmation (its own prompt, or
  `--yes`). Everything else that writes — `wishlist add/remove`, `review post` —
  publishes as soon as it runs and has **no prompt**, so the caller must have the
  user's intent (and for a review, the wording) first. `--dry-run` previews the
  request without sending it.
- `review post` reads the review back from your profile afterwards
  (`--verify/--no-verify`, on by default), because Steam answering `{"success": true}`
  is not proof the review is visible.
- Login and activation challenges (captcha / Steam Guard / 2FA) are handed back to the
  user — never auto-retried, never bypassed.
- A review needs at least 5 minutes of playtime on the product; Steam enforces that and
  the CLI surfaces its message as the structured `review_rejected` error.

## How it talks to Steam

- **① Public API** — the official Web API with a key: library, friends, stats, news,
  achievements.
- **② Session API** — reads that need a login: wishlist, your own reviews.
- **③ Web-session simulation** — no public API exists, so these call exactly what the
  official web front-end calls: CDK activation, wishlist writes, review posting, friend
  invite links. The least stable and most ToS-sensitive layer; endpoints change without
  notice.

`steam doctor` probes the endpoints each layer depends on.

## Compatibility with current Steam (2026)

Valve retired or reworked several endpoints this CLI was originally built on. Each
failure looked like "bad credentials" but was a dead endpoint; what changed, how the
symptom presents and where the fix lives is documented in
[docs/steam-endpoint-changes-2026.md](docs/steam-endpoint-changes-2026.md). Worth
knowing up front:

- **`steam review post` used to publish nothing while reporting success** — it posted to
  a community *page* and only checked for HTTP 200. It now uses the store front-end's
  `friends/recommendgame` endpoint with the parameters that front-end sends, and parses
  the JSON reply: a refusal becomes the structured `review_rejected` error instead of a
  fake success, and a non-JSON body raises `network_error` rather than passing.
- **Login was rebuilt, and now lives in the CLI.** `steam login` drives Steam's
  current flow (`IAuthenticationService`: approve in the mobile app or type a Steam
  Guard code, then `finalizelogin` + the per-domain settoken calls). A session that has
  merely expired is rebuilt from the stored refresh token with `steam refresh --remint`
  — no password, no 2FA. `tools/steam_modern_login.py` / `tools/steam_remint_session.py`
  remain as JSON-emitting wrappers for automation.
- **Verify activations** with `tools/check_licenses.py`: `GetOwnedGames` carries no
  acquisition timestamp, so the account licenses page (date + method) is the only proof
  that a key landed.
- `steam friends invite-link` answers **403** — Valve changed that endpoint server-side;
  it is not fixable locally.
- Two quirks in the installed `steam` package need local patches — see
  [`patches/`](patches/README.md).
- Chinese store search cannot find every translated title (the community index resolves
  黑神话 to an unrelated knock-off, and 二之国 to nothing at all). CJK titles are looked
  up through the Simplified-Chinese store search instead; when that misses too, use the
  English title or the appid.

## Development

```bash
pip install -e ".[dev]"     # or: uv sync (uv.lock pins the versions)
pre-commit install

ruff check src tests tools
ruff format --check src tests tools
mypy src
PYTHONPATH=src python3 -m pytest -q
```

Those four gates are what CI enforces (87 tests at v0.2.5). `make test`, `make build`
and `make build-skill` wrap the common ones.

Testing principles: read-only features are safe to exercise against live endpoints;
write operations — above all `activate` — are **never** run against a primary account.
Use an isolated test account, and prefer HTTP record/replay for CI.

## Release

```bash
python -m pip install build twine
python -m build --outdir dist/python
python scripts/build_skill.py --output-dir dist/skill
python -m twine check dist/python/*
```

Two artifacts ship per release: the Python package (runtime code under `src/` only) and
the Hermes Skill archive (`steam-skill-<version>.tar.gz`). The release procedure: write
the notes in `docs/releases/<tag>.md` — **Chinese first, then English** — bump the
version in *both* `pyproject.toml` and `uv.lock`, push `main`, then push the tag. CI
verifies the tag against `pyproject.toml`, builds both artifacts, publishes the Release
from those notes and commits the regenerated `CHANGELOG.md` back to `main`. See
[docs/releases/README.md](docs/releases/README.md) and
[CONTRIBUTING.md](CONTRIBUTING.md).

## Hermes Skill

The agent-facing Skill lives in [`skill/steam/`](skill/steam) and ships as the separate
`steam-skill-<version>.tar.gz` artifact. Extract it to `~/.hermes/skills/steam/` to
expose these capabilities to Hermes — the Skill documents the same commands plus the
agent-oriented rules: when to ask first, what to verify afterwards, and which traps have
already been paid for.

## License

MIT — see [LICENSE](LICENSE).
