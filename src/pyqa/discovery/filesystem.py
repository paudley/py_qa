# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Filesystem discovery strategy."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from pyqa.core.config.constants import ALWAYS_EXCLUDE_DIRS, PY_QA_DIR_NAME
from pyqa.platform.workspace import is_py_qa_workspace

from ..config import FileDiscoveryConfig
from .base import DiscoveryStrategy, is_within_limits, resolve_limit_paths


@dataclass(frozen=True, slots=True)
class WalkContext:
    """Parameters required to walk the filesystem hierarchy."""

    base: Path
    excludes: frozenset[Path]
    limits: tuple[Path, ...]
    root: Path
    allow_root_py_qa: bool
    follow_symlinks: bool


class FilesystemDiscovery(DiscoveryStrategy):
    """Traverse the filesystem collecting candidate files."""

    def __init__(self, *, follow_symlinks: bool = False) -> None:
        """Create a discovery strategy optionally following symlinks.

        Args:
            follow_symlinks: When ``True`` walk directories pointed to by
                symlinks instead of skipping them.
        """

        self.follow_symlinks = follow_symlinks

    @property
    def identifier(self) -> str:
        """Return the identifier for the filesystem discovery strategy."""

        return "filesystem"

    def discover(self, config: FileDiscoveryConfig, root: Path) -> Iterable[Path]:
        """Yield files deemed discoverable under ``root``.

        Args:
            config: User-provided discovery configuration.
            root: Repository root directory.

        Yields:
            Path: Absolute paths for files that satisfy discovery criteria.
        """

        limits = tuple(resolve_limit_paths(config.limit_to, root))

        explicit = list(self._yield_explicit_files(config, root, limits))
        if explicit:
            yield from explicit
            return

        if config.paths_from_stdin:
            yield from self._paths_from_stdin(root)
            return

        excludes = frozenset(root.joinpath(path).resolve() for path in config.excludes)
        allow_root_py_qa = is_py_qa_workspace(root)
        for base in self._iter_root_candidates(config, root, limits):
            if base.is_file():
                resolved = base.resolve()
                if is_within_limits(resolved, limits):
                    yield resolved
                continue
            context = WalkContext(
                base=base,
                excludes=excludes,
                limits=limits,
                root=root,
                allow_root_py_qa=allow_root_py_qa,
                follow_symlinks=self.follow_symlinks,
            )
            yield from self._walk(context)

    def __call__(self, config: FileDiscoveryConfig, root: Path) -> Iterable[Path]:
        """Delegate to :meth:`discover` enabling callable semantics."""

        return self.discover(config, root)

    def _yield_explicit_files(
        self,
        config: FileDiscoveryConfig,
        root: Path,
        limits: Sequence[Path],
    ) -> Iterable[Path]:
        """Yield explicitly provided paths fitting within ``limits``.

        Args:
            config: Discovery configuration with explicit entries.
            root: Repository root used to resolve relative paths.
            limits: Optional list of limit directories.

        Yields:
            Path: Resolved file paths that should be included.
        """

        for entry in config.explicit_files:
            candidate = entry if entry.is_absolute() else root / entry
            if not candidate.exists():
                continue
            resolved = candidate.resolve()
            if is_within_limits(resolved, limits):
                yield resolved

    def _iter_root_candidates(
        self,
        config: FileDiscoveryConfig,
        root: Path,
        limits: Sequence[Path],
    ) -> Iterable[Path]:
        """Yield base directories to traverse for discovery.

        Args:
            config: Discovery configuration including roots.
            root: Repository root directory.
            limits: Normalised list of limit directories.

        Yields:
            Path: Candidate base directories.
        """

        for base in self._resolve_roots(config, root):
            resolved = base.resolve()
            if limits and not is_within_limits(resolved, limits):
                continue
            if not resolved.exists():
                continue
            yield resolved

    def _resolve_roots(self, config: FileDiscoveryConfig, root: Path) -> Iterator[Path]:
        """Resolve configured roots relative to ``root``.

        Args:
            config: Discovery configuration with ``roots`` entries.
            root: Repository root directory.

        Yields:
            Path: Possibly unresolved candidate root paths.
        """

        for entry in config.roots:
            candidate = entry if entry.is_absolute() else root / entry
            yield candidate

    def _walk(self, context: WalkContext) -> Iterator[Path]:
        """Walk ``context.base`` yielding files within scope.

        Args:
            context: Immutable walk context containing traversal settings.

        Yields:
            Path: Files that satisfy exclusion and limit rules.
        """

        for dirpath, dirnames, filenames in os.walk(context.base, followlinks=context.follow_symlinks):
            current = Path(dirpath)
            if self._should_skip_directory(current, context):
                dirnames[:] = []
                continue
            dirnames[:] = [name for name in dirnames if not self._should_skip_directory(current / name, context)]
            for filename in filenames:
                candidate = current / filename
                if self._is_excluded(candidate, context):
                    continue
                resolved = candidate.resolve()
                if is_within_limits(resolved, context.limits):
                    yield resolved

    def _paths_from_stdin(self, root: Path) -> Iterator[Path]:
        """Yield paths read from STDIN relative to ``root``.

        Args:
            root: Repository root directory.

        Yields:
            Path: Resolved candidate paths supplied via STDIN.
        """

        for line in sys.stdin.read().splitlines():
            entry = line.strip()
            if not entry:
                continue
            candidate = Path(entry)
            yield (candidate if candidate.is_absolute() else root / candidate).resolve()

    def _should_skip_directory(self, path: Path, context: WalkContext) -> bool:
        """Return whether ``path`` should be skipped during traversal.

        Args:
            path: Directory currently being examined.
            context: Traversal context containing excludes and limits.

        Returns:
            bool: ``True`` if the directory should not be traversed.
        """

        if any(path.is_relative_to(ex) for ex in context.excludes):
            return True
        if path.name not in ALWAYS_EXCLUDE_DIRS:
            return False
        return not _should_include_py_qa(
            path,
            context.base,
            context.root,
            allow_root_py_qa=context.allow_root_py_qa,
        )

    def _is_excluded(self, candidate: Path, context: WalkContext) -> bool:
        """Return whether ``candidate`` should be excluded from results.

        Args:
            candidate: File candidate discovered during walking.
            context: Traversal context containing excludes and limits.

        Returns:
            bool: ``True`` when ``candidate`` matches an exclusion.
        """

        return any(candidate.is_relative_to(ex) for ex in context.excludes)


def _should_include_py_qa(
    current: Path,
    base: Path,
    root: Path,
    *,
    allow_root_py_qa: bool,
) -> bool:
    """Return whether the py_qa directory should be retained during walk.

    Args:
        current: Directory currently under consideration.
        base: Base directory from which the walk originated.
        root: Repository root directory.
        allow_root_py_qa: Flag indicating whether py_qa root should be kept.

    Returns:
        bool: ``True`` when the py_qa workspace directory should be included.
    """

    if not allow_root_py_qa or current.name != PY_QA_DIR_NAME:
        return False
    try:
        return current.resolve() == root.resolve() and base.resolve() == root.resolve()
    except OSError:
        return False
