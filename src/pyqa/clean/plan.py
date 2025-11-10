# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Planning helpers for repository cleanup."""

from __future__ import annotations

import shutil
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from pyqa.config import CleanConfig
from pyqa.core.config.constants import PY_QA_DIR_NAME
from pyqa.core.logging import info, warn
from pyqa.discovery.utils import iter_paths
from pyqa.platform.workspace import is_py_qa_workspace

PROTECTED_DIRECTORIES: Final[set[str]] = {".git", ".hg", ".svn"}


@dataclass(slots=True)
class CleanPlanItem:
    """Describe a single filesystem path scheduled for cleanup."""

    path: Path


@dataclass(slots=True)
class CleanPlan:
    """Represent cleanup targets and ignored project directories."""

    items: list[CleanPlanItem] = field(default_factory=list)
    ignored_py_qa: list[Path] = field(default_factory=list)

    @property
    def paths(self) -> list[Path]:
        """Return the filesystem paths slated for removal.

        Returns:
            list[Path]: Paths that will be removed when the plan executes.
        """

        return [item.path for item in self.items]


class CleanPlanner:
    """Build a cleanup plan from configuration and overrides."""

    def __init__(
        self,
        *,
        extra_patterns: Sequence[str] | None = None,
        extra_trees: Sequence[str] | None = None,
    ) -> None:
        """Initialise the planner with optional pattern and tree overrides.

        Args:
            extra_patterns: Additional glob patterns appended to configured
                patterns.
            extra_trees: Additional directory prefixes appended to configured
                tree lists.
        """

        self._extra_patterns = tuple(extra_patterns or ())
        self._extra_trees = tuple(extra_trees or ())

    @property
    def overrides(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Return the pattern and tree overrides configured for the planner.

        Returns:
            tuple[tuple[str, ...], tuple[str, ...]]: Tuples containing pattern
            and tree overrides provided at construction time.
        """

        return self._extra_patterns, self._extra_trees

    def plan(self, root: Path, config: CleanConfig) -> CleanPlan:
        """Build a cleanup plan for ``root`` using ``config`` and overrides.

        Args:
            root: Repository root scanned for cleanup targets.
            config: Configuration describing base patterns and tree roots.

        Returns:
            CleanPlan: Plan describing discovered cleanup items and ignored
            ``py_qa`` directories.
        """

        root = root.resolve()
        patterns = _merge_unique(config.patterns, self._extra_patterns)
        trees = _merge_unique(config.trees, self._extra_trees)
        skip_py_qa = not is_py_qa_workspace(root)

        info("✨ Cleaning repository temporary files...", use_emoji=True)
        collected, ignored_py_qa = _collect_matches_from_directory(
            root,
            patterns,
            root=root,
            skip_py_qa=skip_py_qa,
        )

        for tree in trees:
            base_dir = (root / tree).resolve()
            if not base_dir.exists():
                continue
            info(f"🧹 Cleaning {tree}/ ...", use_emoji=True)
            tree_items, tree_ignored = _collect_matches_from_directory(
                base_dir,
                patterns,
                root=root,
                skip_py_qa=skip_py_qa,
            )
            collected.update(tree_items)
            ignored_py_qa.extend(tree_ignored)

        if skip_py_qa:
            ignored_py_qa.extend(_discover_py_qa_directories(root))

        items = sorted(collected.values(), key=lambda item: item.path)
        return CleanPlan(items=items, ignored_py_qa=_dedupe_paths(ignored_py_qa))


def _collect_matches_from_directory(
    base: Path,
    patterns: Sequence[str],
    *,
    root: Path,
    skip_py_qa: bool,
) -> tuple[dict[Path, CleanPlanItem], list[Path]]:
    """Collect filesystem matches within ``base`` using ``patterns``.

    Args:
        base: Directory scanned for pattern matches.
        patterns: Glob patterns evaluated relative to ``base``.
        root: Repository root used when evaluating protected directories.
        skip_py_qa: When ``True`` ignore matches inside py_qa directories.

    Returns:
        tuple[dict[Path, CleanPlanItem], list[Path]]: Mapping of matched paths
        to plan items alongside skipped py_qa directories.
    """

    collected: dict[Path, CleanPlanItem] = {}
    ignored: list[Path] = []
    for directory, _subdirs, _files in iter_paths(base):
        for match in _match_patterns(directory, patterns):
            if _should_skip_py_qa(match, root, skip_py_qa):
                ignored.append(match)
                continue
            collected[match] = CleanPlanItem(path=match)
    return collected, ignored


def _merge_unique(primary: Sequence[str], extras: Sequence[str]) -> list[str]:
    """Return merged patterns with duplicates removed while preserving order.

    Args:
        primary: Primary collection of patterns.
        extras: Additional patterns appended after deduplication.

    Returns:
        list[str]: Ordered list of trimmed patterns without duplicates.
    """

    merged: list[str] = []
    seen: set[str] = set()
    for collection in (primary, extras):
        for candidate in collection:
            trimmed = candidate.strip()
            if not trimmed or trimmed in seen:
                continue
            merged.append(trimmed)
            seen.add(trimmed)
    return merged


def _is_protected(path: Path, root: Path) -> bool:
    """Return ``True`` when ``path`` resides in protected directories.

    Args:
        path: Candidate filesystem path.
        root: Repository root used to compute relative segments.

    Returns:
        bool: ``True`` if the path is inside protected directories; ``False``
        otherwise.
    """

    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    return any(part in PROTECTED_DIRECTORIES for part in relative.parts)


def _match_patterns(base: Path, patterns: Iterable[str]) -> set[Path]:
    """Collect paths under ``base`` that match any of the provided patterns.

    Args:
        base: Directory searched for pattern matches.
        patterns: Iterable of glob patterns evaluated against ``base``.

    Returns:
        set[Path]: Resolved paths matching the provided patterns.
    """

    matches: set[Path] = set()
    for pattern in patterns:
        for match_path in base.glob(pattern):
            resolved = match_path.resolve()
            if resolved == base or not resolved.exists():
                continue
            if _is_protected(resolved, base):
                continue
            matches.add(resolved)
    return matches


def _should_skip_py_qa(path: Path, root: Path, skip_py_qa: bool) -> bool:
    """Determine whether ``path`` should be skipped due to py_qa rules.

    Args:
        path: Candidate filesystem path.
        root: Repository root that anchors py_qa detection.
        skip_py_qa: When ``True`` skip paths inside py_qa directories.

    Returns:
        bool: ``True`` if the path should be skipped, ``False`` otherwise.
    """

    if not skip_py_qa:
        return False
    try:
        relative = path.resolve().relative_to(root)
    except (OSError, ValueError):
        try:
            relative = path.resolve()
        except OSError:
            relative = path
    return PY_QA_DIR_NAME in relative.parts


def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    """Remove duplicate paths while preserving input order.

    Args:
        paths: Iterable of candidate paths that may contain duplicates.

    Returns:
        list[Path]: Ordered paths with duplicates removed.
    """

    seen: set[Path] = set()
    ordered: list[Path] = []
    for path in paths:
        try:
            key = path.resolve()
        except OSError:
            key = path
        if key in seen:
            continue
        seen.add(key)
        ordered.append(path)
    return ordered


def _discover_py_qa_directories(root: Path) -> list[Path]:
    """Identify py_qa directories under ``root`` for reporting purposes.

    Args:
        root: Repository root scanned for py_qa directories.

    Returns:
        list[Path]: Directories named ``PY_QA_DIR_NAME`` that reside under
        ``root``.
    """

    try:
        candidates = list(root.rglob(PY_QA_DIR_NAME))
    except OSError:
        return []
    return [candidate for candidate in candidates if candidate.is_dir() and candidate.is_relative_to(root)]


def remove_path(path: Path) -> None:
    """Remove ``path`` from the filesystem, tolerating permission errors.

    Args:
        path: Filesystem path scheduled for deletion.
    """

    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink(missing_ok=True)
        except PermissionError:
            warn(f"Permission denied removing {path}", use_emoji=True)


__all__ = [
    "CleanPlan",
    "CleanPlanItem",
    "CleanPlanner",
    "PROTECTED_DIRECTORIES",
    "_collect_matches_from_directory",
    "_discover_py_qa_directories",
    "_dedupe_paths",
    "remove_path",
]
