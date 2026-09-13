#!/usr/bin/env python3
"""Re-mint a steam-cli session from the stored refresh token.

Thin wrapper around `steam_cli.modern_login.remint_session` — the same code path as
`steam refresh --remint`. No password and no 2FA: the refresh token keeps working
until `rtExpiry` (returned by the settoken calls). Prints one JSON object per step.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from steam_cli import modern_login


def emit(**event: object) -> None:
    print(json.dumps(event, ensure_ascii=False), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", default="", help="account name (defaults to the stored one)")
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    try:
        result = modern_login.remint_session(args.username or None, save=args.save, on_event=emit)
    except Exception as exc:
        emit(step="error", error=type(exc).__name__, message=str(exc)[:200])
        return 1
    emit(
        step="result", ok=result["store_authed"], steam_id=result["steam_id"], saved=result["saved"]
    )
    return 0 if result["store_authed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
