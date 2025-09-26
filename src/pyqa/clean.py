# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.

"""Utilities for removing temporary artefacts from a repository."""

from __future__ import annotations

import shutil
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .config import CleanConfig
from .discovery.utils import iter_paths
from .logging import info, ok, warn


@dataclass(slots=True)
class CleanPlanItem:
    path: Path


@dataclass(slots=True)
class CleanPlan:
    items: list[CleanPlanItem] = field(default_factory=list)

    @property
    def paths(self) -> list[Path]:
        return [item.path for item in self.items]


@dataclass(slots=True)
class CleanResult:
    removed: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)

    def register_removed(self, path: Path) -> None:
        self.removed.append(path)

    def register_skipped(self, path: Path) -> None:
        self.skipped.append(path)


class CleanPlanner:
    """Build a cleanup plan from configuration and overrides."""

    def __init__(
        self,
        *,
        extra_patterns: Sequence[str] | None = None,
        extra_trees: Sequence[str] | None = None,
    ) -> None:
        self._extra_patterns = tuple(extra_patterns or ())
        self._extra_trees = tuple(extra_trees or ())

    def plan(self, root: Path, config: CleanConfig) -> CleanPlan:
        root = root.resolve()
        patterns = _merge_unique(config.patterns, self._extra_patterns)
        trees = _merge_unique(config.trees, self._extra_trees)

        collected: dict[Path, CleanPlanItem] = {}

        info("✨ Cleaning repository temporary files...", use_emoji=True)
        for directory, _subdirs, _files in iter_paths(root):
            matches = _match_patterns(directory, patterns)
            for path in matches:
                collected[path] = CleanPlanItem(path=path)

        for tree in trees:
            directory = (root / tree).resolve()
            if not directory.exists():
                continue
            info(f"🧹 Cleaning {tree}/ ...", use_emoji=True)
            for subdir, _subdirs, _files in iter_paths(directory):
                matches = _match_patterns(subdir, patterns)
                for path in matches:
                    collected[path] = CleanPlanItem(path=path)

        items = sorted(collected.values(), key=lambda item: item.path)
        return CleanPlan(items=items)


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

    result = CleanResult()
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


def _merge_unique(primary: Sequence[str], extras: Sequence[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for collection in (primary, extras):
        for value in collection:
            value = value.strip()
            if not value or value in seen:
                continue
            merged.append(value)
            seen.add(value)
    return merged


def _is_protected(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    protected_names = {".git", ".hg", ".svn"}
    return any(part in protected_names for part in relative.parts)


def _match_patterns(base: Path, patterns: Iterable[str]) -> set[Path]:
    matches: set[Path] = set()
    for pattern in patterns:
        iterator = base.glob(pattern)
        for candidate in iterator:
            candidate = candidate.resolve()
            if candidate == base:
                continue
            if not candidate.exists():
                continue
            if _is_protected(candidate, base):
                continue
            matches.add(candidate)
    return matches


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink(missing_ok=True)
        except PermissionError:
            warn(f"Permission denied removing {path}", use_emoji=True)


__all__ = ["CleanPlan", "CleanPlanItem", "CleanPlanner", "CleanResult", "sparkly_clean"]
