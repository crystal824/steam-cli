"""Work around third-party behaviour that breaks the shipped commands.

`steam-cli` depends on ValvePython (`steam>=1.4.4`), whose `WebAPI` validates every
call against the metadata from Steam's `GetSupportedAPIList`. That metadata no longer
describes what the live endpoints accept: it marks parameters as required that Steam
is happy to receive omitted — `IPlayerService.GetOwnedGames` demands `appids_filter`,
then `include_free_sub` — so the call died **client-side** before it ever reached
Steam::

    network_error: a network error occurred while contacting Steam
    Method requires 'appids_filter' to be set

Anyone installing the package on a clean machine hit that on the first
`steam stats summary` / `steam library list`. The old remedy was to hand-patch
`site-packages/steam/webapi.py` (see `patches/`), which is not something a user should
have to do to a dependency.

Instead the parameters are flagged `optional` right after the metadata is loaded, so
absent parameters are simply not sent and Steam does the real validation. That is
exactly what the local patch did, applied from inside the package this time.
"""

from __future__ import annotations

_APPLIED = False


def relax_webapi_param_validation() -> bool:
    """Mark every WebAPI parameter optional. Idempotent; True when it is in effect.

    Returns False instead of raising when the library is a shape we do not recognise —
    a newer ValvePython may not need this at all, and the CLI must still run.
    """
    global _APPLIED
    try:
        from steam.webapi import WebAPI
    except Exception:
        return False
    if getattr(WebAPI, "_steam_cli_relaxed", False) or _APPLIED:
        return True

    original = WebAPI.load_interfaces

    def load_interfaces(self, interfaces_dict, *args, **kwargs):
        result = original(self, interfaces_dict, *args, **kwargs)
        for interface in getattr(self, "interfaces", None) or []:
            for method in getattr(interface, "methods", None) or []:
                parameters = getattr(method, "parameters", None)
                if isinstance(parameters, dict):
                    for parameter in parameters.values():
                        if isinstance(parameter, dict):
                            parameter["optional"] = True
        return result

    WebAPI.load_interfaces = load_interfaces
    WebAPI._steam_cli_relaxed = True  # type: ignore[attr-defined]
    _APPLIED = True
    return True
