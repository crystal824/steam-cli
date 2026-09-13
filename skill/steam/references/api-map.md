# API map

Each command is tagged with its technical layer:

- **① Public API** — official Web API (dev key), documented and stable.
- **② Session API** — requires the login session; endpoints are used by the official frontend but not documented for third parties.
- **③ Web-session simulation** — no API exists; drives the official web form/page endpoints via the login session.

| Command | Capability | Layer |
|---|---|---|
| `steam set-key <key>` | store Web API key | ① |
| `steam login` / `status` / `logout` / `refresh` / `revoke-all` | session & key management | ① + ② |
| `steam doctor` | probe endpoint availability | ① + ③ (diagnostic) |
| `steam config proxy set/show/test/unset` | configure & verify a proxy for all requests | local config |
| `steam config region show/set/clear` | store region & language (default: follow the account) | local config |
| `steam search <query>` | store search | ① |
| `steam app <appid\|name>` | app details (price, genres, categories, release, description) | ① |
| `steam price <appid\|name>` | current price + historical low (IsThereAnyDeal, needs `STEAM_CLI_ITAD_KEY`) | ① |
| `steam news <appid>` | app news | ① |
| `steam radar [--wishlist] [--library-never-played]` | discount radar | ② |
| `steam library list` / `has` | owned games, playtime, sort | ① |
| `steam wishlist list` / `on-sale` | wishlist read + sale check | ① (session for private wishlists) |
| `steam wishlist add` / `remove` | wishlist write | ③ |
| `steam activate <cdk>` (incl. `--batch`) | redeem CD key | ③ |
| `steam review post` | publish review | ③ |
| `steam review summary <appid\|title>` | review score band + recent picture + pros/cons samples (`--json`) | ① |
| `steam review list <appid>` | list public reviews (any appid) | ① |
| `steam review list --mine` | your own review for one app | ② |
| `steam review mine` | every review this account has posted | ② |
| `steam friends list` / `playing` / `recently-played` | friend reads | ① |
| `steam friends invite-link [--refresh]` | generate / refresh invite link | ③ |
| `steam profile <steamid\|vanity>` | public profile lookup | ① |
| `steam stats summary` / `game` | playtime statistics | ① |
| `steam launch <appid\|name>` | launch via `steam://run/<appid>` | local protocol |
| `steam achievements <appid>` | achievement progress / rarity | ① + ② |
| `steam recommend [--based-on library\|wishlist]` | genre-overlap recommendations | ① + ② |

Layers read: **①** = official Web API (needs a Web API key), **②** = needs a login
session, **③** = web-front-end simulation. Store queries (`search`, `app`, `price`,
`profile`, `review summary`, `review list`) need no credentials at all.

> **③ gray area warning:** `activate`, `wishlist add/remove`, `review post`, and `friends invite-link` have no official API. They simulate the web frontend against undocumented endpoints, so they are unstable (break on page changes) and carry ToS/risk-control exposure — a burst of such requests can trip Steam's account-level automation controls (a different mechanism from VAC anti-cheat). Treat them as best-effort, always rate-limited, and never run unattended.
