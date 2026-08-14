import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


from steam_cli.client import resolve_appid  # noqa: E402
from steam_cli.commands.activate import validate_cdk_format  # noqa: E402
from steam_cli.commands.review import filter_review_text  # noqa: E402
from steam_cli.errors import (  # noqa: E402
    AlreadyActivatedError,
    InvalidFormatError,
)


def test_cdk_3x5_valid():
    assert validate_cdk_format("ABCDE-12345-ZYXWV") is True


def test_cdk_5x5_valid():
    assert validate_cdk_format("ABCDE-FGHIJ-KLMNO-PQRST-UVWXY") is True


def test_cdk_invalid_short():
    assert validate_cdk_format("ABCDE-1234") is False


def test_cdk_invalid_chars():
    assert validate_cdk_format("ABC!E-12345-ZYXWV") is False


def test_cdk_invalid_empty():
    assert validate_cdk_format("") is False


def test_resolve_appid_by_id():
    assert resolve_appid("2358720") == 2358720


def test_review_filter_ok():
    assert filter_review_text("A very fun game with great combat.") is None


def test_review_filter_empty():
    assert filter_review_text("") is not None


def test_error_types():
    err = AlreadyActivatedError()
    assert err.code == "already_activated"
    assert InvalidFormatError().code == "invalid_format"
