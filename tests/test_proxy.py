import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from steam_cli import auth  # noqa: E402
from steam_cli.commands.config import (  # noqa: E402
    build_proxy_url,
    mask_proxy_url,
    validate_proxy_url,
)
from steam_cli.errors import InvalidFormatError  # noqa: E402


class FakeKeyring:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value

    def delete(self, key):
        self.store.pop(key, None)


def make_fixture(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(auth, "_keyring_get", fake.get)
    monkeypatch.setattr(auth, "_keyring_set", fake.set)
    monkeypatch.setattr(auth, "_keyring_delete", fake.delete)
    return fake


def test_validate_proxy_url_ok():
    assert validate_proxy_url("http://127.0.0.1:7890") == "http://127.0.0.1:7890"
    assert validate_proxy_url("https://user:pass@proxy.example.com:8080").startswith("https://")


def test_validate_proxy_url_rejects_bad_scheme():
    with pytest.raises(InvalidFormatError):
        validate_proxy_url("ftp://127.0.0.1:21")


def test_validate_proxy_url_rejects_no_host():
    with pytest.raises(InvalidFormatError):
        validate_proxy_url("http://:7890")


def test_build_proxy_url():
    assert build_proxy_url("127.0.0.1", 7890) == "http://127.0.0.1:7890"
    assert build_proxy_url("x.com", 8080, "alice", "s3cret") == "http://alice:s3cret@x.com:8080"


def test_mask_proxy_url():
    masked = mask_proxy_url("http://alice:s3cret@x.com:8080")
    assert "s3cret" not in masked
    assert masked == "http://alice:***@x.com:8080"
    assert mask_proxy_url("http://x.com:8080") == "http://x.com:8080"


def test_set_proxy_injects_env_and_unset_restores(monkeypatch):
    make_fixture(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", "http://original:1")
    monkeypatch.setenv("HTTP_PROXY", "http://original:1")
    monkeypatch.setenv("https_proxy", "http://original:1")
    monkeypatch.setenv("http_proxy", "http://original:1")
    auth._proxy_env_saved = {}

    auth.set_proxy("http://127.0.0.1:7890")
    assert auth.get_proxy() == "http://127.0.0.1:7890"
    assert auth.apply_proxy() is None
    for var in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        assert __import__("os").environ[var] == "http://127.0.0.1:7890"

    auth.clear_proxy()
    assert auth.get_proxy() is None
    for var in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        assert __import__("os").environ[var] == "http://original:1"


def test_set_proxy_without_prior_env(monkeypatch):
    make_fixture(monkeypatch)
    for var in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        monkeypatch.delenv(var, raising=False)
    auth._proxy_env_saved = {}

    auth.set_proxy("http://127.0.0.1:7890")
    for var in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        assert var in __import__("os").environ

    auth.clear_proxy()
    for var in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        assert var not in __import__("os").environ
