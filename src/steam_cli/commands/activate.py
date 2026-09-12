"""Product key activation (single and batch)."""

from __future__ import annotations

import re
import time

import requests
import typer
from rich.console import Console
from rich.table import Table

from .. import auth
from ..errors import (
    AlreadyActivatedError,
    EndpointUnavailableError,
    InvalidFormatError,
    InvalidKeyError,
    NetworkError,
    RegionLockedError,
)

console = Console()

REGISTER_PAGE = "https://store.steampowered.com/account/registerkey"
# 2026-09-12 实测：/account/registerkey 只是**表单页**（POST 它也只会回表单 HTML），
# 真正做激活的是 ajaxregisterkey（返回 JSON；store 前端 registerkey.js 用的就是它）。
ACTIVATE_URL = "https://store.steampowered.com/account/ajaxregisterkey/"

# purchase_result_details 错误码（摘自 store 前端 registerkey.js）
_PURCHASE_RESULTS = {
    14: "invalid",
    15: "already_activated",
    53: "rate_limited",
    13: "region_locked",
    9: "already_owned",
    24: "base_game_required",
    4: "retry_later",
}

_CDK_RE_3 = re.compile(r"^[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}$")
_CDK_RE_5 = re.compile(r"^[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}-[A-Z0-9]{5}$")

_RESULT_PHRASES = (
    ("already_activated", ("already been activated", "already own", "already registered")),
    ("region_locked", ("not available in your country", "not available in your region")),
    (
        "invalid",
        (
            "not valid or is incomplete",
            "is invalid",
            "invalid key",
            "product key is invalid",
            "cannot be redeemed",
            "invalid or incomplete",
        ),
    ),
    ("rate_limited", ("too many", "try again later", "please wait")),
)


def validate_cdk_format(key: str) -> bool:
    k = key.strip().upper()
    return bool(_CDK_RE_3.match(k) or _CDK_RE_5.match(k))


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "****"
    return key[:4] + "-****-" + key[-4:]


def _receipt_name(data: dict) -> str | None:
    receipt = data.get("purchase_receipt_info") or {}
    items = receipt.get("line_items") or []
    if items:
        return items[0].get("line_item_description")
    return None


