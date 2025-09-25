# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime handler for Python-based tooling via uv."""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path

from ...tools.base import Tool
from ..constants import PYQA_ROOT, UV_CACHE_DIR
from ..models import PreparedCommand
from .base import RuntimeHandler


class PythonRuntime(RuntimeHandler):
    """Provision Python tools via uv with system/project fallbacks."""

    def _try_system(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand | None:
        executable = base_cmd[0]
        if not shutil.which(executable):
            return None
        version = None
        if tool.version_command:
            version = self._versions.capture(tool.version_command)
        if not self._versions.is_compatible(version, target_version):
            return None
        return PreparedCommand.from_parts(cmd=base_cmd, env=None, version=version, source="system")

    def _try_project(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand | None:
        version = None
        if tool.version_command:
            version = self._versions.capture(tool.version_command)
        if version is None and target_version is not None:
            return None
        if not self._versions.is_compatible(version, target_version):
            return None
        return PreparedCommand.from_parts(cmd=base_cmd, env=None, version=version, source="project")

    def _prepare_local(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand:
        requirement = tool.package or tool.name
        if tool.min_version:
            requirement = f"{requirement}=={tool.min_version}"
        cmd = [
            "uv",
            "--project",
            str(PYQA_ROOT),
            "run",
            "--with",
            requirement,
            *base_cmd,
        ]
        env = {
            "UV_CACHE_DIR": str(UV_CACHE_DIR),
            "UV_PROJECT": str(PYQA_ROOT),
        }
        version = None
        if tool.version_command:
            version = self._versions.capture(tool.version_command)
        return PreparedCommand.from_parts(cmd=cmd, env=env, version=version, source="local")


__all__ = ["PythonRuntime"]
