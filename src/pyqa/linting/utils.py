# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Utility helpers shared by internal linters."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Final

from pyqa.core.config.constants import ALWAYS_EXCLUDE_DIRS

if TYPE_CHECKING:  # pragma: no cover - type checking import
    from pyqa.cli.commands.lint.preparation import PreparedLintState


_PYTHON_EXTENSIONS: Final[tuple[str, ...]] = (".py", ".pyi")


def collect_target_files(
    state: PreparedLintState,
    *,
    extensions: Iterable[str] | None = None,
) -> list[Path]:
    """Return lint target files filtered by optional extensions.

    Args:
        state: Prepared lint state exposing user-supplied targets.
        extensions: Optional iterable of lowercase extensions that should be
            included. When ``None`` all discovered files are returned.

    Returns:
        Sorted list of resolved file paths matching the requested filters.
    """

    options = state.options.target_options
    candidates: set[Path] = set()
    root = options.root.resolve()
    extension_filter = {ext.lower() for ext in extensions} if extensions is not None else None
    paths = [path.resolve() for path in options.paths]
    if not paths and not options.dirs:
        paths.append(root)

    def _maybe_add(file_path: Path) -> None:
        if extension_filter is None or file_path.suffix.lower() in extension_filter:
            candidates.add(file_path)

    for path in paths:
        if _is_excluded(path, options.exclude, root):
            continue
        if path.is_file():
            _maybe_add(path)
        elif path.is_dir():
            candidates.update(_walk_files(path, options.exclude, root, extension_filter))
    for directory in options.dirs:
        dir_path = directory.resolve()
        candidates.update(_walk_files(dir_path, options.exclude, root, extension_filter))
    return sorted(candidates)


def collect_python_files(state: PreparedLintState) -> list[Path]:
    """Return Python source files addressed by the current lint invocation."""

    return collect_target_files(state, extensions=_PYTHON_EXTENSIONS)


def _walk_files(
    directory: Path,
    exclude: Iterable[Path],
    root: Path,
    extension_filter: set[str] | None,
) -> set[Path]:
    """Return files beneath ``directory`` while applying exclusions."""

    excluded = [path.resolve() for path in exclude]
    results: set[Path] = set()
    for candidate in directory.rglob("*"):
        if not candidate.is_file():
            continue
        if _is_excluded(candidate, excluded, root):
            continue
        if extension_filter and candidate.suffix.lower() not in extension_filter:
            continue
        results.add(candidate.resolve())
    return results


def _is_excluded(path: Path, excluded: Iterable[Path], root: Path) -> bool:
    """Return ``True`` when ``path`` should be ignored during scanning.

    Args:
        path: File or directory under consideration.
        excluded: Paths explicitly excluded by user configuration.
        root: Repository root for default exclusion checks.

    Returns:
        ``True`` if the path should be skipped by internal linters.
    """

    path = path.resolve()
    for skip in excluded:
        try:
            path.relative_to(skip)
        except ValueError:
            continue
        return True
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    if any(part in ALWAYS_EXCLUDE_DIRS for part in relative.parts):
        return True
    return False


__all__ = ["collect_target_files", "collect_python_files"]
