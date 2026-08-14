from __future__ import annotations

import datetime

import requests
import typer
from rich.console import Console
from rich.table import Table

from .. import auth
from ..client import SteamClient
from ..errors import NetworkError

console = Console()


def _format_ts(ts: float | int | None) -> str:
    if not ts:
        return "-"
    try:
        return datetime.datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        return str(ts)


def register(app: typer.Typer) -> None:
    @app.command()
    def achievements(
        appid: str,
        missing: bool = False,
        rarity: bool = False,
    ) -> None:
        """List your achievements for an app (requires a Web API key and login)."""
        steam_id = auth.require_steam_id()
        client = SteamClient()
        try:
            player = client.api.ISteamUserStats.GetPlayerAchievements(
                appid=appid, steamid=steam_id
            )
            glob = client.api.ISteamUserStats.GetGlobalAchievementPercentagesForApp(
                gameid=appid
            )
        except (requests.RequestException, ValueError) as exc:
            raise NetworkError(detail=str(exc))

        playerstats = player.get("playerstats") or {}
        achievements = playerstats.get("achievements") or []
        global_pcts = {
            item.get("name"): item.get("percent")
            for item in (glob.get("achievementpercentages") or {}).get("achievements", [])
        }

        rows = []
        for ach in achievements:
            apiname = ach.get("apiname", "")
            achieved = ach.get("achieved") == 1
            if missing and achieved:
                continue
            rows.append(
                {
                    "name": ach.get("name") or apiname,
                    "achieved": achieved,
                    "unlocktime": ach.get("unlocktime") if achieved else None,
                    "percent": global_pcts.get(apiname),
                }
            )

        if rarity:
            rows.sort(key=lambda r: r["percent"] if r["percent"] is not None else 101.0)

        table = Table(title=f"achievements: {appid}")
        table.add_column("Name")
        table.add_column("Achieved")
        table.add_column("Unlocked")
        table.add_column("Global %")
        for row in rows:
            pct = f"{row['percent']:.2f}" if row["percent"] is not None else "-"
            table.add_row(
                row["name"],
                "yes" if row["achieved"] else "no",
                _format_ts(row["unlocktime"]),
                pct,
            )
        console.print(table)
