"""Optional third-party data source helpers.

SteamDB does not expose an official API, so we avoid scraping it directly.
This module is a thin, clearly-labelled placeholder for future integrations
and is not used by the read-only price path (see price.py).
"""

from __future__ import annotations


def steamdb_url(appid: int) -> str:
    return f"https://steamdb.info/app/{appid}/"
