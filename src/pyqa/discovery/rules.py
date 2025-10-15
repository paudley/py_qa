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
    """Return ``True`` when *candidate* resides within any *bases* entries."""

    return any(_is_under_base(candidate, base) for base in bases)


def normalize_path_requirement(raw: str) -> tuple[str, ...]:
    """Convert a requirement string into normalised path segments."""

    return _normalise_path_requirement(raw)


def path_matches_requirements(candidate: Path, root: Path, requirements: Sequence[tuple[str, ...]]) -> bool:
    """Return ``True`` when *candidate* satisfies all required path fragments."""

    return _path_matches_requirements(candidate, root, tuple(requirements))


@memoize(maxsize=512)
def _normalise_path_requirement(raw: str) -> tuple[str, ...]:
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
    if not requirements:
        return True

    parts = _candidate_parts(candidate, root)
    if not parts:
        return False

    return all(_has_path_sequence(parts, requirement) for requirement in requirements)


@memoize(maxsize=1024)
def _candidate_parts(candidate: Path, root: Path) -> tuple[str, ...]:
    relative_path = _resolve_relative_path(candidate, root)
    normalised = _normalise_parts(relative_path)
    if normalised:
        return normalised
    return _fallback_parts(candidate)


def _resolve_relative_path(candidate: Path, root: Path) -> Path | None:
    if not candidate.is_absolute():
        return candidate
    try:
        return candidate.relative_to(root)
    except ValueError:
        return candidate
    except OSError:
        return None


def _normalise_parts(path: Path | None) -> tuple[str, ...]:
    if path is None:
        return ()
    try:
        return tuple(part for part in path.parts if part not in ("", _CURRENT_DIRECTORY_MARKER))
    except OSError:
        return ()


def _fallback_parts(candidate: Path) -> tuple[str, ...]:
    return tuple(segment for segment in candidate.as_posix().split(_PATH_SEPARATOR) if segment)


def _has_path_sequence(parts: Sequence[str], required: tuple[str, ...]) -> bool:
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
    try:
        relative = path.relative_to(root)
    except ValueError:
        return None
    return str(relative)


def _is_under_base(candidate: Path, base: Path) -> bool:
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
