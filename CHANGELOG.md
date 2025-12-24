# Changelog

This project follows Keep a Changelog and Semantic Versioning.

## 0.2.1

- Fixed: tolerate empty JSON responses from favorite endpoints without raising `ParseError`.
- Internal: shared JSON decoding helper to reduce duplication between API and Auth.

## 0.2.0

- First CityParkingPermit client release (`pyCityParkingPermit`) with async-only Auth and `CityParkingPermitAPI` on aiohttp.
- Typed dataclass models (Account, Reservation, Favorite, Zone) with parsed UTC datetimes and field validation.
- Added `RateLimitError` with `Retry-After` support and cached User-Agent/version metadata.
- Exported `__version__`, tightened mypy/ruff defaults, and documented usage, testing, and publishing steps.

## 0.1.0

- Initial async client with account, reservation, and favorite endpoints
- Cookie-based login with retry on authentication errors
- Dataclass models and typed exceptions

Release checklist

- Update version and changelog
- Run `pre-commit run --all-files`
- Run `pytest`, `ruff check .`, and `mypy`
- Run `python -m build`
- Run `python -m twine check dist/*`
- Publish to PyPI
