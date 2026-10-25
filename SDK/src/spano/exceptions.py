"""Custom exceptions for the Spano SDK."""


class SpanoError(Exception):
    """Base exception for Spano SDK errors."""


class SpanoConfigurationError(SpanoError):
    """Invalid SDK configuration."""


class SpanoTransportError(SpanoError):
    """Telemetry transport failed."""
