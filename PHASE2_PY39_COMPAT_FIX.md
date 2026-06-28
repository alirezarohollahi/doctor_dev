# Phase 2 - Python 3.9 Compatibility Fix

This patch removes Python 3.10-only union annotations from runtime and Pydantic-facing code paths.

## Fixed

- Replaced `str | None` and similar PEP 604 annotations with `typing.Optional[...]`.
- Updated node FastAPI/Pydantic request models so they import correctly on Python 3.9.
- Updated panel Pydantic schemas and helper modules for the same compatibility issue.
- Kept existing `main.py` env-driven panel/node mode behavior unchanged.
- Kept `doctor_dev.sh` behavior unchanged.

## Why

Python 3.9 cannot evaluate annotations such as `str | None` when Pydantic/FastAPI resolves model type hints. This caused node mode to crash during import of `doctor_dev_node.server`.
