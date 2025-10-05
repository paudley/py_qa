# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Utilities for removing temporary artefacts from a repository."""

from __future__ import annotations

import shutil
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from .config import CleanConfig
from .constants import PY_QA_DIR_NAME
from .discovery.utils import iter_paths
from .logging import info, ok, warn
from .workspace import is_py_qa_workspace

PROTECTED_DIRECTORIES: Final[set[str]] = {".git", ".hg", ".svn"}


@dataclass(slots=True)
class CleanPlanItem:
    """Describe a single filesystem path scheduled for cleanup."""

    path: Path


@dataclass(slots=True)
class CleanPlan:
    """Aggregate cleanup targets and ignored project directories."""

    items: list[CleanPlanItem] = field(default_factory=list)
    ignored_py_qa: list[Path] = field(default_factory=list)

    @property
    def paths(self) -> list[Path]:
        """Return the list of filesystem paths slated for removal."""

        return [item.path for item in self.items]


@dataclass(slots=True)
class CleanResult:
    """Capture the outcome of a cleanup operation."""

    removed: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    ignored_py_qa: list[Path] = field(default_factory=list)

    def register_removed(self, path: Path) -> None:
        """Record a path removed during cleanup."""

        self.removed.append(path)

    def register_skipped(self, path: Path) -> None:
        """Record a path that would be removed during a dry run."""

        self.skipped.append(path)


class CleanPlanner:
    """Build a cleanup plan from configuration and overrides."""

    def __init__(
        self,
        *,
        extra_patterns: Sequence[str] | None = None,
        extra_trees: Sequence[str] | None = None,
    ) -> None:
        """Create a planner with optional pattern or tree overrides.

        Args:
            extra_patterns: Additional glob patterns supplied via CLI.
            extra_trees: Additional tree roots supplied via CLI.
        """

        self._extra_patterns = tuple(extra_patterns or ())
        self._extra_trees = tuple(extra_trees or ())

    @property
    def overrides(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Return the pattern and tree overrides configured for the planner."""

        return self._extra_patterns, self._extra_trees

    def plan(self, root: Path, config: CleanConfig) -> CleanPlan:
        """Return a cleanup plan for ``root`` based on ``config`` and overrides."""

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


def sparkly_clean(
    root: Path,
    *,
    config: CleanConfig,
    extra_patterns: Sequence[str] | None = None,
    extra_trees: Sequence[str] | None = None,
    dry_run: bool = False,
) -> CleanResult:
    """Remove temporary artefacts under *root* based on *config* and overrides."""
    planner = CleanPlanner(
        extra_patterns=extra_patterns,
        extra_trees=extra_trees,
    )
    plan = planner.plan(root, config)

    result = CleanResult(ignored_py_qa=list(plan.ignored_py_qa))
    for item in plan.items:
        path = item.path
        if dry_run:
            result.register_skipped(path)
            continue
        _remove_path(path)
        result.register_removed(path)

    if dry_run:
        ok(
            f"Dry run complete; {len(result.skipped)} paths would be removed",
            use_emoji=True,
        )
    else:
        ok(f"Removed {len(result.removed)} paths", use_emoji=True)
    return result


def _collect_matches_from_directory(
    base: Path,
    patterns: Sequence[str],
    *,
    root: Path,
    skip_py_qa: bool,
) -> tuple[dict[Path, CleanPlanItem], list[Path]]:
    """Return plan items and ignored paths discovered beneath ``base``.

    Args:
        base: Directory to search for pattern matches.
        patterns: Glob patterns used to discover cleanup targets.
        root: Repository root used for relative comparisons.
        skip_py_qa: Whether py-qa cache directories should be preserved.

    Returns:
        tuple containing a mapping of paths to plan items and a list of ignored
        ``py-qa`` directories encountered during discovery.
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
    """Return a list merging two string sequences without duplicates."""

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
    """Return whether ``path`` resides inside a protected VCS directory."""

    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    return any(part in PROTECTED_DIRECTORIES for part in relative.parts)


def _match_patterns(base: Path, patterns: Iterable[str]) -> set[Path]:
    """Return filesystem paths matching ``patterns`` beneath ``base``."""

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
    """Return whether ``path`` should be preserved due to py-qa cache rules."""

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
    """Return ``paths`` without duplicates while maintaining order."""

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
    """Return all ``.py-qa`` directories contained within ``root``."""

    try:
        candidates = list(root.rglob(PY_QA_DIR_NAME))
    except OSError:
        return []
    return [candidate for candidate in candidates if candidate.is_dir() and candidate.is_relative_to(root)]


def _remove_path(path: Path) -> None:
    """Remove ``path`` from disk, warning on permission issues."""

    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink(missing_ok=True)
        except PermissionError:
            warn(f"Permission denied removing {path}", use_emoji=True)


__all__ = ["CleanPlan", "CleanPlanItem", "CleanPlanner", "CleanResult", "sparkly_clean"]
