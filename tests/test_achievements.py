import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from steam_cli.commands.achievements import _pct_value


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("12.34", 12.34), (1.5, 1.5), (None, 101.0), ("", 101.0), ("n/a", 101.0)],
)
def test_pct_value_parses_api_strings(raw, expected):
    """ISteamUserStats returns percent as a string; formatting it with :.2f used
    to raise ValueError. Unparseable values sort last (101.0) and print as '-'."""
    assert _pct_value(raw) == pytest.approx(expected)
