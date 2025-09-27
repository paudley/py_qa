# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime handler for Perl-based tooling."""

from __future__ import annotations

import json
import os
import shutil
import stat
from collections.abc import Sequence
from pathlib import Path

from ...process_utils import run_command
from ...tools.base import Tool
from .. import constants as tool_constants
from ..models import PreparedCommand
from ..utils import slugify
from .base import RuntimeHandler


class PerlRuntime(RuntimeHandler):
    """Provision Perl tooling using cpanm."""

    def _try_system(
        self,
        tool: Tool,
        base_cmd: Sequence[str],
        root: Path,
        cache_dir: Path,
        target_version: str | None,
    ) -> PreparedCommand | None:
        executable = shutil.which(base_cmd[0])
        if not executable:
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
        del cache_dir, target_version
        binary_name = Path(base_cmd[0]).name
        candidate = root / "bin" / binary_name
        if not candidate.exists():
            return None
        cmd = list(base_cmd)
        cmd[0] = str(candidate)
        env = self._perl_env(root)
        version = None
        if tool.version_command:
            version = self._versions.capture(tool.version_command, env=self._merge_env(env))
        return PreparedCommand.from_parts(
            cmd=cmd,
            env=env,
            version=version,
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
        binary_name = Path(base_cmd[0]).name
        binary_path = self._ensure_local_tool(tool, binary_name)
        cmd = list(base_cmd)
        cmd[0] = str(binary_path)
        env = self._perl_env(root)
        version = None
        if tool.version_command:
            version = self._versions.capture(tool.version_command, env=self._merge_env(env))
        return PreparedCommand.from_parts(cmd=cmd, env=env, version=version, source="local")

    def _ensure_local_tool(self, tool: Tool, binary_name: str) -> Path:
        requirement = tool.package or tool.name
        slug = slugify(requirement)
        prefix = tool_constants.PERL_CACHE_DIR / slug
        meta_file = tool_constants.PERL_META_DIR / f"{slug}.json"
        binary = tool_constants.PERL_BIN_DIR / binary_name

        if binary.exists() and meta_file.exists():
            try:
                data = json.loads(meta_file.read_text(encoding="utf-8"))
                if data.get("requirement") == requirement:
                    return binary
            except json.JSONDecodeError:
                pass

        prefix.mkdir(parents=True, exist_ok=True)
        tool_constants.PERL_META_DIR.mkdir(parents=True, exist_ok=True)
        tool_constants.PERL_BIN_DIR.mkdir(parents=True, exist_ok=True)

        cmd = [
            "cpanm",
            "--notest",
            "--reinstall",
            "--local-lib-contained",
            str(prefix),
            requirement,
        ]
        run_command(cmd, capture_output=True)

        target = prefix / "bin" / binary_name
        if not target.exists():
            msg = f"Failed to install perl tool '{tool.name}'"
            raise RuntimeError(msg)

        shutil.copy2(target, binary)
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        meta_file.write_text(json.dumps({"requirement": requirement}), encoding="utf-8")
        return binary

    @staticmethod
    def _perl_env(root: Path) -> dict[str, str]:
        path_value = os.environ.get("PATH", "")
        combined = (
            f"{tool_constants.PERL_BIN_DIR}{os.pathsep}{path_value}"
            if path_value
            else str(tool_constants.PERL_BIN_DIR)
        )
        return {
            "PATH": combined,
            "PWD": str(root),
        }


__all__ = ["PerlRuntime"]
