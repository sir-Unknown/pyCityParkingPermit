"""Typed data models for the CityParkingPermit parking API."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .exceptions import ParseError


def _parse_int(value: Any, field: str) -> int:
    """Parse an integer field from API data."""
    try:
        return int(value)
    except (TypeError, ValueError) as err:
        raise ParseError(f"Invalid int for {field}: {value!r}") from err


def _parse_str(value: Any, field: str) -> str:
    """Parse a string field from API data."""
    if isinstance(value, str):
        return value
    raise ParseError(f"Invalid str for {field}: {value!r}")


def _parse_dt_value(value: Any, field: str) -> datetime:
    """Parse API datetime into a timezone-aware value."""
    if not isinstance(value, str):
        raise ParseError(f"Invalid datetime for {field}: {value!r}")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as err:
        raise ParseError(f"Invalid datetime for {field}: {value!r}") from err

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    return dt


def _normalize_dt(dt: datetime) -> datetime:
    """Normalize datetimes to UTC with seconds precision."""
    return dt.astimezone(UTC).replace(microsecond=0)


def _dt_to_client(dt: datetime) -> str:
    """Serialize datetimes for library consumers using ISO 8601 strings."""
    return _normalize_dt(dt).isoformat()


def _parse_dt(value: Any, field: str) -> datetime:
    """Parse API datetime into normalized UTC."""
    return _normalize_dt(_parse_dt_value(value, field))


def _parse_optional_str(value: Any, field: str) -> str | None:
    """Parse an optional string field from API data."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise ParseError(f"Invalid str for {field}: {value!r}")


@dataclass(slots=True, frozen=True)
class Zone:
    """Parking zone data with a paid block for the current day."""

    id: str
    start_time: str
    end_time: str

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> Zone | None:
        """Build a zone from a permit mapping."""
        zone_code = _parse_str(data.get("ZoneCode"), "permit.ZoneCode")
        block_times = data.get("BlockTimes")
        if not isinstance(block_times, list):
            raise ParseError("Expected permit.BlockTimes list")

        paid_blocks: list[tuple[datetime, datetime]] = []
        for item in block_times:
            if not isinstance(item, Mapping):
                raise ParseError("Expected permit.BlockTimes item object")
            if item.get("IsFree") is True:
                continue
            start_raw = _parse_dt_value(item.get("ValidFrom"), "block.ValidFrom")
            end_raw = _parse_dt_value(item.get("ValidUntil"), "block.ValidUntil")
            today = datetime.now(tz=start_raw.tzinfo or UTC).date()
            if start_raw.date() != today:
                continue
            paid_blocks.append((start_raw, end_raw))

        if not paid_blocks:
            return None

        start_raw, end_raw = min(paid_blocks, key=lambda item: item[0])
        return cls(
            id=zone_code,
            start_time=_dt_to_client(start_raw),
            end_time=_dt_to_client(end_raw),
        )


@dataclass(slots=True, frozen=True)
class Account:
    """Account data including remaining time and active reservations."""

    id: int
    remaining_time: int
    active_reservation_count: int

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> Account:
        """Build an account from a permit media mapping."""
        reservations = data.get("ActiveReservations")
        if reservations is None:
            active_reservation_count = 0
        elif isinstance(reservations, list):
            active_reservation_count = len(reservations)
        else:
            raise ParseError("Expected permit_media.ActiveReservations list")

        return cls(
            id=_parse_int(data.get("Code"), "permit_media.Code"),
            remaining_time=_parse_int(data.get("Balance"), "permit_media.Balance"),
            active_reservation_count=active_reservation_count,
        )


@dataclass(slots=True, frozen=True)
class Reservation:
    """Reservation data for a license plate."""

    id: int
    license_plate: str
    name: str
    start_time: str
    end_time: str

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> Reservation:
        """Build a reservation from a permit media reservation mapping."""
        license_plate = data.get("LicensePlate")
        if not isinstance(license_plate, Mapping):
            raise ParseError("Expected reservation.LicensePlate object")

        return cls(
            id=_parse_int(data.get("ReservationID"), "reservation.ReservationID"),
            license_plate=_parse_str(
                license_plate.get("Value"), "reservation.LicensePlate.Value"
            ),
            name=_parse_str(
                license_plate.get("DisplayValue"),
                "reservation.LicensePlate.DisplayValue",
            ),
            start_time=_dt_to_client(
                _parse_dt(data.get("ValidFrom"), "reservation.ValidFrom")
            ),
            end_time=_dt_to_client(
                _parse_dt(data.get("ValidUntil"), "reservation.ValidUntil")
            ),
        )


@dataclass(slots=True, frozen=True)
class Favorite:
    """Favorite license plate data."""

    license_plate: str
    name: str | None

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> Favorite:
        """Build a favorite from a permit media mapping."""
        return cls(
            license_plate=_parse_str(data.get("Value"), "favorite.Value"),
            name=_parse_optional_str(data.get("Name"), "favorite.Name"),
        )
