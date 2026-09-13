"""Steam CLI, a safe and controllable tool for the Hermes agent."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("steam-cli")
except PackageNotFoundError:
    # Source checkouts can be imported before the package is installed.
    __version__ = "0+unknown"

from ._compat import relax_webapi_param_validation

# Applied on import so a clean `pip install` needs no patching of site-packages: see
# _compat for what ValvePython's stale API metadata would otherwise do to every call.
WEBAPI_METADATA_RELAXED = relax_webapi_param_validation()
