# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Filesystem discovery strategy."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable, Iterator

from ..config import FileDiscoveryConfig
from ..constants import ALWAYS_EXCLUDE_DIRS
from .base import DiscoveryStrategy


class FilesystemDiscovery(DiscoveryStrategy):
    """Traverse the filesystem collecting candidate files."""

    def __init__(self, *, follow_symlinks: bool = False) -> None:
        self.follow_symlinks = follow_symlinks

    def discover(self, config: FileDiscoveryConfig, root: Path) -> Iterable[Path]:
        limits = self._normalise_limits(config, root)

        if config.explicit_files:
            for entry in config.explicit_files:
                candidate = entry if entry.is_absolute() else root / entry
                if not candidate.exists():
                    continue
                resolved = candidate.resolve()
                if self._is_within_limits(resolved, limits):
                    yield resolved
            return
        if config.paths_from_stdin:
            yield from self._paths_from_stdin(root)
            return

        excludes = {root.joinpath(p).resolve() for p in config.excludes}
        for base in self._resolve_roots(config, root):
            if limits and not self._is_within_limits(base.resolve(), limits):
                continue
            if not base.exists():
                continue
            if base.is_file():
                resolved = base.resolve()
                if self._is_within_limits(resolved, limits):
                    yield resolved
                continue
            yield from self._walk(base, excludes, limits)

    def _resolve_roots(self, config: FileDiscoveryConfig, root: Path) -> Iterator[Path]:
        for entry in config.roots:
            candidate = entry if entry.is_absolute() else root / entry
            yield candidate

    def _walk(self, base: Path, excludes: set[Path], limits: list[Path]) -> Iterator[Path]:
        follow_links = self.follow_symlinks
        for dirpath, dirnames, filenames in os.walk(base, followlinks=follow_links):
            current = Path(dirpath)
            if current.name in ALWAYS_EXCLUDE_DIRS or any(self._is_child_of(current, ex) for ex in excludes):
                dirnames[:] = []
                continue
            dirnames[:] = [
                name
                for name in dirnames
                if name not in ALWAYS_EXCLUDE_DIRS and not any(self._is_child_of(current / name, ex) for ex in excludes)
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
