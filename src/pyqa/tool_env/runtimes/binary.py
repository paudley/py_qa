# SPDX-License-Identifier: MIT
"""Runtime handler for tools executed as plain binaries."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ...tools.base import Tool
from ..models import PreparedCommand
from .base import RuntimeHandler


class BinaryRuntime(RuntimeHandler):
    """Fallback runtime for tools executed directly as system binaries."""

    def _prepare_local(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand:
        return PreparedCommand.from_parts(
            cmd=base_cmd, env=None, version=None, source="system"
        )


__all__ = ["BinaryRuntime"]
