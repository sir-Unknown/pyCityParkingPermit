"""Tests for the pyCityParkingPermit client."""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any

import pytest
from aiohttp import ClientSession
from aioresponses import aioresponses
from yarl import URL

from pyCityParkingPermit import Auth, CityParkingPermitAPI, Reservation
from pyCityParkingPermit.exceptions import ParseError, RateLimitError

BASE_URL = "https://example.test"

LOGIN_TYPES_RESPONSE = {"PermitMediaTypes": [{"ID": 1}]}
LOGIN_RESPONSE = {"Token": "token-123", "LoginStatus": 0}

RESERVATION_ITEM = {
    "ReservationID": 1844553,
    "ValidFrom": "2025-12-23T00:47:00",
    "ValidUntil": "2025-12-23T23:59:00",
    "LicensePlate": {
        "DisplayValue": "AA11BB",
        "Value": "AA11BB",
    },
    "Units": 359,
    "PermitMediaCode": "32600",
}

LICENSE_PLATE_ITEM = {
    "Value": "AA11BBCC",
    "Name": "Test",
    "ValidFrom": "0001-01-01T00:00:00",
    "ValidUntil": "9999-12-31T23:59:59.9999999",
}


@pytest.mark.asyncio
async def test_auth_requires_base_url() -> None:
    """Require base_url to be provided."""
    async with ClientSession() as session:
        with pytest.raises(ValueError, match="base_url must be a non-empty string"):
            Auth(session, "user", "pass", base_url="")


def build_permit_payload(
    *,
    active_reservations: list[dict[str, Any]] | None = None,
    license_plates: list[dict[str, Any]] | None = None,
    block_times: list[dict[str, Any]] | None = None,
    code: str = "32600",
    balance: int = 6996,
    type_id: int = 1,
    zone_code: str = "zone 4",
) -> dict[str, Any]:
    return {
        "Permit": {
            "ZoneCode": zone_code,
            "PermitMedias": [
                {
                    "TypeID": type_id,
                    "Code": code,
                    "Balance": balance,
                    "ActiveReservations": active_reservations or [],
                    "LicensePlates": license_plates or [],
                    "History": {"Reservations": {"Items": []}},
                    "RemainingUpgrades": 0,
                    "RemainingDowngrades": None,
                }
            ],
            "BlockTimes": block_times or [],
        }
    }


@pytest.mark.asyncio
async def test_get_account() -> None:
    """Test fetching the account details."""
    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}/login", payload=LOGIN_TYPES_RESPONSE)
        mocked.post(f"{BASE_URL}/login", payload=LOGIN_RESPONSE)
        mocked.post(
            f"{BASE_URL}/login/getbase",
            payload=build_permit_payload(active_reservations=[RESERVATION_ITEM]),
        )

        async with ClientSession() as session:
            auth = Auth(session, "user", "pass", base_url=BASE_URL)
            api = CityParkingPermitAPI(auth)
            account = await api.async_get_account()

    assert account.id == 32600
    assert account.remaining_time == 6996
    assert account.active_reservation_count == 1


@pytest.mark.asyncio
async def test_list_reservations_reauth_retry() -> None:
    """Test retrying after authentication failure."""
    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}/login", payload=LOGIN_TYPES_RESPONSE)
        mocked.post(f"{BASE_URL}/login", payload=LOGIN_RESPONSE)
        mocked.post(f"{BASE_URL}/login/getbase", status=401)
        mocked.post(f"{BASE_URL}/login", payload=LOGIN_RESPONSE)
        mocked.post(
            f"{BASE_URL}/login/getbase",
            payload=build_permit_payload(active_reservations=[RESERVATION_ITEM]),
        )

        async with ClientSession() as session:
            auth = Auth(session, "user", "pass", base_url=BASE_URL)
            api = CityParkingPermitAPI(auth)
            reservations = await api.async_list_reservations()

    assert len(reservations) == 1
    reservation = reservations[0]
    assert isinstance(reservation, Reservation)
    assert reservation.id == 1844553
    assert reservation.name == "AA11BB"
    assert reservation.start_time == "2025-12-23T00:47:00+00:00"
    assert reservation.end_time == "2025-12-23T23:59:00+00:00"
    login_calls = mocked.requests[("POST", URL(f"{BASE_URL}/login"))]
    assert len(login_calls) == 2


