# pyCityParkingPermit

[![CI](https://github.com/sir-Unknown/pyCityParkingPermit/actions/workflows/ci.yml/badge.svg)](https://github.com/sir-Unknown/pyCityParkingPermit/actions/workflows/ci.yml)
[![PyPI](https://badge.fury.io/py/pyCityParkingPermit.svg)](https://badge.fury.io/py/pyCityParkingPermit)
[![Python versions](https://img.shields.io/pypi/pyversions/pyCityParkingPermit.svg)](https://pypi.org/project/pyCityParkingPermit/)
[![Issues](https://img.shields.io/github/issues/sir-Unknown/pyCityParkingPermit.svg)](https://github.com/sir-Unknown/pyCityParkingPermit/issues)
[![Security policy](https://img.shields.io/badge/security-policy-blue.svg)](https://github.com/sir-Unknown/pyCityParkingPermit/security/policy)

Async client for the CityParkingPermit parking service, built for Home Assistant
custom integrations and any asyncio project.

## Highlights

- Async-only HTTP calls via `aiohttp`; you own the `ClientSession`.
- Auth helper handles login and retries on 401/403 with cached defaults.
- Typed dataclass models expose ISO 8601 timestamp strings.
- Reservation and favorite helpers map CityParkingPermit Permit endpoints.
- Requires the CityParkingPermit `base_url` to target your environment.

## Requirements

- Python 3.13.2+ (matches Home Assistant 2025.12)
- `aiohttp>=3.10.0`

## Installation

```bash
python -m pip install pyCityParkingPermit
```

## Quick start

```python
import asyncio
from aiohttp import ClientSession

from pyCityParkingPermit import Auth, CityParkingPermitAPI

BASE_URL = "https://cityparkingpermit.example"


async def main() -> None:
    async with ClientSession() as session:
        auth = Auth(session, username="user", password="pass", base_url=BASE_URL)
        api = CityParkingPermitAPI(auth)
        account = await api.async_get_account()
        reservations = await api.async_list_reservations()
        favorites = await api.async_list_favorites()
        print(account, reservations, favorites)


asyncio.run(main())
```

`Auth` requires the CityParkingPermit `base_url`; set it to your tenant's endpoint.

## API overview

- `async_get_account() -> Account`: Fetch account details with remaining time and active reservation count.
- `async_get_zone() -> Zone | None`: Fetch the paid block for the current day.
- `async_list_reservations() -> list[Reservation]`: List active reservations.
- `async_create_reservation(...) -> Reservation`: Create a reservation.
- `async_end_reservation(...) -> None`: End a reservation.
- `async_delete_reservation(reservation_id) -> None`: Alias for ending a reservation.
- `async_list_favorites() -> list[Favorite]`: List favorites.
- `async_create_favorite(...) -> Favorite`: Create a favorite.
- `async_update_favorite(...) -> Favorite`: Update a favorite by remove + upsert.
- `async_delete_favorite(...) -> None`: Delete a favorite.

Creating and ending a reservation:

```python
from datetime import UTC, datetime, timedelta

from aiohttp import ClientSession

from pyCityParkingPermit import Auth, CityParkingPermitAPI

async with ClientSession() as session:
    api = CityParkingPermitAPI(
        Auth(session, "user", "pass", base_url="https://cityparkingpermit.example")
    )
    starts_at = datetime.now(tz=UTC)
    ends_at = starts_at + timedelta(hours=2)

    reservation = await api.async_create_reservation(
        license_plate_value="12-AB-34",
        license_plate_name="My Car",
        date_from=starts_at,
        date_until=ends_at,
    )
    await api.async_end_reservation(reservation_id=reservation.id)
```

Managing favorites:

```python
await api.async_update_favorite(name="My Car", license_plate="12-AB-34")
await api.async_delete_favorite(name="My Car", license_plate="12-AB-34")
```

Reading the package version:

```python
from pyCityParkingPermit import __version__
print("pyCityParkingPermit", __version__)
```

## API notes

- Datetimes are sent as ISO 8601 strings with seconds precision.
- Incoming timestamps are normalized to ISO 8601 UTC strings; `Zone` and `Reservation` timestamp fields are always strings, not `datetime` objects.
- Session ownership: you always pass your own `aiohttp.ClientSession`; the library never creates or closes sessions.

## Error handling

```python
from aiohttp import ClientSession

from pyCityParkingPermit import Auth, CityParkingPermitAPI, RateLimitError

async with ClientSession() as session:
    api = CityParkingPermitAPI(
        Auth(session, "user", "pass", base_url="https://cityparkingpermit.example")
    )
    try:
        await api.async_list_reservations()
    except RateLimitError as err:
        print("Retry after:", err.retry_after)
```

- `AuthError` for authentication failures or expired sessions.
- `ParkingConnectionError` for network errors and timeouts.
- `RateLimitError` for HTTP 429 responses (`retry_after` hints).
- `ParseError` for unexpected response payloads.
- `aiohttp.ClientResponseError` is raised for other HTTP errors via `raise_for_status()`.

## Development

```bash
python -m pip install -e '.[test,dev]'
python -m pip install pre-commit
pre-commit install
pre-commit run --all-files
pytest tests/
ruff check .
ruff format .
mypy
```

## Support and security

- Issues: https://github.com/sir-Unknown/pyCityParkingPermit/issues
- Security: https://github.com/sir-Unknown/pyCityParkingPermit/security/policy

MIT License. See `LICENSE` and `NOTICE`.
