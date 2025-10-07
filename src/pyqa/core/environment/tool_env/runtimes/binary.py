# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime handler for tools executed as plain binaries."""

from __future__ import annotations

from ..models import PreparedCommand
from .base import RuntimeContext, RuntimeHandler


class BinaryRuntime(RuntimeHandler):
    """Fallback runtime for tools executed directly as system binaries."""

    def _try_system(self, context: RuntimeContext) -> PreparedCommand | None:
        """Binary runtime delegates system execution without modification."""

        return PreparedCommand.from_parts(cmd=context.command, env=None, version=None, source="system")

    def _try_project(self, context: RuntimeContext) -> PreparedCommand | None:
        """Use ``bin`` directory inside the project when present."""

        return self._project_binary(context)

    def _prepare_local(self, context: RuntimeContext) -> PreparedCommand:
        """Local fallback simply reuses the base command."""

        return PreparedCommand.from_parts(cmd=context.command, env=None, version=None, source="system")


__all__ = ["BinaryRuntime"]
