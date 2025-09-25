# SPDX-License-Identifier: MIT
"""Runtime abstraction for preparing tool commands."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from pathlib import Path

from ...tools.base import Tool
from ..models import PreparedCommand
from ..utils import desired_version
from ..versioning import VersionResolver


class RuntimeHandler(ABC):
    """Strategy object responsible for preparing tool commands per runtime."""

    def __init__(self, versions: VersionResolver) -> None:
        self._versions = versions

    def prepare(
        self,
        *,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        project_mode: bool,
        system_preferred: bool,
        use_local_override: bool,
    ) -> PreparedCommand:
        target_version = desired_version(tool)

        if use_local_override or tool.prefer_local:
            return self._prepare_local(tool, base_cmd, root, cache_dir, target_version)

        if project_mode:
            project_cmd = self._try_project(tool, base_cmd, root, cache_dir, target_version)
            if project_cmd is not None:
                return project_cmd

        if system_preferred:
            system_cmd = self._try_system(tool, base_cmd, root, cache_dir, target_version)
            if system_cmd is not None:
                return system_cmd

        fallback_project = self._try_project(tool, base_cmd, root, cache_dir, target_version)
        if fallback_project is not None:
            return fallback_project

        return self._prepare_local(tool, base_cmd, root, cache_dir, target_version)

    @abstractmethod
    def _try_system(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand | None:
        raise NotImplementedError

    @abstractmethod
    def _try_project(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand | None:
        raise NotImplementedError

    @abstractmethod
    def _prepare_local(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand:
        raise NotImplementedError

    @staticmethod
    def _merge_env(overrides: Mapping[str, str] | None = None) -> dict[str, str]:
        env = os.environ.copy()
        if overrides:
            env.update(overrides)
        return env


__all__ = ["RuntimeHandler"]
