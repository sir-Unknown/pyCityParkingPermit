"""Authentication helpers for the CityParkingPermit parking service API."""

from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Mapping
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from typing import Any, TypedDict, Unpack

from aiohttp import (
    ClientError,
    ClientResponse,
    ClientSession,
    ClientTimeout,
)

from ._utils import async_json
from .exceptions import AuthError, ParkingConnectionError, RateLimitError

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 20.0


class _AuthInitKwargs(TypedDict, total=False):
    timeout: float
    permit_media_type_id: int | None


class Auth:
    """Handle authenticated requests and session state."""

    def __init__(
        self,
        session: ClientSession,
        username: str,
        password: str,
        base_url: str,
        **kwargs: Unpack[_AuthInitKwargs],
    ) -> None:
        timeout = kwargs.get("timeout", DEFAULT_TIMEOUT)
        permit_media_type_id = kwargs.get("permit_media_type_id")
        unexpected_kwargs = set(kwargs) - {
            "timeout",
            "permit_media_type_id",
        }
        if unexpected_kwargs:
            unexpected = ", ".join(sorted(unexpected_kwargs))
            raise TypeError(f"Unexpected keyword arguments: {unexpected}")

        if not username or not username.strip():
            raise ValueError("username must be a non-empty string")
        if not password or not password.strip():
            raise ValueError("password must be a non-empty string")
        if not base_url or not base_url.strip():
            raise ValueError("base_url must be a non-empty string")
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")

        self._session = session
        self._identifier = username
        self._password = password
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._permit_media_type_id = permit_media_type_id
        self._token: str | None = None
        self._authenticated = False
        self._login_lock = asyncio.Lock()

    async def request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> ClientResponse:
        """Perform an authenticated request and return the response."""
        auth_required = kwargs.pop("auth_required", True)
        if auth_required:
            await self._ensure_logged_in()

        url = f"{self._base_url}{path}"
        extra_headers = kwargs.pop("headers", None)
        headers = self._merge_headers(extra_headers, auth_required)
        timeout = ClientTimeout(total=self._timeout)

        attempt = 0
        while True:
            attempt += 1
            try:
                response = await self._session.request(
                    method,
                    url,
                    headers=headers,
                    timeout=timeout,
                    **kwargs,
                )
            except (TimeoutError, ClientError) as err:
                raise ParkingConnectionError("Request failed") from err

            if response.status == 429:
                response.release()
                raise RateLimitError(_parse_retry_after(response.headers))
            if auth_required and response.status in {401, 403}:
                response.release()
                self._invalidate_session()
                if attempt == 1:
                    _LOGGER.debug("Session expired, re-authenticating")
                    await self._ensure_logged_in()
                    headers = self._merge_headers(extra_headers, auth_required)
                    continue
                raise AuthError("Authentication failed")

            return response

    def invalidate(self) -> None:
        """Invalidate the current session so the next request reauthenticates."""
        self._invalidate_session()

    async def _ensure_logged_in(self) -> None:
        if self._authenticated:
            return
        async with self._login_lock:
            if self._authenticated:
                return
            await self._login()

    async def _login(self) -> None:
        if self._permit_media_type_id is None:
            await self._fetch_default_type_id()

        url = f"{self._base_url}/login"
        headers = self._build_default_headers()
        timeout = ClientTimeout(total=self._timeout)
        payload = {
            "identifier": self._identifier,
            "loginMethod": "Pas",
            "password": self._password,
            "permitMediaTypeID": self._permit_media_type_id,
        }

        try:
            response = await self._session.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
        except (TimeoutError, ClientError) as err:
            raise ParkingConnectionError("Login request failed") from err

        try:
            if response.status == 429:
                raise RateLimitError(_parse_retry_after(response.headers))
            if response.status in {401, 403}:
                raise AuthError("Authentication failed")
            if response.status >= 400:
                raise AuthError("Authentication failed")
            data = await async_json(response, on_error=AuthError)
        finally:
            response.release()

        if not isinstance(data, Mapping):
            raise AuthError("Authentication failed")
        if data.get("LoginStatus") == 2:
            message = data.get("ErrorMessage", "Unknown authentication error")
            raise AuthError(f"Authentication failed: {message}")

        token = data.get("Token")
        if not token:
            raise AuthError("Authentication failed")

        self._token = str(token)
        self._authenticated = True

    async def _fetch_default_type_id(self) -> None:
        url = f"{self._base_url}/login"
        headers = self._build_default_headers()
        timeout = ClientTimeout(total=self._timeout)

        try:
            response = await self._session.get(url, headers=headers, timeout=timeout)
        except (TimeoutError, ClientError) as err:
            raise ParkingConnectionError("Login request failed") from err

        try:
            if response.status == 429:
                raise RateLimitError(_parse_retry_after(response.headers))
            if response.status >= 400:
                raise AuthError("Authentication failed")
            data = await async_json(response, on_error=AuthError)
        finally:
            response.release()

        data_map = _ensure_mapping(data, "login")
        raw_types = _ensure_list(data_map.get("PermitMediaTypes"), "PermitMediaTypes")
        if not raw_types:
            raise AuthError("No permit media types available")

        types: list[Mapping[str, Any]] = []
        for raw_type in raw_types:
            if not isinstance(raw_type, Mapping):
                raise AuthError("Invalid permit media type entry")
            types.append(raw_type)

        type_id = types[0].get("ID")
        if type_id is None:
            raise AuthError("Invalid permit media type ID")
        if not isinstance(type_id, (int, str)):
            raise AuthError("Invalid permit media type ID")
        try:
            self._permit_media_type_id = int(type_id)
        except (TypeError, ValueError) as err:
            raise AuthError("Invalid permit media type ID") from err

    def _invalidate_session(self) -> None:
        self._authenticated = False
        self._token = None

    def _build_authorization_header(self) -> dict[str, str]:
        if self._token is None:
            raise AuthError("Authentication token missing")
        encoded = base64.b64encode(self._token.encode("utf-8")).decode("utf-8")
        return {"Authorization": f"Token {encoded}"}

    def _build_default_headers(self) -> dict[str, str]:
        return {
            "accept": "application/json",
            "user-agent": _get_user_agent(),
        }

    def _merge_headers(
        self, headers: Mapping[str, str] | None, auth_required: bool
    ) -> dict[str, str]:
        merged = self._build_default_headers()
        if auth_required:
            merged.update(self._build_authorization_header())
        if headers:
            merged.update(headers)
        return merged


def _parse_retry_after(headers: Mapping[str, str]) -> int | None:
    value = headers.get("Retry-After")
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _ensure_mapping(data: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise AuthError(f"Expected {label} object")
    return data


def _ensure_list(data: Any, label: str) -> list[Any]:
    if not isinstance(data, list):
        raise AuthError(f"Expected {label} list")
    return data


@lru_cache(maxsize=1)
def _get_user_agent() -> str:
    try:
        package_version = version("pyCityParkingPermit")
    except PackageNotFoundError:
        package_version = "0.0.0"
    return f"pyCityParkingPermit/{package_version}"
