# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared protocol building blocks reused across pyqa interfaces."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class RepositoryRootProvider(Protocol):
    """Expose repository root paths required by runtime components.

    Attributes:
        root: Repository root path used for relative resolution.
    """

    @property
    def root(self) -> Path:
        """Return the repository root path used for relative resolution.

        Returns:
            Path: Path representing the repository root.
        """

        raise NotImplementedError

    def root_exists(self) -> bool:
        """Return ``True`` when the resolved repository root exists on disk.

        Returns:
            bool: ``True`` if :meth:`root` points to an existing directory.
        """

        return self.root.exists()


@runtime_checkable
class PathSelectionOptions(RepositoryRootProvider, Protocol):
    """Describe coarse path selection controls used during discovery.

    Attributes:
        paths: Explicit file paths selected for discovery.
        dirs: Directory paths that should be recursively explored.
        exclude: Paths that must be excluded from discovery.
        include_dotfiles: Flag indicating whether dot-prefixed files are included.
        paths_from_stdin: Flag indicating whether targets were provided via stdin.
    """

    @property
    def paths(self) -> Sequence[Path]:
        """Return explicit file paths selected for discovery.

        Returns:
            Sequence[Path]: Files explicitly requested for linting.
        """

        raise NotImplementedError("PathSelectionOptions.paths")

    @property
    def dirs(self) -> Sequence[Path]:
        """Return directory paths that should be recursively explored.

        Returns:
            Sequence[Path]: Directories slated for recursive discovery.
        """

        raise NotImplementedError("PathSelectionOptions.dirs")

    @property
    def exclude(self) -> Sequence[Path]:
        """Return paths that must be excluded from discovery.

        Returns:
            Sequence[Path]: Paths that discovery must skip.
        """

        raise NotImplementedError("PathSelectionOptions.exclude")

    @property
    def include_dotfiles(self) -> bool:
        """Return whether dot-prefixed files are included in discovery.

        Returns:
            bool: ``True`` when dot-prefixed entries remain eligible.
        """

        raise NotImplementedError("PathSelectionOptions.include_dotfiles")

    @property
    def paths_from_stdin(self) -> bool:
        """Return whether discovery targets were provided via stdin.

        Returns:
            bool: ``True`` when targets were injected through standard input.
        """

        raise NotImplementedError("PathSelectionOptions.paths_from_stdin")

    def iter_targets(self) -> Sequence[Path]:
        """Return a sequence containing both explicit and directory targets.

        Returns:
            Sequence[Path]: Combined listing of explicit and directory targets.
        """

        return tuple(self.paths) + tuple(self.dirs)


@runtime_checkable
class CacheControlOptions(RepositoryRootProvider, Protocol):
    """Expose cache directory configuration shared across tooling interfaces.

    Attributes:
        cache_dir: Directory used for caching tool or linter results.
        no_cache: Flag indicating whether caching must be bypassed entirely.
    """

    @property
    def cache_dir(self) -> Path:
        """Return the directory used to persist cache contents.

        Returns:
            Path: Directory used for caching artefacts.
        """

        raise NotImplementedError("CacheControlOptions.cache_dir")

    @property
    def no_cache(self) -> bool:
        """Return ``True`` when caching must be bypassed entirely.

        Returns:
            bool: ``True`` when cache usage is disabled.
        """

        raise NotImplementedError("CacheControlOptions.no_cache")

    def caching_enabled(self) -> bool:
        """Return ``True`` when caching behaviour is enabled for this run.

        Returns:
            bool: ``True`` when caching should be performed.
        """

        return not self.no_cache


__all__ = ["CacheControlOptions", "PathSelectionOptions", "RepositoryRootProvider"]
