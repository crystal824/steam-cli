#!/usr/bin/env python3
"""Steam license / activation verifier (2026-09-12).

Why this tool exists
--------------------
`IPlayerService/GetOwnedGames` returns no acquisition timestamp, so it cannot
prove *when* something entered the library -- and playtime/last-played can even
predate the activation (the user may have played a Playtest build). The
authoritative source is the account licenses page:
`store.steampowered.com/account/licenses/`, where every row carries the
acquisition DATE and METHOD:

    Retail            -> a product key / CDK was activated
    Steam Store       -> purchased
    Gift/Guest Pass   -> gift or guest pass

Use it whenever you need to confirm an activation actually landed (including
keys activated from another session/channel), instead of trusting a CLI message
or a "the other side said it worked" report.

Usage:
    .venv/bin/python tools/check_licenses.py [--grep TEXT] [--all] [--limit N]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from steam_cli import auth

LICENSES_URL = "https://store.steampowered.com/account/licenses/"
# The page is parsed as HTML and its acquisition column is localised ("Retail" /
# 零售, "Steam Store" / Steam 商店), so ask for the English rendering explicitly
# instead of inheriting the session's Steam_Language.
LICENSES_PARAMS = {"l": "english"}
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _session() -> requests.Session:
    state = auth.load_session()
    if state is None:
        raise SystemExit("not logged in: run tools/steam_remint_session.py --save first")
    s = requests.Session()
    s.headers["User-Agent"] = UA
    for name, entries in state.cookies.items():
        for entry in entries:
            domains = [entry["domain"]] if entry.get("domain") else ["store.steampowered.com"]
            for domain in domains:
                s.cookies.set(name, entry["value"], domain=domain, path=entry.get("path") or "/")
    return s


def _text(cell: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell)).strip()


def rows() -> list[list[str]]:
    html = re.sub(
        r"\s+", " ", _session().get(LICENSES_URL, params=LICENSES_PARAMS, timeout=30).text
    )
    out: list[list[str]] = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.DOTALL):
        cells = [_text(td) for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.DOTALL)]
        cells = [c for c in cells if c]
        if cells:
            out.append(cells)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--grep", default="", help="only rows containing this text (case-insensitive)")
    ap.add_argument("--all", action="store_true", help="print every row")
    ap.add_argument("--limit", type=int, default=25)
    args = ap.parse_args()

    data = rows()
    if args.grep:
        needle = args.grep.lower()
        data = [r for r in data if any(needle in c.lower() for c in r)]
    print(f"licenses: {len(data)} row(s) matched")
    shown = data if args.all else data[: args.limit]
    for row in shown:
        print("  " + " | ".join(row)[:160])
    if not args.all and len(data) > len(shown):
        print(f"  … {len(data) - len(shown)} more (use --all)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
