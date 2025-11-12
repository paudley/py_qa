# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime handler for Python-based tooling via uv."""

from __future__ import annotations

from ..models import PreparedCommand
from .base import RuntimeContext, RuntimeHandler


class PythonRuntime(RuntimeHandler):
    """Provide the runtime for Python tools via uv with fallback strategies."""

    def _try_project(self, context: RuntimeContext) -> PreparedCommand | None:
        """Return the project command when version constraints are satisfied.

        Args:
            context: Runtime context describing command preparation parameters.

        Returns:
            PreparedCommand | None: Prepared project command, or ``None`` when incompatible.
        """

        version = None
        if context.tool.version_command:
            version = self._versions.capture(context.tool.version_command)
        if version is None and context.target_version is not None:
            return None
        if not self._versions.is_compatible(version, context.target_version):
            return None
        return PreparedCommand.from_parts(cmd=context.command, env=None, version=version, source="project")

    def _prepare_local(self, context: RuntimeContext) -> PreparedCommand:
        """Return the command after provisioning Python tooling using uv.

        Args:
            context: Runtime context describing command preparation parameters.

        Returns:
            PreparedCommand: Prepared command referencing the uv-managed environment.
        """

        requirement = context.tool.package or context.tool.name
        if context.tool.min_version:
            requirement = f"{requirement}=={context.tool.min_version}"
        cmd = [
            "uv",
            "--project",
            str(context.pyqa_root),
            "run",
            "--with",
            requirement,
            *context.command,
        ]
        env = {
            "UV_CACHE_DIR": str(context.cache_layout.uv_dir),
            "UV_PROJECT": str(context.pyqa_root),
        }
        version = None
        if context.tool.version_command:
            version = self._versions.capture(context.tool.version_command)
        return PreparedCommand.from_parts(cmd=cmd, env=env, version=version, source="local")


__all__ = ["PythonRuntime"]
