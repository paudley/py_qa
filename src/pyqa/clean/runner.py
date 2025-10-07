# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Execution helpers for repository cleanup."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pyqa.config import CleanConfig
from pyqa.core.logging import ok

from .plan import CleanPlan, CleanPlanner, _remove_path


@dataclass(slots=True)
class CleanResult:
    """Capture the outcome of a cleanup operation."""

    removed: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)
    ignored_py_qa: list[Path] = field(default_factory=list)

    def register_removed(self, path: Path) -> None:
        """Record that ``path`` was removed during cleaning.

        Args:
            path: Filesystem path removed by the cleanup routine.
        """

        self.removed.append(path)

    def register_skipped(self, path: Path) -> None:
        """Record that ``path`` was skipped due to dry-run or protection rules.

        Args:
            path: Filesystem path retained after evaluation.
        """

        self.skipped.append(path)


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
    plan: CleanPlan = planner.plan(root, config)

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


__all__ = ["CleanResult", "sparkly_clean"]
