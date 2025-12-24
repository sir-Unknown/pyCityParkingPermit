# Contributing

Thanks for contributing to `pyCityParkingPermit`. This library is async-only and targets
Python 3.13+.

## Getting started

- Create a virtual environment: `python -m venv .venv`
- Activate it: `. .venv/bin/activate`
- Install dependencies: `python -m pip install -e '.[test,dev]'`
- Install pre-commit hooks (recommended): `pre-commit install`

## Quality checks

- Format and lint: `pre-commit run --all-files` (runs Ruff + MyPy)
- Tests: `pytest tests/`
- Type check: `mypy`
- Build: `python -m build`

## Style and scope

- Keep code async-only; no synchronous wrappers.
- Prefer typed dataclasses for API models.
- Avoid new dependencies unless required.
- Update README and CHANGELOG when adjusting the public API or models.

## Releasing

- Bump `pyproject.toml` and `CHANGELOG.md` together.
- Run `pre-commit run --all-files`, `pytest tests/`, `python -m build`, and `python -m twine check dist/*`.
