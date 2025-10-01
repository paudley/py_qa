# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime handler for Perl-based tooling."""

from __future__ import annotations

import json
import os
import shutil
import stat
from pathlib import Path

from ...process_utils import run_command
from ...tools.base import Tool
from .. import constants as tool_constants
from ..models import PreparedCommand
from ..utils import _slugify
from .base import RuntimeContext, RuntimeHandler


class PerlRuntime(RuntimeHandler):
    """Provision Perl tooling using cpanm."""

    def _try_project(self, context: RuntimeContext) -> PreparedCommand | None:
        """Reuse project ``bin`` directory when a Perl binary exists."""

        project_cmd = self._project_binary(context)
        if project_cmd is None:
            return None
        env = self._perl_env(context.root)
        version = None
        if context.tool.version_command:
            version = self._versions.capture(context.tool.version_command, env=self._merge_env(env))
        project_cmd.env = env
        project_cmd.version = version
        return project_cmd

    def _prepare_local(self, context: RuntimeContext) -> PreparedCommand:
        """Install Perl tooling using cpanm and return the command."""

        binary_name = Path(context.executable).name
        binary_path = self._ensure_local_tool(context.tool, binary_name)
        cmd = context.command_list()
        cmd[0] = str(binary_path)
        env = self._perl_env(context.root)
        version = None
        if context.tool.version_command:
            version = self._versions.capture(context.tool.version_command, env=self._merge_env(env))
        return PreparedCommand.from_parts(cmd=cmd, env=env, version=version, source="local")

    def _ensure_local_tool(self, tool: Tool, binary_name: str) -> Path:
        """Ensure ``binary_name`` is installed for ``tool`` via cpanm."""

        requirement = tool.package or tool.name
        slug = _slugify(requirement)
        prefix = tool_constants.PERL_CACHE_DIR / slug
        meta_file = tool_constants.PERL_META_DIR / f"{slug}.json"
        binary = tool_constants.PERL_BIN_DIR / binary_name

        if binary.exists() and meta_file.exists():
            data = self._load_json(meta_file)
            if data and data.get("requirement") == requirement:
                return binary

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
        """Return environment variables required for Perl tool execution."""
        path_value = os.environ.get("PATH", "")
        combined = (
            f"{tool_constants.PERL_BIN_DIR}{os.pathsep}{path_value}" if path_value else str(tool_constants.PERL_BIN_DIR)
        )
        return {
            "PATH": combined,
            "PWD": str(root),
        }


__all__ = ["PerlRuntime"]
