"""Structured error types so the Skill can react programmatically."""


class SteamError(Exception):
    """Base error for all steam-cli failures."""

    code = "error"
    hint = ""

    def __init__(self, message: str = "", *, detail: str = ""):
        self.message = message or self.hint
        self.detail = detail
        super().__init__(self.message)


class NotAuthenticatedError(SteamError):
    code = "not_authenticated"
    hint = "not logged in; run `steam auth login` first"


class ApiKeyMissingError(SteamError):
    code = "api_key_missing"
    hint = "no Web API key configured; run `steam auth set-key <key>`"


class InvalidFormatError(SteamError):
    code = "invalid_format"
    hint = "input format is invalid"


class AlreadyActivatedError(SteamError):
    code = "already_activated"
    hint = "this key has already been activated"


class RegionLockedError(SteamError):
    code = "region_locked"
    hint = "this key cannot be activated in your region"


class InvalidKeyError(SteamError):
    code = "invalid_key"
    hint = "this key is invalid or has been revoked"


class NetworkError(SteamError):
    code = "network_error"
    hint = "a network error occurred while contacting Steam"


class SessionExpiredError(SteamError):
    code = "session_expired"
    hint = "your login session has expired; run `steam auth login`"


class EndpointUnavailableError(SteamError):
    code = "endpoint_unavailable"
    hint = "a non-official endpoint appears to be unavailable"


class ForbiddenError(SteamError):
    code = "forbidden"
    hint = "this operation is forbidden by safety policy"