@pytest.mark.asyncio
async def test_list_favorites() -> None:
    """Test listing favorites."""
    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}/login", payload=LOGIN_TYPES_RESPONSE)
        mocked.post(f"{BASE_URL}/login", payload=LOGIN_RESPONSE)
        mocked.post(
            f"{BASE_URL}/login/getbase",
            payload=build_permit_payload(license_plates=[LICENSE_PLATE_ITEM]),
        )

        async with ClientSession() as session:
            auth = Auth(session, "user", "pass", base_url=BASE_URL)
            api = CityParkingPermitAPI(auth)
            favorites = await api.async_list_favorites()

    assert len(favorites) == 1
    assert favorites[0].license_plate == "AA11BBCC"
    assert favorites[0].name == "Test"


@pytest.mark.asyncio
async def test_update_favorite_remove_then_upsert() -> None:
    """Test updating a favorite removes then recreates."""
    permit_payload = build_permit_payload(license_plates=[LICENSE_PLATE_ITEM])

    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}/login", payload=LOGIN_TYPES_RESPONSE)
        mocked.post(f"{BASE_URL}/login", payload=LOGIN_RESPONSE)
        mocked.post(f"{BASE_URL}/login/getbase", payload=permit_payload)
        mocked.post(f"{BASE_URL}/permitmedialicenseplate/remove", payload={})
        mocked.post(f"{BASE_URL}/permitmedialicenseplate/upsert", payload={})

        async with ClientSession() as session:
            auth = Auth(session, "user", "pass", base_url=BASE_URL)
            api = CityParkingPermitAPI(auth)
            favorite = await api.async_update_favorite(
                name="New Name",
                license_plate="AA11BBCC",
            )

    assert favorite.license_plate == "AA11BBCC"
    assert favorite.name == "New Name"
    remove_request = mocked.requests[
        ("POST", URL(f"{BASE_URL}/permitmedialicenseplate/remove"))
    ][0]
    assert remove_request.kwargs["json"]["permitMediaTypeID"] == 1
    assert remove_request.kwargs["json"]["permitMediaCode"] == "32600"
    assert remove_request.kwargs["json"]["licensePlate"] == "AA11BBCC"
    assert remove_request.kwargs["json"]["name"] == "Test"
    upsert_request = mocked.requests[
        ("POST", URL(f"{BASE_URL}/permitmedialicenseplate/upsert"))
    ][0]
    assert upsert_request.kwargs["json"]["permitMediaTypeID"] == 1
    assert upsert_request.kwargs["json"]["permitMediaCode"] == "32600"
    assert upsert_request.kwargs["json"]["licensePlate"]["Value"] == "AA11BBCC"
    assert upsert_request.kwargs["json"]["licensePlate"]["Name"] == "New Name"


@pytest.mark.asyncio
async def test_get_zone_paid_block_today() -> None:
    """Test zone returns paid block for the current day."""
    today = datetime.now(tz=UTC).date()
    start = datetime.combine(today, time(18, 0), tzinfo=UTC)
    end = datetime.combine(today, time(23, 0), tzinfo=UTC)
    block_times = [
        {
            "ValidFrom": start.isoformat(),
            "ValidUntil": end.isoformat(),
            "IsFree": False,
        }
    ]

    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}/login", payload=LOGIN_TYPES_RESPONSE)
        mocked.post(f"{BASE_URL}/login", payload=LOGIN_RESPONSE)
        mocked.post(
            f"{BASE_URL}/login/getbase",
            payload=build_permit_payload(block_times=block_times),
        )

        async with ClientSession() as session:
            auth = Auth(session, "user", "pass", base_url=BASE_URL)
            api = CityParkingPermitAPI(auth)
            zone = await api.async_get_zone()

    assert zone is not None
    assert zone.id == "zone 4"
    assert zone.start_time == start.isoformat()
    assert zone.end_time == end.isoformat()


