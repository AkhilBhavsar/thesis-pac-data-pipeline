"""Thesis Dagster orchestration package."""

from __future__ import annotations

from typing import Any


__all__ = ["defs"]


def __getattr__(name: str) -> Any:
    """Load Dagster definitions only when explicitly requested."""

    if name == "defs":
        from thesis_orchestration.definitions import defs

        globals()["defs"] = defs
        return defs

    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )
