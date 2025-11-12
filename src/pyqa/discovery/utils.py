# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Shared discovery helpers for filesystem traversal with exclusions."""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from pathlib import Path

from pyqa.core.config.constants import ALWAYS_EXCLUDE_DIRS


def iter_paths(
    root: Path,
    *,
    skip_patterns: Iterable[str] | None = None,
) -> Iterator[tuple[Path, list[str], list[str]]]:
    """Return an iterator over ``(directory, dirnames, filenames)`` triples.

    Args:
        root: Root directory whose descendants should be traversed.
        skip_patterns: Optional iterable of substrings that disqualify directories.

    Returns:
        Iterator[tuple[Path, list[str], list[str]]]: Iterator yielding directory walk tuples.
    """

    return _iter_paths(root.resolve(), skip_patterns)


def _iter_paths(
    root: Path,
    skip_patterns: Iterable[str] | None,
) -> Iterator[tuple[Path, list[str], list[str]]]:
    """Yield directory traversal tuples while enforcing exclusions.

    Args:
        root: Resolved root directory to traverse.
        skip_patterns: Optional iterable of substrings that disqualify directories.

    Returns:
        Iterator[tuple[Path, list[str], list[str]]]: Iterator yielding directory walk tuples.

    Yields:
        tuple[Path, list[str], list[str]]: Directory path, mutable directories, and filenames.
    """

    for dirpath, dirnames, filenames in os.walk(root):
        directory = Path(dirpath)
        if _should_skip(directory, root, skip_patterns):
            dirnames[:] = []
            continue
        yield directory, dirnames, filenames


def _should_skip(directory: Path, root: Path, skip_patterns: Iterable[str] | None) -> bool:
    """Return whether ``directory`` should be excluded from traversal.

    Args:
        directory: Candidate directory encountered while walking ``root``.
        root: Root directory used to derive relative paths.
        skip_patterns: Optional iterable of substrings that trigger exclusion.

    Returns:
        bool: ``True`` when the directory should be pruned from traversal.
    """

    try:
        relative = directory.relative_to(root)
    except ValueError:
        return True
    parts = relative.parts
    if any(part in ALWAYS_EXCLUDE_DIRS for part in parts):
        return True
    if skip_patterns:
        rel_str = str(relative)
        if any(pattern in rel_str for pattern in skip_patterns):
            return True
    return False


__all__ = ["iter_paths"]
