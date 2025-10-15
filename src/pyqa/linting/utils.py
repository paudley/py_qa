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
    """Collect lint target files filtered by optional extensions.

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

    for path in paths:
        _include_candidate(
            candidates,
            path,
            excluded=options.exclude,
            root=root,
            extension_filter=extension_filter,
        )
        if path.is_dir():
            resolved_dir = _resolve_within_root(path, root)
            if resolved_dir is None:
                continue
            candidates.update(_walk_files(resolved_dir, options.exclude, root, extension_filter))
    for directory in options.dirs:
        resolved_dir = _resolve_within_root(directory, root)
        if resolved_dir is None:
            continue
        candidates.update(_walk_files(resolved_dir, options.exclude, root, extension_filter))
    return sorted(candidates)


def collect_python_files(state: PreparedLintState) -> list[Path]:
    """Collect Python source files addressed by the current lint invocation.

    Args:
        state: Prepared lint state exposing user-supplied targets.

    Returns:
        list[Path]: Python source files drawn from the lint invocation.
    """

    return collect_target_files(state, extensions=_PYTHON_EXTENSIONS)


def _walk_files(
    directory: Path,
    exclude: Iterable[Path],
    root: Path,
    extension_filter: set[str] | None,
) -> set[Path]:
    """Collect files beneath ``directory`` while applying exclusions.

    Args:
        directory: Directory explored for candidate files.
        exclude: Iterable of paths explicitly excluded by the caller.
        root: Workspace root used to constrain traversal.
        extension_filter: Optional set of extensions used to filter results.

    Returns:
        set[Path]: Resolved file paths discovered within ``directory``.
    """

    excluded = [path.resolve() for path in exclude]
    results: set[Path] = set()
    for candidate in directory.rglob("*"):
        if not candidate.is_file():
            continue
        if _is_excluded(candidate, excluded, root):
            continue
        resolved = _resolve_within_root(candidate, root)
        if resolved is None:
            continue
        if extension_filter and resolved.suffix.lower() not in extension_filter:
            continue
        results.add(resolved)
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
        return True
    if any(part in ALWAYS_EXCLUDE_DIRS for part in relative.parts):
        return True
    return False


def _resolve_within_root(path: Path, root: Path) -> Path | None:
    """Resolve ``path`` ensuring it remains within ``root``.

    Args:
        path: Candidate path supplied by the caller.
        root: Workspace root constraining traversal.

    Returns:
        Path | None: Resolved path when ``path`` resides within ``root``;
        otherwise ``None``.
    """

    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def _include_candidate(
    candidates: set[Path],
    path: Path,
    *,
    excluded: Iterable[Path],
    root: Path,
    extension_filter: set[str] | None,
) -> None:
    """Include ``path`` in ``candidates`` when it is an eligible file.

    Args:
        candidates: Accumulator tracking resolved candidate paths.
        path: Candidate path supplied by the caller.
        excluded: Iterable of paths explicitly excluded by the caller.
        root: Workspace root constraining traversal.
        extension_filter: Optional set of extensions used to filter results.
    """

    if _is_excluded(path, excluded, root):
        return
    resolved = _resolve_within_root(path, root)
    if resolved is None or not resolved.is_file():
        return
    if extension_filter and resolved.suffix.lower() not in extension_filter:
        return
    candidates.add(resolved)


__all__ = ["collect_target_files", "collect_python_files"]
