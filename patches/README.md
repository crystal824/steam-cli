# patches/

Diffs against the **installed** third-party library (`steam` 1.4.4, the newest
release on PyPI). They are not part of the published package — they exist because
the library lags behind Steam's current endpoints, and a rebuilt virtualenv needs
them reapplied.

| Patch | Applies to | Why |
|---|---|---|
| `steam-1.4.4-webauth-transfer-info.patch` | `steam/webauth.py` (`_finalize_login`) | Steam no longer returns `transfer_parameters`, so the original one-liner raised `KeyError` **after** a successful password + 2FA login. The patch accepts the modern `transfer_info` shape, never raises, and recovers the SteamID from the `steamLoginSecure` cookie. |
| `steam-1.4.4-webapi-required-params.patch` | `steam/webapi.py` | ValvePython enforces Steam's `GetSupportedAPIList` metadata, which now marks parameters as required that the live endpoints accept as omitted (`GetOwnedGames`: `appids_filter`, `include_free_sub`). The patch skips absent parameters and lets Steam validate. |

The diffs are written against a plain `steam/` prefix, so apply them from the
directory that holds the package (e.g. `…/site-packages`):

```bash
cd "$(python -c 'import steam, os; print(os.path.dirname(os.path.dirname(steam.__file__)))')"
patch -p0 --dry-run < path/to/patches/steam-1.4.4-webauth-transfer-info.patch
patch -p0          < path/to/patches/steam-1.4.4-webauth-transfer-info.patch
```

Or simply reproduce the two edits by hand — each is a single function.

Context: [`../docs/steam-endpoint-changes-2026.md`](../docs/steam-endpoint-changes-2026.md).
