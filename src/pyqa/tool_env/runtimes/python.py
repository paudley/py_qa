# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime handler for Python-based tooling via uv."""

from __future__ import annotations

from ..constants import PYQA_ROOT, UV_CACHE_DIR
from ..models import PreparedCommand
from .base import RuntimeContext, RuntimeHandler


class PythonRuntime(RuntimeHandler):
    """Provision Python tools via uv with system/project fallbacks."""

    def _try_project(self, context: RuntimeContext) -> PreparedCommand | None:
        """Return project Python tooling when version constraints are satisfied."""

        version = None
        if context.tool.version_command:
            version = self._versions.capture(context.tool.version_command)
        if version is None and context.target_version is not None:
            return None
        if not self._versions.is_compatible(version, context.target_version):
            return None
        return PreparedCommand.from_parts(cmd=context.command, env=None, version=version, source="project")

    def _prepare_local(self, context: RuntimeContext) -> PreparedCommand:
        """Provision Python tooling using uv and return the updated command."""

        requirement = context.tool.package or context.tool.name
        if context.tool.min_version:
            requirement = f"{requirement}=={context.tool.min_version}"
        cmd = [
            "uv",
            "--project",
            str(PYQA_ROOT),
            "run",
            "--with",
            requirement,
            *context.command,
        ]
        env = {
            "UV_CACHE_DIR": str(UV_CACHE_DIR),
            "UV_PROJECT": str(PYQA_ROOT),
        }
        version = None
        if context.tool.version_command:
            version = self._versions.capture(context.tool.version_command)
        return PreparedCommand.from_parts(cmd=cmd, env=env, version=version, source="local")


__all__ = ["PythonRuntime"]
