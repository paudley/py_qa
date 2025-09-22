# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Discovery helpers for the pyqa package."""

from __future__ import annotations

from pathlib import Path

from ..config import FileDiscoveryConfig
from .base import DiscoveryService, DiscoveryStrategy
from .filesystem import FilesystemDiscovery
from .git import GitDiscovery

__all__ = [
    "DiscoveryService",
    "DiscoveryStrategy",
    "FilesystemDiscovery",
    "GitDiscovery",
    "build_default_discovery",
]


class DefaultDiscovery(DiscoveryService):
    """Discovery pipeline that prefers Git when change tracking is requested."""

    def __init__(self, filesystem: FilesystemDiscovery, git: GitDiscovery) -> None:
        super().__init__((git, filesystem))
        self._filesystem = filesystem
        self._git = git

    def run(self, config: FileDiscoveryConfig, root: Path) -> list[Path]:
        changed = list(self._git.discover(config, root))
        if changed:
            return changed
        return list(self._filesystem.discover(config, root))


def build_default_discovery() -> DefaultDiscovery:
    """Factory for the default discovery pipeline."""

    return DefaultDiscovery(filesystem=FilesystemDiscovery(), git=GitDiscovery())
