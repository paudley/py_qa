# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Filesystem discovery strategy."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable, Iterator

from ..config import FileDiscoveryConfig
from ..constants import ALWAYS_EXCLUDE_DIRS, PY_QA_DIR_NAME
from ..workspace import is_py_qa_workspace
from .base import DiscoveryStrategy


class FilesystemDiscovery(DiscoveryStrategy):
    """Traverse the filesystem collecting candidate files."""

    def __init__(self, *, follow_symlinks: bool = False) -> None:
        self.follow_symlinks = follow_symlinks

    def discover(self, config: FileDiscoveryConfig, root: Path) -> Iterable[Path]:
        limits = self._normalise_limits(config, root)

        explicit = list(self._yield_explicit_files(config, root, limits))
        if explicit:
            yield from explicit
            return

        if config.paths_from_stdin:
            yield from self._paths_from_stdin(root)
            return

        excludes = {root.joinpath(path).resolve() for path in config.excludes}
        allow_root_py_qa = is_py_qa_workspace(root)
        for base in self._iter_root_candidates(config, root, limits):
            if base.is_file():
                resolved = base.resolve()
                if self._is_within_limits(resolved, limits):
                    yield resolved
                continue
            yield from self._walk(
                base,
                excludes,
                limits,
                root=root,
                allow_root_py_qa=allow_root_py_qa,
            )

    def _yield_explicit_files(
        self,
        config: FileDiscoveryConfig,
        root: Path,
        limits: list[Path],
    ) -> Iterable[Path]:
        for entry in config.explicit_files:
            candidate = entry if entry.is_absolute() else root / entry
            if not candidate.exists():
                continue
            resolved = candidate.resolve()
            if self._is_within_limits(resolved, limits):
                yield resolved

    def _iter_root_candidates(
        self,
        config: FileDiscoveryConfig,
        root: Path,
        limits: list[Path],
    ) -> Iterable[Path]:
        for base in self._resolve_roots(config, root):
            resolved = base.resolve()
            if limits and not self._is_within_limits(resolved, limits):
                continue
            if not resolved.exists():
                continue
            yield resolved

    def _resolve_roots(self, config: FileDiscoveryConfig, root: Path) -> Iterator[Path]:
        for entry in config.roots:
            candidate = entry if entry.is_absolute() else root / entry
            yield candidate

    def _walk(
        self,
        base: Path,
        excludes: set[Path],
        limits: list[Path],
        *,
        root: Path,
        allow_root_py_qa: bool,
    ) -> Iterator[Path]:
        follow_links = self.follow_symlinks
        for dirpath, dirnames, filenames in os.walk(base, followlinks=follow_links):
            current = Path(dirpath)
            if (
                current.name in ALWAYS_EXCLUDE_DIRS
                and not _should_include_py_qa(
                    current,
                    base,
                    root,
                    allow_root_py_qa=allow_root_py_qa,
                )
            ) or any(self._is_child_of(current, ex) for ex in excludes):
                dirnames[:] = []
                continue
            dirnames[:] = [
                name
                for name in dirnames
                if name not in ALWAYS_EXCLUDE_DIRS
                and not any(self._is_child_of(current / name, ex) for ex in excludes)
            ]
            for filename in filenames:
                candidate = current / filename
                if any(self._is_child_of(candidate, ex) for ex in excludes):
                    continue
                resolved = candidate.resolve()
                if self._is_within_limits(resolved, limits):
                    yield resolved

    def _paths_from_stdin(self, root: Path) -> Iterator[Path]:
        for line in sys.stdin.read().splitlines():
            entry = line.strip()
            if not entry:
                continue
            candidate = Path(entry)
            yield (candidate if candidate.is_absolute() else root / candidate).resolve()

    @staticmethod
    def _is_child_of(candidate: Path, parent: Path) -> bool:
        try:
            candidate.relative_to(parent)
            return True
        except ValueError:
            return False

    def _normalise_limits(self, config: FileDiscoveryConfig, root: Path) -> list[Path]:
        limits: list[Path] = []
        for entry in config.limit_to:
            candidate = entry if entry.is_absolute() else root / entry
            resolved = candidate.resolve()
            if resolved not in limits:
                limits.append(resolved)
        return limits

    @staticmethod
    def _is_within_limits(candidate: Path, limits: list[Path]) -> bool:
        if not limits:
            return True
        for limit in limits:
            try:
                candidate.relative_to(limit)
                return True
            except ValueError:
                continue
        return False


def _should_include_py_qa(
    current: Path,
    base: Path,
    root: Path,
    *,
    allow_root_py_qa: bool,
) -> bool:
    if not allow_root_py_qa or current.name != PY_QA_DIR_NAME:
        return False
    try:
        return current.resolve() == root.resolve() and base.resolve() == root.resolve()
    except OSError:
        return False
