# SPDX-License-Identifier: MIT
"""Utility helpers shared by internal linters."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from pyqa.core.config.constants import ALWAYS_EXCLUDE_DIRS

if False:  # pragma: no cover - import guard for type checking
    from pyqa.cli.commands.lint.preparation import PreparedLintState


def collect_python_files(state: "PreparedLintState") -> list[Path]:
    """Return Python source files addressed by the current lint invocation."""

    options = state.options.target_options
    candidates: set[Path] = set()
    root = options.root.resolve()
    paths = [path.resolve() for path in options.paths]
    if not paths and not options.dirs:
        paths.append(root)
    for path in paths:
        if _is_excluded(path, options.exclude, root):
            continue
        if path.is_file() and path.suffix in {".py", ".pyi"}:
            candidates.add(path)
        elif path.is_dir():
            candidates.update(_walk_python_files(path, options.exclude, root))
    for directory in options.dirs:
        dir_path = directory.resolve()
        candidates.update(_walk_python_files(dir_path, options.exclude, root))
    return sorted(candidates)


def _walk_python_files(directory: Path, exclude: Iterable[Path], root: Path) -> set[Path]:
    excluded = [path.resolve() for path in exclude]
    results: set[Path] = set()
    for candidate in directory.rglob("*.py"):
        if _is_excluded(candidate, excluded, root):
            continue
        results.add(candidate)
    for candidate in directory.rglob("*.pyi"):
        if _is_excluded(candidate, excluded, root):
            continue
        results.add(candidate)
    return results


def _is_excluded(path: Path, excluded: Iterable[Path], root: Path) -> bool:
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
