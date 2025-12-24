"""Public exports for the CityParkingPermit parking service."""

from importlib.metadata import PackageNotFoundError, version

from .api import CityParkingPermitAPI
from .auth import Auth
from .exceptions import (
    AuthError,
    ParkingConnectionError,
    ParseError,
    PyCityParkingPermitError,
    RateLimitError,
)
from .models import Account, Favorite, Reservation, Zone

__all__ = [
    "Auth",
    "CityParkingPermitAPI",
    "Account",
    "Favorite",
    "Reservation",
    "Zone",
    "AuthError",
    "ParkingConnectionError",
    "PyCityParkingPermitError",
    "ParseError",
    "RateLimitError",
    "__version__",
]

try:
    __version__ = version("pyCityParkingPermit")
except PackageNotFoundError:
    __version__ = "0.0.0"
