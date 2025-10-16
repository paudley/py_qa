# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Utility helpers shared by internal linters."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from pyqa.core.config.constants import ALWAYS_EXCLUDE_DIRS

if TYPE_CHECKING:  # pragma: no cover - type checking import
    from pyqa.cli.commands.lint.preparation import PreparedLintState


_PYTHON_EXTENSIONS: Final[tuple[str, ...]] = (".py", ".pyi")
_CACHE_SEGMENT_INDICATOR: Final[str] = "cache"


@dataclass(frozen=True, slots=True)
class _DiscoveryContext:
    """Describe discovery rules shared across helper functions."""

    excluded: Iterable[Path]
    root: Path
    extension_filter: set[str] | None
    include_dotfiles: bool


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
        Dot-prefixed files and directories are excluded unless the caller
        opts into ``include_dotfiles``.
    """

    options = state.options.target_options
    candidates: set[Path] = set()
    root = options.root.resolve()
    extension_filter = {ext.lower() for ext in extensions} if extensions is not None else None
    paths = [path.resolve() for path in options.paths]
    if not paths and not options.dirs:
        paths.append(root)
    include_dotfiles = options.include_dotfiles

    context = _DiscoveryContext(
        excluded=options.exclude,
        root=root,
        extension_filter=extension_filter,
        include_dotfiles=include_dotfiles,
    )

    for path in paths:
        _include_candidate(
            candidates,
            path,
            context=context,
        )
        if path.is_dir():
            resolved_dir = _resolve_within_root(path, root)
            if resolved_dir is None:
                continue
            candidates.update(_walk_files(resolved_dir, context))
    for directory in options.dirs:
        resolved_dir = _resolve_within_root(directory, root)
        if resolved_dir is None:
            continue
        candidates.update(_walk_files(resolved_dir, context))
    return sorted(candidates)


def collect_python_files(state: PreparedLintState) -> list[Path]:
    """Collect Python source files addressed by the current lint invocation.

    Args:
        state: Prepared lint state exposing user-supplied targets.

    Returns:
        list[Path]: Python source files drawn from the lint invocation.
    """

    return collect_target_files(state, extensions=_PYTHON_EXTENSIONS)


def _walk_files(directory: Path, context: _DiscoveryContext) -> set[Path]:
    """Collect files beneath ``directory`` while applying exclusions.

    Args:
        directory: Directory explored for candidate files.
        context: Discovery context describing exclusion lists and options.

    Returns:
        set[Path]: Resolved file paths discovered within ``directory``.
    """

    excluded = [path.resolve() for path in context.excluded]
    results: set[Path] = set()
    for candidate in directory.rglob("*"):
        if not candidate.is_file():
            continue
        if _is_excluded(candidate, excluded, context.root, context.include_dotfiles):
            continue
        resolved = _resolve_within_root(candidate, context.root)
        if resolved is None:
            continue
        if context.extension_filter and resolved.suffix.lower() not in context.extension_filter:
            continue
        results.add(resolved)
    return results


def _is_excluded(path: Path, excluded: Iterable[Path], root: Path, include_dotfiles: bool) -> bool:
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
    if any(_should_exclude_segment(part, include_dotfiles) for part in relative.parts):
        return True
    return False


def _should_exclude_segment(segment: str, include_dotfiles: bool) -> bool:
    """Return ``True`` when ``segment`` represents an excluded directory name.

    Args:
        segment: Individual path component extracted from a candidate path.
        include_dotfiles: Whether dot-prefixed segments should be retained.

    Returns:
        bool: ``True`` if the component should cause the path to be skipped.
    """

    lowered = segment.lower()
    if segment in ALWAYS_EXCLUDE_DIRS:
        return True
    if not include_dotfiles and segment.startswith("."):
        return True
    return _CACHE_SEGMENT_INDICATOR in lowered


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
    context: _DiscoveryContext,
) -> None:
    """Include ``path`` in ``candidates`` when it is an eligible file.

    Args:
        candidates: Accumulator tracking resolved candidate paths.
        path: Candidate path supplied by the caller.
        context: Discovery context describing exclusion lists and options.
    """

    if _is_excluded(path, context.excluded, context.root, context.include_dotfiles):
        return
    resolved = _resolve_within_root(path, context.root)
    if resolved is None or not resolved.is_file():
        return
    extension_filter = context.extension_filter
    if extension_filter and resolved.suffix.lower() not in extension_filter:
        return
    candidates.add(resolved)


__all__ = ["collect_target_files", "collect_python_files"]
