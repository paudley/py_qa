# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Discovery helpers for the pyqa package."""

from __future__ import annotations

from pathlib import Path

from ..config import FileDiscoveryConfig
from .base import DiscoveryService, DiscoveryStrategy
from .filesystem import FilesystemDiscovery
from .git import GitDiscovery
from .planners import build_project_scanner
from .rules import compile_exclude_arguments, is_under_any, normalize_path_requirement, path_matches_requirements

__all__ = [
    "DiscoveryService",
    "DiscoveryStrategy",
    "FilesystemDiscovery",
    "GitDiscovery",
    "build_default_discovery",
    "build_project_scanner",
    "compile_exclude_arguments",
    "is_under_any",
    "normalize_path_requirement",
    "path_matches_requirements",
]


class DefaultDiscovery(DiscoveryService):
    """Discovery pipeline that prefers Git when change tracking is requested."""

    def __init__(self, filesystem: FilesystemDiscovery, git: GitDiscovery) -> None:
        """Create a default discovery pipeline.

        Args:
            filesystem: Filesystem-based discovery strategy.
            git: Git-backed discovery strategy.
        """
        super().__init__((git, filesystem))
        self._filesystem = filesystem
        self._git = git

    def run(self, config: FileDiscoveryConfig, root: Path) -> list[Path]:
        """Return discovered files honouring git change tracking when possible.

        Args:
            config: Discovery configuration provided by the caller.
            root: Repository root used to resolve relative paths.

        Returns:
            list[Path]: Resolved file paths in execution order.
        """

        changed = list(self._git.discover(config, root))
        if changed:
            return changed
        return list(self._filesystem.discover(config, root))

    def strategies(self) -> tuple[DiscoveryStrategy, ...]:
        """Return the configured discovery strategies in evaluation order.

        Returns:
            tuple[DiscoveryStrategy, ...]: Ordered strategies used by the pipeline.
        """

        return (self._git, self._filesystem)

    def __call__(self, config: FileDiscoveryConfig, root: Path) -> list[Path]:
        """Delegate to :meth:`run` enabling callable semantics.

        Args:
            config: Discovery configuration supplied by the caller.
            root: Repository root used for resolving relative paths.

        Returns:
            list[Path]: Discovered paths returned by :meth:`run`.
        """

        return self.run(config, root)


def build_default_discovery() -> DefaultDiscovery:
    """Construct the default discovery pipeline used by the CLI.

    Returns:
        DefaultDiscovery: Discovery pipeline composed of git and filesystem.
    """
    return DefaultDiscovery(filesystem=FilesystemDiscovery(), git=GitDiscovery())
