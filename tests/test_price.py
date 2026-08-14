import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from steam_cli.utils import price  # noqa: E402


def test_itad_unavailable_without_key(monkeypatch):
    monkeypatch.delenv("STEAM_CLI_ITAD_KEY", raising=False)
    assert price.itad_available() is False
    assert price.price_history(2358720) is None


def test_itad_available_with_key(monkeypatch):
    monkeypatch.setenv("STEAM_CLI_ITAD_KEY", "dummy")
    assert price.itad_available() is True
    assert price._itad_lookup(2358720) is None