@pytest.mark.asyncio
async def test_login_rate_limited() -> None:
    """Test rate limit error during login."""
    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}/login", payload=LOGIN_TYPES_RESPONSE)
        mocked.post(
            f"{BASE_URL}/login",
            status=429,
            headers={"Retry-After": "60"},
        )

        async with ClientSession() as session:
            auth = Auth(session, "user", "pass", base_url=BASE_URL)
            api = CityParkingPermitAPI(auth)
            with pytest.raises(RateLimitError) as err:
                await api.async_get_account()

    assert err.value.retry_after == 60


@pytest.mark.asyncio
async def test_request_rate_limited() -> None:
    """Test rate limit error on an API request."""
    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}/login", payload=LOGIN_TYPES_RESPONSE)
        mocked.post(f"{BASE_URL}/login", payload=LOGIN_RESPONSE)
        mocked.post(
            f"{BASE_URL}/login/getbase",
            status=429,
            headers={"Retry-After": "120"},
        )

        async with ClientSession() as session:
            auth = Auth(session, "user", "pass", base_url=BASE_URL)
            api = CityParkingPermitAPI(auth)
            with pytest.raises(RateLimitError) as err:
                await api.async_list_reservations()

    assert err.value.retry_after == 120


@pytest.mark.asyncio
async def test_rate_limit_retry_after_invalid() -> None:
    """Test rate limit error when Retry-After is invalid."""
    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}/login", payload=LOGIN_TYPES_RESPONSE)
        mocked.post(f"{BASE_URL}/login", payload=LOGIN_RESPONSE)
        mocked.post(
            f"{BASE_URL}/login/getbase",
            status=429,
            headers={"Retry-After": "soon"},
        )

        async with ClientSession() as session:
            auth = Auth(session, "user", "pass", base_url=BASE_URL)
            api = CityParkingPermitAPI(auth)
            with pytest.raises(RateLimitError) as err:
                await api.async_list_reservations()

    assert err.value.retry_after is None


@pytest.mark.asyncio
async def test_invalid_json_body_raises_parse_error() -> None:
    """Test invalid JSON raises ParseError."""
    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}/login", payload=LOGIN_TYPES_RESPONSE)
        mocked.post(f"{BASE_URL}/login", payload=LOGIN_RESPONSE)
        mocked.post(f"{BASE_URL}/login/getbase", body="not-json")

        async with ClientSession() as session:
            auth = Auth(session, "user", "pass", base_url=BASE_URL)
            api = CityParkingPermitAPI(auth)
            with pytest.raises(ParseError):
                await api.async_get_account()


@pytest.mark.asyncio
async def test_create_reservation_payload() -> None:
    """Test create reservation payload and response parsing."""
    permit_response = build_permit_payload(active_reservations=[RESERVATION_ITEM])

    with aioresponses() as mocked:
        mocked.get(f"{BASE_URL}/login", payload=LOGIN_TYPES_RESPONSE)
        mocked.post(f"{BASE_URL}/login", payload=LOGIN_RESPONSE)
        mocked.post(f"{BASE_URL}/reservation/create", payload=permit_response)

        async with ClientSession() as session:
            auth = Auth(session, "user", "pass", base_url=BASE_URL)
            api = CityParkingPermitAPI(auth)
            reservation = await api.async_create_reservation(
                license_plate_value="AA11BB",
                license_plate_name="Visitor",
                permit_media_type_id=1,
                permit_media_code="32600",
                date_from=datetime(2025, 12, 23, 0, 47, tzinfo=UTC),
                date_until=datetime(2025, 12, 23, 23, 59, tzinfo=UTC),
            )

    assert reservation.id == 1844553
    request = mocked.requests[("POST", URL(f"{BASE_URL}/reservation/create"))][0]
    assert request.kwargs["json"]["permitMediaCode"] == "32600"
