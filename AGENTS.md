# Codex instructions for pyCityParkingPermit

## Scope
- This file applies to this repository only.

## Language and style
- Python 3.13+ only.
- Prefer type hints, f-strings, and dataclasses.
- Keep docstrings in American English, sentence case.

## Code organization
- Public exports live in `src/pyCityParkingPermit/__init__.py`.
- API entrypoints live in `src/pyCityParkingPermit/api.py`.
- Data models live in `src/pyCityParkingPermit/models.py`.

## Quality
- Format with Ruff.
- Lint with Ruff and MyPy via pre-commit.
- Update tests under `tests/` for public API changes.
- Keep README and CHANGELOG in sync with API and model changes.

## Release checklist
- Update `CHANGELOG.md` and `pyproject.toml` version together.
- Run `pre-commit run --all-files`.
- Run `pytest tests/`.
- Build and check distributions: `python -m build` and `python -m twine check dist/*`.
- Publish by creating a version tag and pushing it, for example:
  - `git tag v0.0.0`
  - `git push --tags`
