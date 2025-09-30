"""Helpers for reasoning about filesystem paths."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from os import PathLike

_Pathish = Union[str, "PathLike[str]", Path]


def _best_effort_resolve(path: Path) -> Path:
    """Resolve ``path`` without failing on missing segments.

    Args:
        path: Candidate path to resolve.

    Returns:
        ``Path`` resolved as far as possible. Missing intermediate segments keep the
        original structure instead of raising an ``OSError``.

    """
    try:
        return path.resolve(strict=False)
    except (OSError, RuntimeError):
        # ``Path.absolute`` is less strict and still provides an absolute variant.
        return path.absolute() if not path.is_absolute() else path


def normalize_path(path: _Pathish, *, base_dir: _Pathish | None = None) -> Path:
    """Normalise ``path`` to a ``Path`` relative to ``base_dir`` (defaults to ``Path.cwd()``).

    Args:
        path: Raw filesystem path supplied by the caller. Strings, ``Path`` objects, and
            ``os.PathLike`` implementations are accepted.
        base_dir: Directory against which the result should be relativised. When omitted,
            ``Path.cwd()`` evaluated at call time is used. ``base_dir`` does not need to
            exist on disk and may itself be relative.

    Returns:
        ``Path`` normalised for comparison and relative to ``base_dir``. Redundant ``."`
        segments are removed. The result may contain ``..`` segments when ``path`` points
        outside of ``base_dir``. If the operating system cannot express a relative path
        between both locations (for example on Windows when they reside on different drives),
        the absolute best-effort resolved path is returned instead.

    Raises:
        ValueError: If ``path`` is ``None``.

    """
    if path is None:
        raise ValueError("path must not be None")

    raw = Path(path).expanduser()

    base = Path.cwd() if base_dir is None else Path(base_dir)
    base = _best_effort_resolve(base.expanduser())

    candidate = raw if raw.is_absolute() else base / raw
    candidate = _best_effort_resolve(candidate)

    try:
        relative = candidate.relative_to(base)
    except ValueError:
        try:
            text = os.path.relpath(candidate, base)
        except ValueError:
            return candidate
        return Path(text)
    return relative


def normalize_path_key(path: _Pathish, *, base_dir: _Pathish | None = None) -> str:
    """Return a normalised cache key for ``path``.

    Args:
        path: Path for which to build a key.
        base_dir: Reference directory for relativisation. Defaults to the current working
            directory when omitted.

    Returns:
        ``str`` representing the path in POSIX form relative to ``base_dir``.

    """
    normalised = normalize_path(path, base_dir=base_dir)
    return normalised.as_posix()


def display_relative_path(path: _Pathish, root: _Pathish) -> str:
    """Return a user-facing string for ``path`` relative to ``root`` when possible.

    Args:
        path: Path to display.
        root: Base directory used for relativisation.

    Returns:
        ``str`` suitable for display. The value prefers a POSIX-style relative path and
        falls back to the best-effort absolute path when no relative form exists.

    """
    try:
        relative = normalize_path(path, base_dir=root)
        return relative.as_posix()
    except ValueError:
        pass
    try:
        return _best_effort_resolve(Path(path)).as_posix()
    except (TypeError, ValueError):
        return str(path)


normalise_path_key = normalize_path_key


__all__ = [
    "display_relative_path",
    "normalise_path_key",
    "normalize_path",
    "normalize_path_key",
]
