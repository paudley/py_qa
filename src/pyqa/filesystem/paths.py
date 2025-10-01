# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Helpers for reasoning about filesystem paths."""

from __future__ import annotations

import os
from functools import lru_cache
from os import PathLike
from pathlib import Path
from typing import Final

_Pathish = str | PathLike[str] | Path
_DEFAULT_CACHE_SIZE: Final[int] = 1024


@lru_cache(maxsize=_DEFAULT_CACHE_SIZE)
def _best_effort_resolve(path: Path) -> Path:
    """Return ``path`` resolved where possible without raising.

    Args:
        path: Candidate path to resolve.

    Returns:
        Path: Absolute variant when resolution succeeds; otherwise the closest
        achievable approximation.

    """

    try:
        return path.resolve(strict=False)
    except (OSError, RuntimeError):
        return path.absolute() if not path.is_absolute() else path


def normalize_path(path: _Pathish, *, base_dir: _Pathish | None = None) -> Path:
    """Return ``path`` normalised relative to ``base_dir``.

    Args:
        path: Filesystem path supplied by the caller.
        base_dir: Base directory used to relativise the path. Defaults to
            ``Path.cwd()`` when omitted.

    Returns:
        Path: Relative path when both inputs share a lineage, otherwise the
        resolved absolute candidate.

    Raises:
        ValueError: If ``path`` is ``None``.

    """

    if path is None:
        raise ValueError("path must not be None")

    raw_path = Path(path).expanduser()
    base_candidate = Path.cwd() if base_dir is None else Path(base_dir)
    base = _best_effort_resolve(base_candidate.expanduser())

    candidate = raw_path if raw_path.is_absolute() else base / raw_path
    candidate = _best_effort_resolve(candidate)

    try:
        return candidate.relative_to(base)
    except ValueError:
        try:
            return Path(os.path.relpath(candidate, base))
        except ValueError:
            return candidate


def normalize_path_key(path: _Pathish, *, base_dir: _Pathish | None = None) -> str:
    """Return a normalised key for ``path``.

    Args:
        path: Path for which to build the key.
        base_dir: Optional base directory used for relativisation.

    Returns:
        str: POSIX-style normalised representation.

    """

    normalized_path = normalize_path(path, base_dir=base_dir)
    return normalized_path.as_posix()


def display_relative_path(path: _Pathish, root: _Pathish) -> str:
    """Return a display-friendly representation of ``path`` relative to ``root``.

    Args:
        path: Path to present to the user.
        root: Base directory used for relativisation.

    Returns:
        str: Relative POSIX path when possible, otherwise the resolved absolute
        representation or the original string fallback.

    """

    relative_display = _safe_relative_display(path, root)
    if relative_display is not None:
        return relative_display
    resolved_display = _safe_resolved_display(path)
    return resolved_display if resolved_display is not None else str(path)


def _safe_relative_display(path: _Pathish, root: _Pathish) -> str | None:
    """Return a relative POSIX string when ``path`` can be normalised.

    Args:
        path: Path to normalise relative to ``root``.
        root: Base directory used during normalisation.

    Returns:
        str | None: POSIX-formatted relative path, or ``None`` when the
        relationship cannot be established due to mismatched roots.

    """

    try:
        return normalize_path(path, base_dir=root).as_posix()
    except ValueError:
        return None


def _safe_resolved_display(path: _Pathish) -> str | None:
    """Return an absolute best-effort representation of ``path``.

    Args:
        path: Path to resolve.

    Returns:
        str | None: POSIX-formatted absolute path when the input can be
        resolved; ``None`` when coercion fails.

    """

    try:
        return _best_effort_resolve(Path(path)).as_posix()
    except (TypeError, ValueError):
        return None


normalise_path_key = normalize_path_key


__all__ = (
    "display_relative_path",
    "normalise_path_key",
    "normalize_path",
    "normalize_path_key",
)
