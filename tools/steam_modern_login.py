#!/usr/bin/env python3
"""Full Steam web login for steam-cli — thin wrapper around the CLI's own flow.

The implementation lives in `steam_cli.modern_login` (the same code `steam login`
runs); this script exists for the deployment/recovery use cases the Skill references —
it prints one JSON object per step, which is easier to consume from automation.

Passwords are read with getpass or the `STEAM_CLI_PASSWORD` environment variable (for
unattended runs); they never appear in argv.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from steam_cli import modern_login


def emit(**event: object) -> None:
    print(json.dumps(event, ensure_ascii=False), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", required=True, help="Steam account name")
    ap.add_argument("--save", action="store_true", help="persist the session for the CLI")
    ap.add_argument(
        "--refresh-token",
        default="",
        help="reuse a stored refresh token instead of a password (no 2FA needed)",
    )
    args = ap.parse_args()

    try:
        if args.refresh_token:
            emit(step="auth", mode="refresh_token")
            result = modern_login.remint_session(
                args.username, refresh_token=args.refresh_token, save=args.save, on_event=emit
            )
        else:
            result = modern_login.login(
                args.username,
                password=os.environ.get("STEAM_CLI_PASSWORD") or None,
                save=args.save,
                on_event=emit,
            )
    except Exception as exc:  # surface the structured error and exit non-zero
        emit(step="error", error=type(exc).__name__, message=str(exc)[:200])
        return 1
    emit(
        step="result",
        ok=result["store_authed"],
        steam_id=result["steam_id"],
        saved=result["saved"],
    )
    return 0 if result["store_authed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
