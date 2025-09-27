# SPDX-License-Identifier: MIT
# Copyright (c) 2025 Blackcat Informatics® Inc.
"""Runtime handler for Go-based tooling."""

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
from ..utils import slugify, split_package_spec
from .base import RuntimeHandler


class GoRuntime(RuntimeHandler):
    """Provision Go tooling by installing modules into a dedicated cache."""

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
        if not shutil.which("go"):
            raise RuntimeError("Go toolchain is required to install go-based linters")

        binary_name = Path(base_cmd[0]).name
        binary_path = self._ensure_local_tool(tool, binary_name)

        cmd = list(base_cmd)
        cmd[0] = str(binary_path)

        env = self._go_env(root)
        version = None
        if tool.version_command:
            version = self._versions.capture(tool.version_command, env=self._merge_env(env))
        return PreparedCommand.from_parts(cmd=cmd, env=env, version=version, source="local")

    def _ensure_local_tool(self, tool: Tool, binary_name: str) -> Path:
        module, version_spec = self._module_spec(tool)
        if not version_spec:
            version_spec = "latest"
        requirement = f"{module}@{version_spec}"
        slug = slugify(requirement)
        meta_file = tool_constants.GO_META_DIR / f"{slug}.json"
        binary = tool_constants.GO_BIN_DIR / binary_name

        if binary.exists() and meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                if meta.get("requirement") == requirement:
                    return binary
            except json.JSONDecodeError:
                pass

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
        if tool.package:
            module, version = split_package_spec(tool.package)
            return module, version
        return tool.name, tool.min_version

    @staticmethod
    def _go_env(root: Path) -> dict[str, str]:
        path_value = os.environ.get("PATH", "")
        entries = [str(tool_constants.GO_BIN_DIR)]
        if path_value:
            entries.append(path_value)
        return {
            "PATH": os.pathsep.join(entries),
            "PWD": str(root),
        }


__all__ = ["GoRuntime"]
