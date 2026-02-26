"""Shared exception classes with no internal dependencies.

Kept in a standalone module to avoid circular imports between
``config`` and ``providers.base``.
"""


class ConfigurationError(Exception):
    """Invalid or missing configuration."""
