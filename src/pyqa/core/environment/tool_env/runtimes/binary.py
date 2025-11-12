# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime handler for tools executed as plain binaries."""

from __future__ import annotations

from ..models import PreparedCommand
from .base import RuntimeContext, RuntimeHandler


class BinaryRuntime(RuntimeHandler):
    """Provide the fallback runtime for tools executed as system binaries."""

    def _try_system(self, context: RuntimeContext) -> PreparedCommand | None:
        """Return the system command when the binary is available.

        Args:
            context: Runtime context describing command preparation parameters.

        Returns:
            PreparedCommand | None: Prepared system command, or ``None`` when unavailable.
        """

        return PreparedCommand.from_parts(cmd=context.command, env=None, version=None, source="system")

    def _try_project(self, context: RuntimeContext) -> PreparedCommand | None:
        """Return the project-local command when the ``bin`` directory contains the executable.

        Args:
            context: Runtime context describing command preparation parameters.

        Returns:
            PreparedCommand | None: Prepared project command, or ``None`` when the binary is absent.
        """

        return self._project_binary(context)

    def _prepare_local(self, context: RuntimeContext) -> PreparedCommand:
        """Return the fallback command used for local execution.

        Args:
            context: Runtime context describing command preparation parameters.

        Returns:
            PreparedCommand: Prepared command matching the original invocation.
        """

        return PreparedCommand.from_parts(cmd=context.command, env=None, version=None, source="system")


__all__ = ["BinaryRuntime"]
