# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Discovery helper rules shared across planners and catalog strategies."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

from pyqa.cache.in_memory import memoize

_CURRENT_DIRECTORY_MARKER = "."
_PATH_SEPARATOR = "/"


def compile_exclude_arguments(excluded_paths: Iterable[Path], root: Path) -> set[str]:
    """Return CLI exclusion arguments for discovery-aware scanners.

    Args:
        excluded_paths: Paths that should be skipped by downstream tooling.
        root: Project root used to compute relative arguments.

    Returns:
        set[str]: Absolute and, when applicable, root-relative exclusion strings.
    """

    arguments: set[str] = set()
    resolved_root = root.resolve()
    for path in excluded_paths:
        resolved = path.resolve()
        arguments.add(str(resolved))
        if relative := _relative_to_root(resolved, resolved_root):
            arguments.add(relative)
    return arguments


def is_under_any(candidate: Path, bases: Iterable[Path]) -> bool:
    """Return whether ``candidate`` resides within any ``bases`` entries.

    Args:
        candidate: Filesystem path evaluated against the provided bases.
        bases: Collection of base directories that may contain ``candidate``.

    Returns:
        bool: ``True`` when ``candidate`` is located under any base directory.
    """

    return any(_is_under_base(candidate, base) for base in bases)


def normalize_path_requirement(raw: str) -> tuple[str, ...]:
    """Convert a requirement string into normalised path segments.

    Args:
        raw: Requirement string containing slash-separated path fragments.

    Returns:
        tuple[str, ...]: Normalised requirement components without separators.
    """

    return _normalise_path_requirement(raw)


def path_matches_requirements(candidate: Path, root: Path, requirements: Sequence[tuple[str, ...]]) -> bool:
    """Return whether ``candidate`` satisfies every requirement sequence.

    Args:
        candidate: Filesystem path evaluated against the requirements.
        root: Repository root used to derive relative candidate parts.
        requirements: Iterable of path-fragment tuples that must each match.

    Returns:
        bool: ``True`` when all requirement sequences match the candidate path.
    """

    return _path_matches_requirements(candidate, root, tuple(requirements))


@memoize(maxsize=512)
def _normalise_path_requirement(raw: str) -> tuple[str, ...]:
    """Normalise requirement strings into path segments.

    Args:
        raw: Requirement specification supplied by the caller.

    Returns:
        tuple[str, ...]: Normalised requirement segments.
    """

    cleaned = raw.replace("\\", "/").strip()
    if not cleaned:
        return ()
    segments = [segment for segment in cleaned.split("/") if segment]
    return tuple(segments)


def _path_matches_requirements(
    candidate: Path,
    root: Path,
    requirements: tuple[tuple[str, ...], ...],
) -> bool:
    """Return whether ``candidate`` matches the provided requirements.

    Args:
        candidate: Filesystem path under evaluation.
        root: Repository root directory used to derive relative parts.
        requirements: Requirement tuples that must be found in the path.

    Returns:
        bool: ``True`` when the candidate satisfies all requirements.
    """

    if not requirements:
        return True

    parts = _candidate_parts(candidate, root)
    if not parts:
        return False

    return all(_has_path_sequence(parts, requirement) for requirement in requirements)


@memoize(maxsize=1024)
def _candidate_parts(candidate: Path, root: Path) -> tuple[str, ...]:
    """Return normalised path parts for ``candidate`` relative to ``root``.

    Args:
        candidate: Filesystem path to normalise.
        root: Repository root directory used for relative resolution.

    Returns:
        tuple[str, ...]: Normalised path components for the candidate.
    """

    relative_path = _resolve_relative_path(candidate, root)
    normalised = _normalise_parts(relative_path)
    if normalised:
        return normalised
    return _fallback_parts(candidate)


def _resolve_relative_path(candidate: Path, root: Path) -> Path | None:
    """Return ``candidate`` relative to ``root`` when possible.

    Args:
        candidate: Filesystem path to resolve.
        root: Repository root directory used for relative resolution.

    Returns:
        Path | None: Relative path when derivable; otherwise ``None``.
    """

    if not candidate.is_absolute():
        return candidate
    try:
        return candidate.relative_to(root)
    except ValueError:
        return candidate
    except OSError:
        return None


def _normalise_parts(path: Path | None) -> tuple[str, ...]:
    """Return cleaned path components for ``path``.

    Args:
        path: Path whose parts should be normalised.

    Returns:
        tuple[str, ...]: Normalised path components without special markers.
    """

    if path is None:
        return ()
    try:
        return tuple(part for part in path.parts if part not in ("", _CURRENT_DIRECTORY_MARKER))
    except OSError:
        return ()


def _fallback_parts(candidate: Path) -> tuple[str, ...]:
    """Return normalised parts for ``candidate`` using POSIX splitting.

    Args:
        candidate: Path to normalise when a structured path is unavailable.

    Returns:
        tuple[str, ...]: Normalised path fragments obtained via string splitting.
    """

    return tuple(segment for segment in candidate.as_posix().split(_PATH_SEPARATOR) if segment)


def _has_path_sequence(parts: Sequence[str], required: tuple[str, ...]) -> bool:
    """Return whether ``parts`` contains the ordered ``required`` segments.

    Args:
        parts: Candidate path components derived from a filesystem path.
        required: Requirement sequence expected to appear in ``parts``.

    Returns:
        bool: ``True`` when the ordered sequence is present within ``parts``.
    """

    if not required:
        return True
    if len(required) == 1:
        target = required[0]
        return any(part == target for part in parts)

    length = len(required)
    limit = len(parts) - length + 1
    if limit <= 0:
        return False
    return any(tuple(parts[offset : offset + length]) == required for offset in range(limit))


def _relative_to_root(path: Path, root: Path) -> str | None:
    """Return a root-relative string for ``path`` when derivable.

    Args:
        path: Path to convert into a root-relative string.
        root: Repository root directory used for relative resolution.

    Returns:
        str | None: Relative path string when derivable; otherwise ``None``.
    """

    try:
        relative = path.relative_to(root)
    except ValueError:
        return None
    return str(relative)


def _is_under_base(candidate: Path, base: Path) -> bool:
    """Return whether ``candidate`` resides underneath ``base``.

    Args:
        candidate: Filesystem path evaluated for containment.
        base: Directory used as the containment boundary.

    Returns:
        bool: ``True`` when ``candidate`` is located within ``base``.
    """

    try:
        candidate.resolve().relative_to(base.resolve())
    except ValueError:
        return False
    return True


__all__ = [
    "compile_exclude_arguments",
    "is_under_any",
    "normalize_path_requirement",
    "path_matches_requirements",
]
