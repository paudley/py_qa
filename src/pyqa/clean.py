# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Utilities for removing temporary artefacts from a repository."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from .logging import info, ok, warn

DEFAULT_PATTERNS: tuple[str, ...] = (
    "*.log",
    ".*cache",
    ".claude*.json",
    ".coverage",
    ".hypothesis",
    ".stream*.json",
    ".venv",
    "__pycache__",
    "chroma*db",
    "coverage*",
    "dist",
    "filesystem_store",
    "htmlcov*",
)

DEFAULT_TREES: tuple[str, ...] = ("examples", "packages")


@dataclass(slots=True)
class CleanResult:
    removed: list[Path] = field(default_factory=list)
    skipped: list[Path] = field(default_factory=list)

    def register_removed(self, path: Path) -> None:
        self.removed.append(path)

    def register_skipped(self, path: Path) -> None:
        self.skipped.append(path)


def sparkly_clean(
    root: Path,
    *,
    patterns: Sequence[str] = DEFAULT_PATTERNS,
    trees: Sequence[str] = DEFAULT_TREES,
    dry_run: bool = False,
) -> CleanResult:
    """Remove temporary artefacts under *root* matching *patterns* safely."""

    root = root.resolve()
    result = CleanResult()
    matched_paths: set[Path] = set()

    info("✨ Cleaning repository temporary files...", use_emoji=True)
    matched_paths.update(_collect_matches(root, patterns, recursive=True))

    for tree in trees:
        directory = (root / tree).resolve()
        if not directory.exists():
            continue
        info(f"🧹 Cleaning {tree}/ ...", use_emoji=True)
        matched_paths.update(_collect_matches(directory, patterns, recursive=True, root=root))

    for path in sorted(matched_paths):
        if not path.exists():
            continue
        if dry_run:
            result.register_skipped(path)
            continue
        _remove_path(path)
        result.register_removed(path)

    if dry_run:
        ok(
            f"Would remove {len(result.skipped)} paths (dry run)",
            use_emoji=True,
        )
    else:
        ok(f"Removed {len(result.removed)} paths", use_emoji=True)
    return result


def _collect_matches(
    base: Path,
    patterns: Sequence[str],
    *,
    recursive: bool,
    root: Path | None = None,
) -> set[Path]:
    collected: set[Path] = set()
    root = root or base
    for pattern in patterns:
        glob_iter = base.rglob(pattern) if recursive else base.glob(pattern)
        for candidate in glob_iter:
            candidate = candidate.resolve()
            if not candidate.exists():
                continue
            if not _is_within(candidate, root):
                warn(f"Skipping outside path {candidate}", use_emoji=True)
                continue
            if _is_protected(candidate, root):
                continue
            collected.add(candidate)
    return collected


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _is_protected(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path
    parts = relative.parts
    return any(part in {".git", ".hg", ".svn"} for part in parts)


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink(missing_ok=True)
        except PermissionError:
            warn(f"Permission denied removing {path}", use_emoji=True)


__all__ = ["sparkly_clean", "CleanResult", "DEFAULT_PATTERNS", "DEFAULT_TREES"]
