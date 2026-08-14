# API map

Each command is tagged with its technical layer:

- **① Public API** — official Web API (dev key), documented and stable.
- **② Session API** — requires the login session; endpoints are used by the official frontend but not documented for third parties.
- **③ Web-session simulation** — no API exists; drives the official web form/page endpoints via the login session.

| Command | Capability | Layer |
|---|---|---|
| `steam auth set-key <key>` | store Web API key | ① |
| `steam auth login` / `status` / `logout` / `refresh` / `revoke-all` | session & key management | ① + ② |
| `steam doctor` | probe endpoint availability | ① + ③ (diagnostic) |
| `steam config proxy set/show/test/unset` | configure & verify a proxy for all requests | local config |
| `steam search <query>` | store search | ① |
| `steam app <appid\|name>` | app details (price, tags, reviews, requirements) | ① |
| `steam price <appid\|name>` | current price + historical low (IsThereAnyDeal) | ① |
| `steam news <appid>` | app news | ① |
| `steam radar [--wishlist] [--library-never-played]` | discount radar | ② |
| `steam library list` / `has` | owned games, playtime, sort | ② |
| `steam wishlist list` / `on-sale` | wishlist read + sale check | ② |
| `steam wishlist add` / `remove` | wishlist write | ③ |
| `steam activate <cdk>` (incl. `--batch`) | redeem CD key | ③ |
| `steam review post` | publish review | ③ |
| `steam review list [--mine]` | list reviews | ① / ② |
| `steam friends list` / `playing` / `recently-played` | friend reads | ② |
| `steam friends invite-link [--refresh]` | generate / refresh invite link | ③ |
| `steam profile <steamid\|vanity>` | public profile lookup | ① |
| `steam stats summary` / `game` | playtime statistics | ② |
| `steam launch <appid\|name>` | launch via `steam://run/<appid>` | local protocol |
| `steam achievements <appid>` | achievement progress / rarity | ① / ② |
| `steam recommend` | recommendations | planned / pending |

> **③ gray area warning:** `activate`, `wishlist add/remove`, `review post`, and `friends invite-link` have no official API. They simulate the web frontend against undocumented endpoints, so they are unstable (break on page changes) and carry ToS/risk-control exposure — a burst of such requests can trip Steam's account-level automation controls (a different mechanism from VAC anti-cheat). Treat them as best-effort, always rate-limited, and never run unattended.
