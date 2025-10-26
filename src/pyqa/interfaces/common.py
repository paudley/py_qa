# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Shared protocol building blocks reused across pyqa interfaces."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class RepositoryRootProvider(Protocol):
    """Expose repository root paths required by runtime components."""

    @property
    def root(self) -> Path:
        """Return the repository root used for relative path resolution.

        Returns:
            Path: Repository root path.
        """

        raise NotImplementedError


@runtime_checkable
class PathSelectionOptions(RepositoryRootProvider, Protocol):
    """Describe coarse path selection controls used during discovery."""

    @property
    def paths(self) -> Sequence[Path]:
        """Return explicit file paths selected for discovery.

        Returns:
            Sequence[Path]: Files explicitly requested for discovery.
        """

        raise NotImplementedError

    @property
    def dirs(self) -> Sequence[Path]:
        """Return directory paths that should be recursively explored.

        Returns:
            Sequence[Path]: Directories to scan recursively.
        """

        raise NotImplementedError

    @property
    def exclude(self) -> Sequence[Path]:
        """Return paths that must be excluded from discovery.

        Returns:
            Sequence[Path]: Paths excluded from discovery.
        """

        raise NotImplementedError

    @property
    def include_dotfiles(self) -> bool:
        """Indicate whether dot-prefixed files should be included.

        Returns:
            bool: ``True`` when dotfiles should be considered.
        """

        raise NotImplementedError

    @property
    def paths_from_stdin(self) -> bool:
        """Return whether target paths were supplied via standard input.

        Returns:
            bool: ``True`` when target paths originated from standard input.
        """

        raise NotImplementedError


@runtime_checkable
class CacheControlOptions(RepositoryRootProvider, Protocol):
    """Expose cache directory configuration shared across tooling interfaces."""

    @property
    def cache_dir(self) -> Path:
        """Return the cache directory applicable to the current invocation.

        Returns:
            Path: Directory used for caching tool or linter results.
        """

        raise NotImplementedError

    @property
    def no_cache(self) -> bool:
        """Return whether caching behaviour should be disabled.

        Returns:
            bool: ``True`` when caching must be bypassed entirely.
        """

        raise NotImplementedError


__all__ = ["CacheControlOptions", "PathSelectionOptions", "RepositoryRootProvider"]
