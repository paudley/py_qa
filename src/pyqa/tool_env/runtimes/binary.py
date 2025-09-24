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

    def _try_system(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand | None:
        del tool, root, cache_dir, target_version
        return PreparedCommand.from_parts(
            cmd=base_cmd, env=None, version=None, source="system"
        )

    def _try_project(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand | None:
        del cache_dir, target_version
        binary_name = Path(base_cmd[0]).name
        candidate = root / "bin" / binary_name
        if not candidate.exists():
            return None
        cmd = list(base_cmd)
        cmd[0] = str(candidate)
        return PreparedCommand.from_parts(
            cmd=cmd,
            env=None,
            version=None,
            source="project",
        )

    def _prepare_local(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand:
        del tool, root, cache_dir, target_version
        return PreparedCommand.from_parts(
            cmd=base_cmd, env=None, version=None, source="system"
        )


__all__ = ["BinaryRuntime"]
