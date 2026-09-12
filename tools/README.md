# tools/

Deployment and recovery helpers that sit *outside* the CLI's command surface.
They are plain scripts; run them with the project's virtualenv, e.g.

```bash
.venv/bin/python tools/steam_modern_login.py --username <account> --save
```

| Script | Purpose |
|---|---|
| `steam_modern_login.py` | Full login through `IAuthenticationService` (RSA → BeginAuthSession → app approval or Steam Guard code → poll → `finalizelogin` → settoken). Use this instead of `steam login`, which relies on ValvePython's retired `/login/dologin/` path. Prompts for the password and, if needed, the Steam Guard code; `--save` persists the session for the CLI. |
| `steam_remint_session.py` | Re-mints session cookies from the stored refresh token — **no password, no 2FA**. Run whenever `steam status` says the session is invalid. `--save` persists the result. |
| `check_licenses.py` | Lists Steam licenses with acquisition date + method (`Retail` = key/CDK, `Steam Store` = purchase, `Gift/Guest Pass` = gift). This is the authoritative way to verify that an activation actually landed. Supports `--grep`, `--all`, `--limit`. |

All three read/write credentials through `steam_cli.auth`, so they share the
CLI's storage (`~/.config/steam-cli/`, keyring when available, otherwise `0600`
files). No password is ever stored; what is stored is the session cookies and a
long-lived refresh token. To revoke access, delete `refresh_token.secret` or run
`steam revoke-all`.

See [`../docs/steam-endpoint-changes-2026.md`](../docs/steam-endpoint-changes-2026.md)
for why the login and activation paths had to be rebuilt.
