"""Shared helpers for CityParkingPermit."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from aiohttp import ClientResponse


async def async_json(
    response: ClientResponse, *, on_error: Callable[[str], Exception]
) -> Any:
    """Decode a JSON response body or return None for empty responses."""
    text = await response.text()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        raise on_error("Response body is not valid JSON") from err
