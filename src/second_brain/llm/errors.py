from __future__ import annotations


class RouterError(Exception):
    """Base class for all LLM router errors."""


class PrivacyViolationError(RouterError):
    """Raised when a private request would be sent to a cloud model."""
