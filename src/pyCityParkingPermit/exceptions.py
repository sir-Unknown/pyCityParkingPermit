"""Exceptions for the CityParkingPermit parking service."""

from __future__ import annotations


class PyCityParkingPermitError(Exception):
    """Base exception for pyCityParkingPermit."""


class AuthError(PyCityParkingPermitError):
    """Authentication failed or session expired."""


class ParkingConnectionError(PyCityParkingPermitError):
    """Network or timeout failure when calling the API."""


class RateLimitError(PyCityParkingPermitError):
    """Rate limit exceeded by the API."""

    def __init__(self, retry_after: int | None) -> None:
        super().__init__("Rate limit exceeded")
        self.retry_after = retry_after


class ParseError(PyCityParkingPermitError):
    """Failed to parse API response data."""
