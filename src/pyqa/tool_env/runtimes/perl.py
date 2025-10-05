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
        env = self._perl_env(context)
        version = None
        if context.tool.version_command:
            version = self._versions.capture(context.tool.version_command, env=self._merge_env(env))
        project_cmd.env = env
        project_cmd.version = version
        return project_cmd

    def _prepare_local(self, context: RuntimeContext) -> PreparedCommand:
        """Install Perl tooling using cpanm and return the command."""

        return self._prepare_cached_command(
            context,
            self._ensure_local_tool,
            self._perl_env,
        )

    def _ensure_local_tool(self, context: RuntimeContext, binary_name: str) -> Path:
        """Ensure ``binary_name`` is installed for ``tool`` via cpanm."""

        tool = context.tool
        layout = context.cache_layout
        requirement = tool.package or tool.name
        slug = _slugify(requirement)
        prefix = layout.perl.cache_dir / slug
        meta_file = layout.perl.meta_dir / f"{slug}.json"
        binary = layout.perl.bin_dir / binary_name

        if binary.exists() and meta_file.exists():
            data = self._load_json(meta_file)
            if data and data.get("requirement") == requirement:
                return binary

        prefix.mkdir(parents=True, exist_ok=True)
        layout.perl.meta_dir.mkdir(parents=True, exist_ok=True)
        layout.perl.bin_dir.mkdir(parents=True, exist_ok=True)

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
    def _perl_env(context: RuntimeContext) -> dict[str, str]:
        """Return environment variables required for Perl tool execution."""
        path_value = os.environ.get("PATH", "")
        bin_dir = context.cache_layout.perl.bin_dir
        combined = f"{bin_dir}{os.pathsep}{path_value}" if path_value else str(bin_dir)
        return {
            "PATH": combined,
            "PWD": str(context.root),
        }


__all__ = ["PerlRuntime"]
