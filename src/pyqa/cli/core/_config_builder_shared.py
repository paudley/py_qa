# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Shared helper utilities for CLI configuration building."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from ...filesystem.paths import ensure_absolute_path, try_ensure_absolute_path
from ._config_builder_constants import LintOptionKey

ModelT = TypeVar("ModelT", bound=BaseModel)
ValueT = TypeVar("ValueT")


def model_clone(instance: ModelT, updates: Mapping[str, ValueT] | None = None) -> ModelT:
    """Return a defensive copy of a Pydantic model applying field updates.

    Args:
        instance: Pydantic model instance being cloned.
        updates: Mapping of field overrides applied to the cloned instance.

    Returns:
        ModelT: Deep-cloned instance with requested updates.
    """

    return instance.model_copy(update=dict(updates or {}), deep=True)


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
    """Resolve a potentially relative path against the project root.

    Args:
        root: Project root directory used as the absolute base.
        path: Source path that may be absolute or relative.

    Returns:
        Path: Absolute path anchored to ``root``.
    """

    return ensure_absolute_path(path, base_dir=root)


def resolve_optional_path(root: Path, path: Path | None) -> Path | None:
    """Resolve an optional path, preserving ``None`` when unspecified.

    Args:
        root: Project root directory used as the absolute base.
        path: Optional path that should be resolved when provided.

    Returns:
        Path | None: Absolute path anchored to ``root`` or ``None`` when the input
        path is unspecified.
    """

    return try_ensure_absolute_path(path, base_dir=root)


def ensure_abs(root: Path, path: Path) -> Path:
    """Ensure ``path`` is absolute relative to ``root`` when required.

    Args:
        root: Project root directory used as the absolute base.
        path: Source path that may require conversion to an absolute path.

    Returns:
        Path: Absolute representation of ``path``.
    """

    return ensure_absolute_path(path, base_dir=root)


def is_within(candidate: Path, bound: Path) -> bool:
    """Return whether ``candidate`` resides within ``bound``.

    Args:
        candidate: Filesystem path under evaluation.
        bound: Directory that may contain ``candidate``.

    Returns:
        bool: ``True`` when ``candidate`` is located inside ``bound``.
    """

    try:
        candidate.relative_to(bound)
    except ValueError:
        return False
    return True


def is_within_any(candidate: Path, bounds: Iterable[Path]) -> bool:
    """Return whether ``candidate`` resides within any provided ``bounds``.

    Args:
        candidate: Filesystem path under evaluation.
        bounds: Iterable of boundary directories.

    Returns:
        bool: ``True`` when ``candidate`` resides within at least one boundary.
    """

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
