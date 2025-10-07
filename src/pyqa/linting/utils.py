# SPDX-License-Identifier: MIT
"""Utility helpers shared by internal linters."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Final

from pyqa.core.config.constants import ALWAYS_EXCLUDE_DIRS

if TYPE_CHECKING:  # pragma: no cover - type checking import
    from pyqa.cli.commands.lint.preparation import PreparedLintState


_PYTHON_EXTENSIONS: Final[tuple[str, ...]] = (".py", ".pyi")


def collect_python_files(state: PreparedLintState) -> list[Path]:
    """Return Python source files addressed by the current lint invocation.

    Args:
        state: Prepared lint state exposing discovery options and root paths.

    Returns:
        Sorted list of Python files targeted for internal lint passes.
    """

    options = state.options.target_options
    candidates: set[Path] = set()
    root = options.root.resolve()
    paths = [path.resolve() for path in options.paths]
    if not paths and not options.dirs:
        paths.append(root)
    for path in paths:
        if _is_excluded(path, options.exclude, root):
            continue
        if path.is_file() and path.suffix in _PYTHON_EXTENSIONS:
            candidates.add(path)
        elif path.is_dir():
            candidates.update(_walk_python_files(path, options.exclude, root))
    for directory in options.dirs:
        dir_path = directory.resolve()
        candidates.update(_walk_python_files(dir_path, options.exclude, root))
    return sorted(candidates)


def _walk_python_files(directory: Path, exclude: Iterable[Path], root: Path) -> set[Path]:
    """Return Python files beneath ``directory`` after applying exclusions.

    Args:
        directory: Directory to scan recursively.
        exclude: Iterable of paths that should be excluded from scanning.
        root: Repository root used for relative exclusion matching.

    Returns:
        Set of resolved Python file paths.
    """

    excluded = [path.resolve() for path in exclude]
    results: set[Path] = set()
    for extension in _PYTHON_EXTENSIONS:
        for candidate in directory.rglob(f"*{extension}"):
            if _is_excluded(candidate, excluded, root):
                continue
            results.add(candidate)
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


__all__ = ["collect_python_files"]
