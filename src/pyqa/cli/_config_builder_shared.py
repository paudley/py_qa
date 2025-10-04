# SPDX-License-Identifier: MIT
"""Shared helper utilities for CLI configuration building."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from ..filesystem.paths import ensure_absolute_path, try_ensure_absolute_path
from ._config_builder_constants import LintOptionKey

ModelT = TypeVar("ModelT", bound=BaseModel)
ValueT = TypeVar("ValueT")


def model_clone(instance: ModelT, **updates: object) -> ModelT:
    """Return a defensive copy of a Pydantic model applying field updates."""

    return instance.model_copy(update=updates, deep=True)


def select_flag(
    candidate: bool,
    fallback: bool,
    key: LintOptionKey,
    provided: Collection[str],
) -> bool:
    """Return the flag value honouring whether the user explicitly provided it.

    Args:
        candidate: Flag derived from CLI or configuration input.
        fallback: Default value sourced from the existing configuration.
        key: Option key that guards whether the CLI flag was supplied.
        provided: Collection of option identifiers supplied by the user.

    Returns:
        bool: ``candidate`` when explicitly provided, otherwise ``fallback``.

    """

    return candidate if key.value in provided else fallback


def select_value(
    value: ValueT,
    fallback: ValueT,
    key: LintOptionKey,
    provided: Collection[str],
) -> ValueT:
    """Return the override value when explicitly provided, otherwise fallback.

    Args:
        value: Override value derived from CLI inputs.
        fallback: Default value from the current configuration state.
        key: Option key mapping to the override flag.
        provided: Collection of option identifiers supplied by the user.

    Returns:
        ValueT: ``value`` when the user supplied the flag, otherwise ``fallback``.

    """

    return value if key.value in provided else fallback


def resolve_path(root: Path, path: Path) -> Path:
    """Resolve a potentially relative path against the project root."""

    return ensure_absolute_path(path, base_dir=root)


def resolve_optional_path(root: Path, path: Path | None) -> Path | None:
    """Resolve an optional path, preserving ``None`` when unspecified."""

    return try_ensure_absolute_path(path, base_dir=root)


def ensure_abs(root: Path, path: Path) -> Path:
    """Ensure ``path`` is absolute relative to ``root`` when required."""

    return ensure_absolute_path(path, base_dir=root)


def is_within(candidate: Path, bound: Path) -> bool:
    """Return whether ``candidate`` resides within ``bound``."""

    try:
        candidate.relative_to(bound)
    except ValueError:
        return False
    return True


def is_within_any(candidate: Path, bounds: Iterable[Path]) -> bool:
    """Return whether ``candidate`` resides within any provided ``bounds``."""

    return any(is_within(candidate, bound) for bound in bounds)


__all__ = [
    "ModelT",
    "ValueT",
    "model_clone",
    "select_flag",
    "select_value",
    "resolve_path",
    "resolve_optional_path",
    "ensure_abs",
    "is_within",
    "is_within_any",
]
