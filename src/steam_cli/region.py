"""Store region (country) and language, resolved from the account.

Everything used to send ``l=english&cc=us``, so a Chinese account was quoted USD
prices and got English store text. Steam is not a reliable oracle to fall back on
either: with no ``cc`` at all, ``appdetails`` answers CNY for one appid and USD for
another, and adding ``filters=price_overview`` flips it back to USD (measured
2026-09-13). The account page is authoritative instead -- it carries
``data-userinfo="{...&quot;country_code&quot;:&quot;CN&quot;...}"`` -- and that is the
same page :func:`steam_cli.auth.is_session_valid` already fetches.

Resolution order
  1. explicit: ``STEAM_CLI_CC`` / ``STEAM_CLI_LANG``, or ``steam config region set``;
  2. the account, when a login session exists (cached for a day in
     ``<config>/region.json``);
  3. ``us`` / ``english``.
"""

from __future__ import annotations

import html
import json
import os
import re
import time

from . import auth
from .errors import NotAuthenticatedError

CACHE_FILE = auth.CONFIG_DIR / "region.json"
CACHE_TTL = 24 * 3600
DEFAULT_CC = "us"
DEFAULT_LANG = "english"
ACCOUNT_URL = "https://store.steampowered.com/account/"

# Store country -> the language its shoppers get by default. Anything unlisted
# falls back to english; STEAM_CLI_LANG / `config region set --lang` overrides.
_CC_LANG = {
    "ar": "arabic",
    "bg": "bulgarian",
    "br": "brazilian",
    "cn": "schinese",
    "cz": "czech",
    "de": "german",
    "dk": "danish",
    "es": "spanish",
    "fi": "finnish",
    "fr": "french",
    "gr": "greek",
    "hk": "tchinese",
    "hu": "hungarian",
    "id": "indonesian",
    "it": "italian",
    "jp": "japanese",
    "kr": "koreana",
    "nl": "dutch",
    "no": "norwegian",
    "pl": "polish",
    "pt": "portuguese",
    "ro": "romanian",
    "ru": "russian",
    "se": "swedish",
    "th": "thai",
    "tr": "turkish",
    "tw": "tchinese",
    "ua": "ukrainian",
    "vn": "vietnamese",
}

_USERINFO_RE = re.compile(r'data-userinfo="([^"]*)"')


def parse_country(page: str) -> str | None:
    """Pull the country code out of an account page (``None`` when absent)."""
    match = _USERINFO_RE.search(page or "")
    if match:
        try:
            userinfo = json.loads(html.unescape(match.group(1)))
        except ValueError:
            userinfo = None
        if isinstance(userinfo, dict):
            code = str(userinfo.get("country_code") or "").strip().upper()
            if len(code) == 2 and code.isalpha():
                return code.lower()
    # Older layouts keep the same field outside the userinfo blob.
    match = re.search(r'country_code"?\s*:\s*"?([A-Za-z]{2})', html.unescape(page or ""))
    return match.group(1).lower() if match else None


def fetch_account_country() -> str | None:
    """The account's store country, straight from the account page."""
    try:
        session = auth.get_session()
    except NotAuthenticatedError:
        return None
    try:
        resp = session.get(
            ACCOUNT_URL,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (steam-cli)"},
        )
    except Exception:  # network trouble: fall back rather than fail every command
        return None
    if resp.status_code != 200:
        return None
    return parse_country(resp.text)


def _read_cache() -> dict:
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_cache(updates: dict) -> dict:
    cache = _read_cache()
    cache.update(updates)
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except OSError:
        pass
    return cache


def _explicit_cc() -> str | None:
    return (os.environ.get("STEAM_CLI_CC") or "").strip().lower() or _clean(
        _read_cache().get("explicit_cc")
    )


def _explicit_lang() -> str | None:
    return (os.environ.get("STEAM_CLI_LANG") or "").strip().lower() or _clean(
        _read_cache().get("explicit_lang")
    )


def _clean(value: object) -> str | None:
    text = str(value or "").strip().lower()
    return text or None


def detected_country(*, force: bool = False) -> tuple[str | None, str]:
    """``(country, source)`` for the account, cached for a day."""
    cache = _read_cache()
    fresh = time.time() - float(cache.get("detected_at") or 0) < CACHE_TTL
    if not force and fresh and cache.get("cc"):
        return str(cache["cc"]), str(cache.get("source") or "cache")
    if not auth.is_logged_in():
        return None, "anonymous"
    country = fetch_account_country()
    if country:
        _write_cache({"cc": country, "detected_at": time.time(), "source": "account"})
        return country, "account"
    if cache.get("cc"):
        return str(cache["cc"]), "stale-cache"
    return None, "unknown"


def country() -> str:
    """Store country code (lowercase, two letters) to use for store requests."""
    return _explicit_cc() or detected_country()[0] or DEFAULT_CC


def language() -> str:
    """Store language code to use for store requests."""
    explicit = _explicit_lang()
    if explicit:
        return explicit
    from_cache = _clean(_read_cache().get("lang"))
    if from_cache:
        return from_cache
    return _CC_LANG.get(country(), DEFAULT_LANG)


def store_params(extra: dict | None = None) -> dict[str, str]:
    """``{"cc": ..., "l": ...}`` merged with ``extra``; ``None`` values dropped.

    Passing an explicit ``{"l": "schinese"}`` in ``extra`` keeps that value, which
    is how call sites ask for a specific language (e.g. the CJK name lookup).
    """
    params: dict[str, object] = {"cc": country(), "l": language()}
    # A call site passing {"cc": None} means "use the resolved value", not "send
    # no cc at all" -- dropping None *after* the merge silently unset the region
    # once already (steam price quoted CDN$ off the proxy's IP because of it).
    params.update({key: value for key, value in (extra or {}).items() if value is not None})
    return {key: str(value) for key, value in params.items() if value is not None}


def region_info() -> dict:
    """Everything the UI needs to explain where the region came from."""
    explicit_cc, explicit_lang = _explicit_cc(), _explicit_lang()
    detected, source = detected_country()
    return {
        "country": country(),
        "language": language(),
        "source": "override" if (explicit_cc or explicit_lang) else source,
        "detected": detected,
        "explicit_country": explicit_cc,
        "explicit_language": explicit_lang,
    }


def set_region(country_code: str | None = None, language_code: str | None = None) -> dict:
    """Pin the region and/or language (used by ``steam config region set``)."""
    updates: dict[str, object] = {}
    if country_code:
        updates["explicit_cc"] = country_code.strip().lower()
    if language_code:
        updates["explicit_lang"] = language_code.strip().lower()
    return _write_cache(updates)


def clear_region() -> None:
    """Drop cached detection and any explicit override."""
    try:
        CACHE_FILE.unlink()
    except OSError:
        pass
