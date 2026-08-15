"""Authentication and session management.

Only the Web API key and login session (cookies) are considered high-sensitivity
and stored via keyring. Low-sensitivity caches (e.g. appid index) go to local
files under the config dir.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import keyring
import requests
from steam.webauth import WebAuth

from .errors import NotAuthenticatedError

SERVICE = "steam-cli"
KEY_API_KEY = "web_api_key"
KEY_SESSION = "web_session"
KEY_SESSION_ID = "session_id"
KEY_STEAM_ID = "steam_id"
KEY_USERNAME = "username"
KEY_PROXY = "proxy_url"

CONFIG_DIR = Path(os.environ.get("STEAM_CLI_HOME", Path.home() / ".config" / "steam-cli"))
AUDIT_LOG = CONFIG_DIR / "audit.log"

_STEAM_DOMAINS = (
    "steamcommunity.com",
    "store.steampowered.com",
    "help.steampowered.com",
)

_STATUS_TTL = 60.0
_audit_lock = threading.Lock()
_status_cache: dict | None = None
_status_cache_at = 0.0
_proxy_env_saved: dict[str, str | None] = {}
_PROXY_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "http_proxy",
    "https_proxy",
)


def _ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _keyring_get(key: str) -> str | None:
    try:
        value = keyring.get_password(SERVICE, key)
        if value is not None:
            return value
    except Exception:
        pass
    secret_file = CONFIG_DIR / f"{key}.secret"
    try:
        return secret_file.read_text(encoding="utf-8")
    except OSError:
        return None


def _write_secret_fallback(key: str, value: str) -> None:
    path = CONFIG_DIR / f"{key}.secret"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(value)


def _keyring_set(key: str, value: str) -> None:
    _ensure_config_dir()
    try:
        keyring.set_password(SERVICE, key, value)
    except Exception:
        _write_secret_fallback(key, value)


def _keyring_delete(key: str) -> None:
    try:
        keyring.delete_password(SERVICE, key)
    except Exception:
        pass
    secret_file = CONFIG_DIR / f"{key}.secret"
    if secret_file.exists():
        secret_file.unlink()


def get_api_key() -> str | None:
    return _keyring_get(KEY_API_KEY)


def set_api_key(api_key: str) -> None:
    _keyring_set(KEY_API_KEY, api_key.strip())
    _invalidate_status()


def clear_api_key() -> None:
    _keyring_delete(KEY_API_KEY)
    _invalidate_status()


def get_proxy() -> str | None:
    return _keyring_get(KEY_PROXY)


def set_proxy(url: str) -> None:
    _keyring_set(KEY_PROXY, url.strip())
    apply_proxy()


def clear_proxy() -> None:
    _keyring_delete(KEY_PROXY)
    apply_proxy()


def apply_proxy() -> None:
    global _proxy_env_saved
    url = get_proxy()
    if url:
        if not _proxy_env_saved:
            _proxy_env_saved = {v: os.environ.get(v) for v in _PROXY_VARS}
        for v in _PROXY_VARS:
            os.environ[v] = url
    else:
        for v, original in _proxy_env_saved.items():
            if original is None:
                os.environ.pop(v, None)
            else:
                os.environ[v] = original
        _proxy_env_saved = {}


@dataclass
class SessionState:
    username: str
    steam_id: str
    session_id: str
    cookies: dict[str, list[dict]]


def _dump_cookies(session: requests.Session) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for c in session.cookies:
        out.setdefault(c.name, []).append(
            {
                "value": c.value,
                "domain": c.domain or "",
                "path": c.path or "/",
            }
        )
    return out


def _normalize_cookies(cookies: object) -> dict[str, list[dict]]:
    if not isinstance(cookies, dict):
        return {}
    if cookies and all(isinstance(v, str) for v in cookies.values()):
        return {k: [{"value": v, "domain": "", "path": "/"}] for k, v in cookies.items()}
    normalized: dict[str, list[dict]] = {}
    for name, entries in cookies.items():
        if not isinstance(entries, list):
            continue
        normalized[name] = [
            {
                "value": e.get("value", ""),
                "domain": e.get("domain") or "",
                "path": e.get("path") or "/",
            }
            for e in entries
            if isinstance(e, dict)
        ]
    return normalized


def _bind_cookies(wa: WebAuth, cookies: dict[str, list[dict]]) -> None:
    for name, entries in cookies.items():
        for entry in entries:
            domain = entry.get("domain") or ""
            path = entry.get("path") or "/"
            if domain:
                wa.session.cookies.set(name, entry["value"], domain=domain, path=path)
            else:
                for d in _STEAM_DOMAINS:
                    wa.session.cookies.set(name, entry["value"], domain=d, path=path)


def save_session(wa: WebAuth, username: str) -> None:
    cookies = _dump_cookies(wa.session)
    _keyring_set(KEY_SESSION, json.dumps(cookies))
    if wa.session_id:
        _keyring_set(KEY_SESSION_ID, wa.session_id)
    if wa.steam_id is not None:
        _keyring_set(KEY_STEAM_ID, str(wa.steam_id))
    _keyring_set(KEY_USERNAME, username)
    _invalidate_status()


def load_session() -> SessionState | None:
    cookies_raw = _keyring_get(KEY_SESSION)
    username = _keyring_get(KEY_USERNAME)
    if not cookies_raw or not username:
        return None
    try:
        cookies = _normalize_cookies(json.loads(cookies_raw))
    except json.JSONDecodeError:
        return None
    return SessionState(
        username=username,
        steam_id=_keyring_get(KEY_STEAM_ID) or "",
        session_id=_keyring_get(KEY_SESSION_ID) or "",
        cookies=cookies,
    )


def clear_session() -> None:
    for key in (KEY_SESSION, KEY_SESSION_ID, KEY_STEAM_ID, KEY_USERNAME):
        _keyring_delete(key)
    _invalidate_status()


def restore_webauth(state: SessionState) -> WebAuth:
    wa = WebAuth(state.username)
    _bind_cookies(wa, state.cookies)
    wa.logged_on = True
    wa.session_id = state.session_id
    if state.steam_id:
        try:
            from steam.steamid import SteamID

            wa.steam_id = SteamID(int(state.steam_id))
        except Exception:
            wa.steam_id = None
    return wa


def get_session() -> requests.Session:
    state = load_session()
    if state is None:
        raise NotAuthenticatedError()
    wa = restore_webauth(state)
    return wa.session


def require_session() -> requests.Session:
    return get_session()


def get_steam_id() -> str | None:
    state = load_session()
    return state.steam_id if state else None


def require_steam_id() -> str:
    steam_id = get_steam_id()
    if not steam_id:
        raise NotAuthenticatedError()
    return steam_id


def is_logged_in() -> bool:
    return load_session() is not None


def is_session_valid() -> bool:
    state = load_session()
    if state is None:
        return False
    try:
        wa = restore_webauth(state)
        resp = wa.session.get(
            "https://store.steampowered.com/account/",
            timeout=10,
            allow_redirects=False,
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False


def log_audit(command: str, target: str, result: str) -> None:
    """Append an audit entry. `target` must already be redacted by the caller
    if it could contain a secret (e.g. a CD key) -- this function does not
    mask anything itself."""
    import datetime

    line = f"{datetime.datetime.now(datetime.UTC).isoformat()}\t{command}\t{target}\t{result}\n"
    with _audit_lock:
        _ensure_config_dir()
        # Open with an explicit 0o600 mode (like _write_secret_fallback) so the
        # log isn't left group/world-readable by the process umask -- it can
        # contain account-identifying activity even when callers redact secrets.
        fd = os.open(AUDIT_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as fh:
            fh.write(line)


def _invalidate_status() -> None:
    global _status_cache, _status_cache_at
    _status_cache = None
    _status_cache_at = 0.0


def status() -> dict:
    global _status_cache, _status_cache_at
    now = time.monotonic()
    if _status_cache is None or now - _status_cache_at > _STATUS_TTL:
        _status_cache = _compute_status()
        _status_cache_at = now
    return _status_cache


def _compute_status() -> dict:
    api_key = get_api_key()
    state = load_session()
    return {
        "logged_in": state is not None,
        "username": state.username if state else None,
        "steam_id": state.steam_id if state else None,
        "api_key": bool(api_key),
        "api_key_valid": _api_key_valid(api_key) if api_key else False,
        "session_valid": is_session_valid() if state else False,
    }


def _api_key_valid(api_key: str | None) -> bool:
    if not api_key:
        return False
    try:
        from steam.webapi import WebAPI

        WebAPI(key=api_key).ISteamWebAPIUtil.GetServerInfo()
        return True
    except Exception:
        return False
