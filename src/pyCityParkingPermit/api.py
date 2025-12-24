"""API entrypoints for the CityParkingPermit parking service."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from ._utils import async_json
from .auth import Auth
from .exceptions import ParseError
from .models import Account, Favorite, Reservation, Zone


def _dt_to_api(value: datetime) -> str:
    """Serialize to API format using ISO 8601 with seconds precision."""
    return value.replace(microsecond=0).isoformat()


class CityParkingPermitAPI:
    """Root API wrapper for CityParkingPermit parking service."""

    def __init__(self, auth: Auth) -> None:
        """Initialize the API client with an authenticated session."""
        self._auth = auth
        self._default_type_id: int | None = None
        self._default_code: str | None = None

    @property
    def auth(self) -> Auth:
        """Return the auth handler used for API calls."""
        return self._auth

    async def async_get_account(self) -> Account:
        """Fetch the account summary."""
        permit, permit_media = await self._fetch_permit()
        return Account.from_mapping(permit_media)

    async def async_get_zone(self) -> Zone | None:
        """Return the paid parking block for the current day, if any."""
        permit, permit_media = await self._fetch_permit()
        return Zone.from_mapping(permit)

    async def async_list_reservations(self) -> list[Reservation]:
        """Return all reservations for the current account."""
        permit, permit_media = await self._fetch_permit()
        items = _ensure_list(
            permit_media.get("ActiveReservations") or [], "reservations"
        )
        return [
            Reservation.from_mapping(_ensure_mapping(item, "reservation"))
            for item in items
        ]

    async def async_create_reservation(
        self,
        *,
        license_plate_value: str,
        license_plate_name: str | None = None,
        date_from: datetime | None = None,
        date_until: datetime | None = None,
        permit_media_type_id: int | None = None,
        permit_media_code: str | None = None,
    ) -> Reservation:
        """Create a new reservation."""
        type_id, code = await self._ensure_media_defaults(
            permit_media_type_id, permit_media_code
        )
        actual_date_from = date_from or datetime.now()
        payload = {
            **self._build_media_payload(type_id, code),
            "DateFrom": _dt_to_api(actual_date_from),
            "LicensePlate": {
                "Value": license_plate_value,
                "Name": license_plate_name,
            },
        }
        if date_until is not None:
            payload["DateUntil"] = _dt_to_api(date_until)

        response = await self._auth.request("POST", "/reservation/create", json=payload)
        try:
            response.raise_for_status()
            data = await async_json(response, on_error=ParseError)
        finally:
            response.release()

        return _pick_reservation_from_permit(
            data,
            license_plate_value=license_plate_value,
            date_from=actual_date_from,
            date_until=date_until,
        )

    async def async_end_reservation(
        self,
        *,
        reservation_id: int,
        permit_media_type_id: int | None = None,
        permit_media_code: str | None = None,
    ) -> None:
        """End an active reservation by its identifier."""
        type_id, code = await self._ensure_media_defaults(
            permit_media_type_id, permit_media_code
        )
        payload = {
            "ReservationID": reservation_id,
            **self._build_media_payload(type_id, code),
        }
        response = await self._auth.request("POST", "/reservation/end", json=payload)
        try:
            response.raise_for_status()
            data = await async_json(response, on_error=ParseError)
        finally:
            response.release()
        self._update_defaults_from_response(data)

    async def async_delete_reservation(self, reservation_id: int) -> None:
        """Delete a reservation by ending it."""
        await self.async_end_reservation(reservation_id=reservation_id)

    async def async_list_favorites(self) -> list[Favorite]:
        """Return all favorites for the current account."""
        permit, permit_media = await self._fetch_permit()
        items = _ensure_list(permit_media.get("LicensePlates") or [], "favorites")
        return [
            Favorite.from_mapping(_ensure_mapping(item, "favorite")) for item in items
        ]

    async def async_create_favorite(
        self, *, name: str | None, license_plate: str
    ) -> Favorite:
        """Create a favorite license plate."""
        await self._upsert_favorite(name=name, license_plate=license_plate)
        return Favorite(license_plate=license_plate, name=name)

    async def async_update_favorite(
        self, *, name: str | None, license_plate: str
    ) -> Favorite:
        """Update an existing favorite by removing it and recreating it."""
        favorites = await self.async_list_favorites()
        existing_name: str | None = None
        found = False
        for favorite in favorites:
            if favorite.license_plate == license_plate:
                existing_name = favorite.name
                found = True
                break

        if found:
            await self.async_delete_favorite(
                name=existing_name, license_plate=license_plate
            )

        await self._upsert_favorite(name=name, license_plate=license_plate)
        return Favorite(license_plate=license_plate, name=name)

    async def async_delete_favorite(
        self, *, name: str | None, license_plate: str
    ) -> None:
        """Delete a favorite by its license plate."""
        type_id, code = await self._ensure_media_defaults(None, None)
        payload = {
            **self._build_media_payload(type_id, code),
            "licensePlate": license_plate,
            "name": name,
        }
        response = await self._auth.request(
            "POST", "/permitmedialicenseplate/remove", json=payload
        )
        try:
            response.raise_for_status()
            data = await async_json(response, on_error=ParseError)
        finally:
            response.release()
        self._maybe_update_defaults_from_response(data)

    async def _upsert_favorite(self, *, name: str | None, license_plate: str) -> None:
        type_id, code = await self._ensure_media_defaults(None, None)
        payload = {
            **self._build_media_payload(type_id, code),
            "licensePlate": {
                "Value": license_plate,
                "Name": name,
            },
            "updateLicensePlate": None,
        }
        response = await self._auth.request(
            "POST", "/permitmedialicenseplate/upsert", json=payload
        )
        try:
            response.raise_for_status()
            data = await async_json(response, on_error=ParseError)
        finally:
            response.release()
        self._maybe_update_defaults_from_response(data)

    async def _ensure_media_defaults(
        self,
        permit_media_type_id: int | None,
        permit_media_code: str | None,
    ) -> tuple[int, str]:
        if permit_media_type_id is None or permit_media_code is None:
            if self._default_type_id is None or self._default_code is None:
                _permit, permit_media = await self._fetch_permit()
                self._update_defaults(permit_media)
            if permit_media_type_id is None:
                permit_media_type_id = self._default_type_id
            if permit_media_code is None:
                permit_media_code = self._default_code

        if permit_media_type_id is None or permit_media_code is None:
            raise ParseError("Missing permit media defaults")
        return permit_media_type_id, permit_media_code

    async def _fetch_permit(self) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
        response = await self._auth.request("POST", "/login/getbase")
        try:
            response.raise_for_status()
            data = await async_json(response, on_error=ParseError)
        finally:
            response.release()

        permit, permit_media = _extract_permit_media(data)
        self._update_defaults(permit_media)
        return permit, permit_media

    def _update_defaults(self, permit_media: Mapping[str, Any]) -> None:
        try:
            self._default_type_id = int(permit_media["TypeID"])
        except (KeyError, TypeError, ValueError) as err:
            raise ParseError("Invalid permit media TypeID") from err
        try:
            code = permit_media["Code"]
            if not isinstance(code, str):
                raise TypeError("permit media Code must be a string")
            self._default_code = code
        except (KeyError, TypeError, ValueError) as err:
            raise ParseError("Invalid permit media Code") from err

    def _update_defaults_from_response(self, data: Any) -> None:
        _permit, permit_media = _extract_permit_media(data)
        self._update_defaults(permit_media)

    def _maybe_update_defaults_from_response(self, data: Any) -> None:
        if data is None:
            return
        if not isinstance(data, Mapping):
            return
        if "Permit" not in data and "Permits" not in data:
            return
        self._update_defaults_from_response(data)

    def _build_media_payload(self, type_id: int, code: str) -> dict[str, Any]:
        return {"permitMediaTypeID": type_id, "permitMediaCode": code}


def _ensure_mapping(data: Any, label: str) -> Mapping[str, Any]:
    """Validate that the response payload is a mapping."""
    if not isinstance(data, Mapping):
        raise ParseError(f"Expected {label} object")
    return data


def _ensure_list(data: Any, label: str) -> list[Any]:
    """Validate that the response payload is a list."""
    if not isinstance(data, list):
        raise ParseError(f"Expected {label} list")
    return data


def _extract_permit_media(data: Any) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    root = _ensure_mapping(data, "response")
    if "Permit" in root:
        permit = _ensure_mapping(root["Permit"], "permit")
    elif "Permits" in root:
        permits = _ensure_list(root["Permits"], "permits")
        if not permits:
            raise ParseError("Expected permit list to have items")
        permit = _ensure_mapping(permits[0], "permit")
    else:
        raise ParseError("Expected permit data in response")

    permit_medias = _ensure_list(permit.get("PermitMedias"), "permit.PermitMedias")
    if not permit_medias:
        raise ParseError("Expected permit media list to have items")
    permit_media = _ensure_mapping(permit_medias[0], "permit_media")
    return permit, permit_media


def _pick_reservation_from_permit(
    data: Any,
    *,
    license_plate_value: str,
    date_from: datetime | None,
    date_until: datetime | None,
) -> Reservation:
    _permit, permit_media = _extract_permit_media(data)
    items = _ensure_list(permit_media.get("ActiveReservations") or [], "reservations")
    reservations = [
        Reservation.from_mapping(_ensure_mapping(item, "reservation")) for item in items
    ]
    if not reservations:
        raise ParseError("No active reservations in response")

    def _matches(reservation: Reservation) -> bool:
        if reservation.license_plate != license_plate_value:
            return False
        if (
            date_from is not None
            and reservation.start_time != _normalize_date(date_from).isoformat()
        ):
            return False
        if (
            date_until is not None
            and reservation.end_time != _normalize_date(date_until).isoformat()
        ):
            return False
        return True

    for reservation in reservations:
        if _matches(reservation):
            return reservation
    return reservations[0]


def _normalize_date(value: datetime) -> datetime:
    dt = value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).replace(microsecond=0)
