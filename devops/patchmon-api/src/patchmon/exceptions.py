"""Typed exception hierarchy for the PatchMon client."""


class PatchmonError(Exception):
    """Base error for all PatchMon client failures."""


class AuthError(PatchmonError):
    """Authentication or credential resolution failed."""


class PollTimeout(PatchmonError):
    """Polling exceeded the configured timeout."""
