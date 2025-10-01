# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime handler for Go-based tooling."""

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
from ..utils import _slugify, _split_package_spec
from .base import RuntimeContext, RuntimeHandler


class GoRuntime(RuntimeHandler):
    """Provision Go tooling by installing modules into a dedicated cache."""

    def _try_project(self, context: RuntimeContext) -> PreparedCommand | None:
        """Reuse project ``bin`` directory when a tool-specific binary exists."""

        return self._project_binary(context)

    def _prepare_local(self, context: RuntimeContext) -> PreparedCommand:
        """Install Go tooling into the shared cache and return the command."""

        if not shutil.which("go"):
            raise RuntimeError("Go toolchain is required to install go-based linters")

        binary_name = Path(context.executable).name
        binary_path = self._ensure_local_tool(context.tool, binary_name)

        cmd = context.command_list()
        cmd[0] = str(binary_path)

        env = self._go_env(context.root)
        version = None
        if context.tool.version_command:
            version = self._versions.capture(context.tool.version_command, env=self._merge_env(env))
        return PreparedCommand.from_parts(cmd=cmd, env=env, version=version, source="local")

    def _ensure_local_tool(self, tool: Tool, binary_name: str) -> Path:
        """Install or reuse a cached Go binary for ``tool``."""

        module, version_spec = self._module_spec(tool)
        if not version_spec:
            version_spec = "latest"
        requirement = f"{module}@{version_spec}"
        slug = _slugify(requirement)
        meta_file = tool_constants.GO_META_DIR / f"{slug}.json"
        binary = tool_constants.GO_BIN_DIR / binary_name

        if binary.exists() and meta_file.exists():
            meta = self._load_json(meta_file)
            if meta and meta.get("requirement") == requirement:
                return binary

        tool_constants.GO_META_DIR.mkdir(parents=True, exist_ok=True)
        tool_constants.GO_BIN_DIR.mkdir(parents=True, exist_ok=True)
        (tool_constants.GO_WORK_DIR / "gopath").mkdir(parents=True, exist_ok=True)
        (tool_constants.GO_WORK_DIR / "gocache").mkdir(parents=True, exist_ok=True)
        (tool_constants.GO_WORK_DIR / "modcache").mkdir(parents=True, exist_ok=True)

        env = os.environ.copy()
        env.setdefault("GOBIN", str(tool_constants.GO_BIN_DIR))
        env.setdefault("GOCACHE", str(tool_constants.GO_WORK_DIR / "gocache"))
        env.setdefault("GOMODCACHE", str(tool_constants.GO_WORK_DIR / "modcache"))
        env.setdefault("GOPATH", str(tool_constants.GO_WORK_DIR / "gopath"))

        run_command(
            ["go", "install", requirement],
            capture_output=True,
            env=env,
        )

        if not binary.exists():
            msg = f"Failed to install go tool '{tool.name}'"
            raise RuntimeError(msg)

        meta_file.write_text(json.dumps({"requirement": requirement}), encoding="utf-8")
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return binary

    @staticmethod
    def _module_spec(tool: Tool) -> tuple[str, str | None]:
        """Return module and version specifiers derived from ``tool`` metadata."""
        if tool.package:
            module, version = _split_package_spec(tool.package)
            return module, version
        return tool.name, tool.min_version

    @staticmethod
    def _go_env(root: Path) -> dict[str, str]:
        """Return environment variables required for executing Go tools."""
        return RuntimeHandler._prepend_path_environment(bin_dir=tool_constants.GO_BIN_DIR, root=root)


__all__ = ["GoRuntime"]
