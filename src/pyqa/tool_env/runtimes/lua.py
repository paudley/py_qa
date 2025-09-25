# SPDX-License-Identifier: MIT
"""Runtime handler for Lua-based tooling via LuaRocks."""

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
from ..utils import _slugify, _split_package_spec
from .base import RuntimeHandler


class LuaRuntime(RuntimeHandler):
    """Provision Lua tooling using luarocks."""

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
        binary_name = Path(base_cmd[0]).name
        binary_path = self._ensure_local_tool(tool, binary_name)
        cmd = list(base_cmd)
        cmd[0] = str(binary_path)
        env = self._lua_env(root)
        version = None
        if tool.version_command:
            version = self._versions.capture(tool.version_command, env=self._merge_env(env))
        return PreparedCommand.from_parts(cmd=cmd, env=env, version=version, source="local")

    def _ensure_local_tool(self, tool: Tool, binary_name: str) -> Path:
        package, version = self._package_spec(tool)
        if not shutil.which("luarocks"):
            raise RuntimeError("luarocks is required to install Lua-based linters")

        slug = _slugify(f"{package}@{version or 'latest'}")
        prefix = tool_constants.LUA_CACHE_DIR / slug
        meta_file = tool_constants.LUA_META_DIR / f"{slug}.json"
        binary = tool_constants.LUA_BIN_DIR / binary_name

        if binary.exists() and meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                if meta.get("package") == package and meta.get("version") == version:
                    return binary
            except json.JSONDecodeError:
                pass

        prefix.mkdir(parents=True, exist_ok=True)
        tool_constants.LUA_META_DIR.mkdir(parents=True, exist_ok=True)
        tool_constants.LUA_BIN_DIR.mkdir(parents=True, exist_ok=True)
        tool_constants.LUA_WORK_DIR.mkdir(parents=True, exist_ok=True)

        args = [
            "luarocks",
            "--tree",
            str(prefix),
            "install",
            package,
        ]
        if version:
            args.append(version)
        run_command(args, capture_output=True)
        target = prefix / "bin" / binary_name
        if not target.exists():
            msg = f"Failed to install lua tool '{tool.name}'"
            raise RuntimeError(msg)

        shutil.copy2(target, binary)
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        meta_file.write_text(
            json.dumps({"package": package, "version": version}),
            encoding="utf-8",
        )
        return binary

    @staticmethod
    def _package_spec(tool: Tool) -> tuple[str, str | None]:
        if tool.package:
            package, version = _split_package_spec(tool.package)
            return package, version
        return tool.name, tool.min_version

    @staticmethod
    def _lua_env(root: Path) -> dict[str, str]:
        path_value = os.environ.get("PATH", "")
        entries = [str(tool_constants.LUA_BIN_DIR)]
        if path_value:
            entries.append(path_value)
        return {
            "PATH": os.pathsep.join(entries),
            "PWD": str(root),
        }


__all__ = ["LuaRuntime"]
