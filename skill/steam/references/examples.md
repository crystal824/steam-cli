# Examples: natural language → CLI

| User says | CLI |
|---|---|
| "Activate this CDK: XXXXX-XXXXX-XXXXX" | `steam activate XXXXX-XXXXX-XXXXX` (confirm intent first; `--dry-run` to preview) |
| "Search Black Myth: Wukong" | `steam search "黑神话：悟空"` |
| "Add Elden Ring to my wishlist" | `steam wishlist add 1245620` |
| "Which of my library games have over 100 hours?" | `steam library list --sort playtime` then filter rows `>= 100h` |
| "Post a positive review for Baldur's Gate 3" | `steam review post 1086940 --recommend --text "..."` |
| "Who is playing It Takes Two?" | `steam friends playing 1426210` |
| "Which wishlist items are on sale?" | `steam wishlist on-sale` |
| "Recommend some games for me" | `steam recommend` (genre-overlap with your library) |
| "Generate a friend invite link" | `steam friends invite-link` |
| "Give me a new invite link, invalidate the old one" | `steam friends invite-link --refresh` (confirm intent first) |
| "Steam is unreachable / slow" | Ask the user for proxy details, then `steam config proxy set --host H --port P` → `steam config proxy test` → retry; `steam config proxy unset` when done |

Notes:

- App IDs above: Elden Ring `1245620`, Baldur's Gate 3 `1086940`, It Takes Two `1426210`, Black Myth: Wukong `2358720`. App names work in place of IDs where a command accepts `<appid|name>`.
- Every write op in this table (activate, wishlist add, review post, invite-link --refresh) requires the second confirmation described in `safety.md`.
