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

ACTIVATE_URL = "https://store.steampowered.com/account/registerkey"

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


def _activate_key(session: requests.Session, key: str, sessionid: str) -> str:
    try:
        resp = session.post(
            ACTIVATE_URL, data={"product_key": key, "sessionid": sessionid}, timeout=20
        )
    except requests.RequestException as exc:
        raise NetworkError(detail=str(exc))
    if resp.status_code != 200:
        return f"http:{resp.status_code}"
    text = resp.text.lower()
    for result, phrases in _RESULT_PHRASES:
        if any(p in text for p in phrases):
            return result
    return "unknown"


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
        sessionid = session.cookies.get("sessionid") or ""
        result = _activate_key(session, key, sessionid)
        auth.log_audit("activate", _mask_key(key), result)
        if result == "ok":
            console.print(f"[green]Activated {_mask_key(key)}[/green]")
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
    sessionid = session.cookies.get("sessionid") or ""
    rows: list[tuple[str, str]] = []
    for k in valid:
        result = _activate_key(session, k, sessionid)
        rows.append((k, result))
        auth.log_audit("activate", _mask_key(k), result)
        time.sleep(2)

    table = Table(title="Activation results")
    table.add_column("Key")
    table.add_column("Result")
    for k, result in rows:
        table.add_row(_mask_key(k), _describe_result(result))
    console.print(table)
