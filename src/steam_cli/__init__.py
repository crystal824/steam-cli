"""Steam CLI, a safe and controllable tool for the Hermes agent."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("steam-cli")
except PackageNotFoundError:
    # Source checkouts can be imported before the package is installed.
    __version__ = "0+unknown"
