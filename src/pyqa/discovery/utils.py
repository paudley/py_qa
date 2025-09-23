# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Shared discovery helpers for filesystem traversal with exclusions."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Iterator

from ..constants import ALWAYS_EXCLUDE_DIRS


def iter_paths(
    root: Path,
    *,
    skip_patterns: Iterable[str] | None = None,
) -> Iterator[tuple[Path, list[str], list[str]]]:
    """Yield ``(directory, dirnames, filenames)`` honoring skip patterns and default exclusions."""

    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root):
        directory = Path(dirpath)
        if _should_skip(directory, root, skip_patterns):
            dirnames[:] = []
            continue
        yield directory, dirnames, filenames


def _should_skip(
    directory: Path, root: Path, skip_patterns: Iterable[str] | None
) -> bool:
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