def _activate_key(session: requests.Session, key: str, sessionid: str) -> tuple[str, str | None]:
    """返回 (result, 商品名)；result == "ok" 即激活成功。"""
    try:
        resp = session.post(
            ACTIVATE_URL,
            data={"product_key": key, "sessionid": sessionid},
            headers={
                "Referer": REGISTER_PAGE,
                "Origin": "https://store.steampowered.com",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=25,
        )
    except requests.RequestException as exc:
        raise NetworkError(detail=str(exc))
    if resp.status_code != 200:
        return f"http:{resp.status_code}", None
    try:
        data = resp.json()
    except ValueError:
        # 非 JSON：通常是被风控/会话失效时返回的表单页 —— 退回短语兜底
        text = resp.text.lower()
        for result, phrases in _RESULT_PHRASES:
            if any(p in text for p in phrases):
                return result, None
        return "unknown", None
    name = _receipt_name(data)
    if data.get("success") == 1:
        return "ok", name
    return _PURCHASE_RESULTS.get(data.get("purchase_result_details"), "unknown"), name


def _describe_result(result: str) -> str:
    if result == "ok":
        return "[green]activated[/green]"
    if result == "already_activated":
        return "[yellow]already activated[/yellow]"
    if result == "region_locked":
        return "[yellow]region locked[/yellow]"
    if result == "invalid":
        return "[red]invalid[/red]"
    if result == "rate_limited":
        return "[yellow]rate limited[/yellow]"
    if result == "already_owned":
        return "[yellow]already owned[/yellow]"
    if result == "base_game_required":
        return "[red]base game required[/red]"
    if result == "retry_later":
        return "[yellow]retry later (30 min)[/yellow]"
    if result == "unknown":
        return "[red]unrecognized response[/red]"
    return f"[red]{result}[/red]"


def _raise_for_result(result: str, key: str) -> None:
    if result == "ok":
        return
    if result == "already_activated":
        raise AlreadyActivatedError()
    if result == "region_locked":
        raise RegionLockedError()
    if result == "invalid":
        raise InvalidKeyError()
    if result == "rate_limited":
        raise NetworkError("rate limited; wait a while and retry")
    if result.startswith("http:"):
        raise NetworkError(detail=f"HTTP {result.split(':', 1)[1]}")
    if result == "already_owned":
        raise AlreadyActivatedError("this account already owns this product")
    if result == "base_game_required":
        raise InvalidKeyError("the base game must be activated before this key")
    if result == "retry_later":
        raise NetworkError("Steam asked to retry later; wait 30 minutes")
    raise EndpointUnavailableError(
        detail="the activation response could not be parsed; the endpoint may have changed"
    )


def _read_batch_file(path: str) -> list[str]:
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError as exc:
        raise InvalidFormatError(f"could not read batch file: {path}", detail=str(exc))
    return lines


def register(app: typer.Typer) -> None:
    @app.command()
    def activate(
        cdk: str = typer.Argument(None, help="Product key to activate"),
        batch: str = typer.Option(None, "--batch", help="File with one key per line"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview only"),
        yes: bool = typer.Option(False, "--yes", help="Skip confirmation"),
    ):
        """Activate a Steam product key, singly or from a batch file."""
        if cdk and batch:
            raise InvalidFormatError("provide either a single key or --batch, not both")
        if not cdk and not batch:
            typer.echo("Usage: steam activate <KEY>  or  steam activate --batch FILE")
            raise typer.Exit()

        if batch:
            _activate_batch(batch, dry_run, yes)
            return

        key = cdk.strip().upper()
        if not validate_cdk_format(key):
            raise InvalidFormatError(
                f"{_mask_key(cdk)} does not look like a Steam key",
                detail="Steam keys are 15 or 25 alphanumeric characters grouped by "
                "dashes. Double-check the source before retrying.",
            )
        if dry_run:
            console.print(f"[yellow]dry-run[/yellow] would activate {_mask_key(key)}")
            return
        if not yes and not typer.confirm(f"Activate {_mask_key(key)}?"):
            raise typer.Abort()
        session = auth.require_session()
        sessionid = auth.cookie_value(session, "sessionid")
        result, name = _activate_key(session, key, sessionid)
        auth.log_audit("activate", _mask_key(key), f"{result}:{name}" if name else result)
        if result == "ok":
            label = f" — [bold]{name}[/bold]" if name else ""
            console.print(f"[green]Activated {_mask_key(key)}[/green]{label}")
        else:
            _raise_for_result(result, key)


def _activate_batch(path: str, dry_run: bool, yes: bool) -> None:
    valid: list[str] = []
    invalid: list[str] = []
    for raw in _read_batch_file(path):
        key = raw.strip()
        if not key or key.startswith("#"):
            continue
        if validate_cdk_format(key):
            valid.append(key.upper())
        else:
            invalid.append(key)

    if not valid and not invalid:
        raise InvalidFormatError("no keys found in batch file")

    if valid:
        console.print(f"Batch contains {len(valid)} valid key(s):")
        table = Table()
        table.add_column("#")
        table.add_column("Key")
        for i, k in enumerate(valid, 1):
            table.add_row(str(i), _mask_key(k))
        console.print(table)

    if invalid:
        masked = [_mask_key(k) for k in invalid]
        console.print(
            f"[yellow]{len(invalid)} key(s) with an invalid format will be skipped:"
            f" {', '.join(masked)}[/yellow]"
        )

    if dry_run:
        console.print(f"[yellow]dry-run[/yellow] would activate {len(valid)} key(s)")
        return

    if not valid:
        return

    if not yes and not typer.confirm(f"Activate {len(valid)} keys?"):
        raise typer.Abort()

    session = auth.require_session()
    sessionid = auth.cookie_value(session, "sessionid")
    rows: list[tuple[str, str, str | None]] = []
    for k in valid:
        result, name = _activate_key(session, k, sessionid)
        rows.append((k, result, name))
        auth.log_audit("activate", _mask_key(k), f"{result}:{name}" if name else result)
        time.sleep(2)

    table = Table(title="Activation results")
    table.add_column("Key")
    table.add_column("Result")
    for k, result, name in rows:
        table.add_row(_mask_key(k), _describe_result(result) + (f" — {name}" if name else ""))
    console.print(table)
