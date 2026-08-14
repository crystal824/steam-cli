#!/usr/bin/env python3
"""Check steam-cli credential state for the Hermes steam skill.

Prints a single JSON status line and exits:
  0 - logged in or a Web API key is set
  1 - no credentials available (login / set-key required)
  2 - steam_cli could not be imported
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _find_src_dir() -> Path | None:
    here = Path(__file__).resolve()
    for parent in (here.parent, *here.parents):
        src = parent / "src" / "steam_cli"
        if src.is_dir():
            return parent / "src"
    return None


def _error(message: str) -> int:
    print(json.dumps({"ok": False, "logged_in": False, "error": message}))
    return 2


def main() -> int:
    src = _find_src_dir()
    if src is not None:
        sys.path.insert(0, str(src))

    try:
        from steam_cli import auth
    except Exception as exc:
        return _error(f"{exc.__class__.__name__}: {exc}")

    try:
        state = auth.load_session()
        api_key = auth.get_api_key()
        logged_in = state is not None
        result = {
            "ok": logged_in or bool(api_key),
            "logged_in": logged_in,
            "username": state.username if state else None,
            "steam_id": state.steam_id if state else None,
            "api_key": bool(api_key),
        }
        print(json.dumps(result))
        return 0 if result["ok"] else 1
    except Exception as exc:
        return _error(f"{exc.__class__.__name__}: {exc}")


if __name__ == "__main__":
    sys.exit(main())
